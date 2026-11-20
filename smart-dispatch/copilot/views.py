"""Sean AI Co-Pilot: email brokers, call assistant, broker directory, mailbox and call log."""

import math
from decimal import Decimal

from django import forms
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.mail import EmailMessage as OutgoingEmail
from django.core.paginator import Paginator
from django.db.models import Avg, Count, Exists, F, FloatField, Max, OuterRef, Q
from django.db.models.functions import Cast
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from accounts.forms import ProfileForm
from dispatch.models import Broker, US_STATES
from engine.models import CompanySettings
from loadboard.models import LoadPosting

from . import ai
from .models import CallLog, EmailMessage

BULK_LIMIT = 25


def _require_dispatcher(user):
    if not user.can_edit_operations:
        raise PermissionDenied


def _int_or_none(value):
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return None


def rate_targets(posting, dh_o):
    """(target, walk-away) all-in rates for a load, from the engine settings, rounded up to $25."""
    engine = CompanySettings.load()
    miles = posting.trip_miles + (dh_o or 0)
    target = Decimal(math.ceil((engine.cost_per_mile + engine.target_profit_per_mile) * miles / 25) * 25)
    walk_away = Decimal(math.ceil(engine.cost_per_mile * miles / 25) * 25)
    return target, walk_away


def _send(user, posting, to_email, subject, body, ai_written):
    """Send one email to a broker and record it in the Mailbox."""
    log = EmailMessage(
        user=user, broker=posting.broker if posting else None, posting=posting,
        to_email=to_email, subject=subject, body=body, ai_written=ai_written,
    )
    try:
        OutgoingEmail(
            subject=subject, body=body, from_email=settings.DEFAULT_FROM_EMAIL,
            to=[to_email], reply_to=[user.email] if user.email else None,
        ).send()
    except Exception as exc:  # SMTP errors vary by provider; record them instead of crashing
        log.status = EmailMessage.Status.FAILED
        log.error = str(exc)[:250]
    log.save()
    return log


class ComposeForm(forms.Form):
    to_email = forms.EmailField(label="To")
    subject = forms.CharField(max_length=200)
    body = forms.CharField(widget=forms.Textarea(attrs={"rows": 12}))
    note = forms.CharField(
        label="Anything to add? (for Sean AI)", required=False,
        widget=forms.TextInput(attrs={"placeholder": "e.g. truck is empty now, can pick up early"}),
    )


@login_required
def compose_email(request, pk):
    _require_dispatcher(request.user)
    posting = get_object_or_404(LoadPosting.objects.select_related("broker"), pk=pk)
    dh_o = _int_or_none(request.GET.get("dh_o") or request.POST.get("dh_o"))
    target, _ = rate_targets(posting, dh_o)
    ai_written = request.POST.get("ai_written") == "1"

    if request.method == "POST" and request.POST.get("action") == "ai":
        form = ComposeForm(request.POST)
        form.is_valid()
        draft = ai.draft_email(posting, request.user, dh_o, target, note=form.cleaned_data.get("note", ""))
        if not draft.ai_used:
            messages.warning(request, "Sean AI is not connected (no API key), so this is the standard template.")
        data = {**form.cleaned_data, "to_email": request.POST.get("to_email", ""), "subject": draft.subject, "body": draft.body}
        form = ComposeForm(initial=data)
        ai_written = draft.ai_used
    elif request.method == "POST":
        form = ComposeForm(request.POST)
        if form.is_valid():
            log = _send(request.user, posting, form.cleaned_data["to_email"], form.cleaned_data["subject"],
                        form.cleaned_data["body"], ai_written)
            if log.status == EmailMessage.Status.SENT:
                messages.success(request, f"Email sent to {log.to_email}.")
            else:
                messages.error(request, f"Email could not be sent: {log.error}")
            return redirect("mailbox")
    else:
        draft = ai.template_email(posting, request.user, dh_o, target)
        form = ComposeForm(initial={"to_email": posting.contact_email, "subject": draft.subject, "body": draft.body})

    return render(request, "copilot/compose.html", {
        "form": form, "posting": posting, "dh_o": dh_o, "target": target,
        "profile_incomplete": not (request.user.company_name and request.user.mc_number),
        "ai_available": ai.ai_available(), "ai_written": ai_written,
    })


BULK_TEMPLATE = (
    "Hello,\n\n"
    "I have a {equipment} available for your load {lane}{ref}, picking up {pickup}. {truck}\n"
    "Could you do {target} all-in? Please send the rate con if it works.\n\n"
    "Thank you,\n{signature}"
)


def _bulk_items(request):
    """Selected loads from the search page: values look like "<posting id>:<DH-O>"."""
    items = []
    for value in request.POST.getlist("pick")[:BULK_LIMIT]:
        pk, _, dh = value.partition(":")
        posting = LoadPosting.objects.filter(pk=_int_or_none(pk)).select_related("broker").first()
        if posting:
            items.append((posting, _int_or_none(dh) or 0))
    return items


def _fill(template, posting, dh_o, target, user):
    ref = f" (ref {posting.reference})" if posting.reference else ""
    values = {
        "lane": f"{posting.origin_label} to {posting.destination_label}", "pickup": f"{posting.pickup_date:%a %b %d}",
        "equipment": posting.get_equipment_display().lower(), "dh_o": dh_o, "target": f"${target:,.0f}",
        "ref": ref, "truck": ai.truck_location(posting, dh_o), "rate": f"${posting.rate:,.0f}" if posting.rate else "open", "broker": posting.company_name,
        "signature": ai.signature(ai.load_facts(posting, user)),
    }
    try:
        return template.format(**values)
    except (KeyError, IndexError, ValueError):
        return None


@require_POST
@login_required
def bulk_email(request):
    _require_dispatcher(request.user)
    items = _bulk_items(request)
    if not items:
        messages.error(request, "Tick at least one load in the search results first.")
        return redirect("load_search")

    template = request.POST.get("template") or BULK_TEMPLATE
    rows = []
    for posting, dh_o in items:
        target, _ = rate_targets(posting, dh_o)
        rows.append({"posting": posting, "dh_o": dh_o, "target": target,
                     "subject": f"{posting.origin_label} → {posting.destination_label} {posting.pickup_date:%m/%d} – truck available",
                     "body": _fill(template, posting, dh_o, target, request.user)})

    if any(row["body"] is None for row in rows):
        messages.error(request, "The template has an unknown {placeholder}. Use only the ones listed.")
    elif request.POST.get("action") == "send":
        sent = failed = 0
        for row in rows:
            if not row["posting"].contact_email:
                continue
            log = _send(request.user, row["posting"], row["posting"].contact_email, row["subject"], row["body"], False)
            sent += log.status == EmailMessage.Status.SENT
            failed += log.status == EmailMessage.Status.FAILED
        messages.success(request, f"Sent {sent} email{'s' if sent != 1 else ''}." + (f" {failed} failed." if failed else ""))
        return redirect("mailbox")

    return render(request, "copilot/bulk.html", {
        "rows": rows, "template": template,
        "with_email": sum(1 for r in rows if r["posting"].contact_email),
    })


@login_required
def mailbox(request):
    _require_dispatcher(request.user)
    emails = EmailMessage.objects.filter(user=request.user).select_related("broker", "posting")
    page = Paginator(emails, 25).get_page(request.GET.get("page"))
    console = settings.EMAIL_BACKEND.endswith("console.EmailBackend")
    return render(request, "copilot/mailbox.html", {"page": page, "console_mode": console})


class CallLogForm(forms.ModelForm):
    class Meta:
        model = CallLog
        fields = ("outcome", "rate_quoted", "notes")
        widgets = {"notes": forms.Textarea(attrs={"rows": 2})}


@login_required
def call_assistant(request, pk):
    _require_dispatcher(request.user)
    posting = get_object_or_404(LoadPosting.objects.select_related("broker"), pk=pk)
    dh_o = _int_or_none(request.GET.get("dh_o") or request.POST.get("dh_o"))
    target, walk_away = rate_targets(posting, dh_o)

    if request.method == "POST" and request.POST.get("action") == "log":
        form = CallLogForm(request.POST)
        if form.is_valid():
            call = form.save(commit=False)
            call.user, call.posting, call.broker = request.user, posting, posting.broker
            call.phone = posting.contact_phone
            call.save()
            messages.success(request, f"Call logged: {call.get_outcome_display()}.")
            return redirect(f"{request.path}?dh_o={dh_o or 0}")
    else:
        form = CallLogForm()

    if request.method == "POST" and request.POST.get("action") == "ai":
        script = ai.draft_call_script(posting, request.user, dh_o, target, walk_away)
        if not script.ai_used:
            messages.warning(request, "Sean AI is not connected (no API key), so this is the standard script.")
    else:
        script = ai.template_call_script(posting, request.user, dh_o, target, walk_away)

    calls = posting.calls.filter(user=request.user)
    last_rate = calls.exclude(rate_quoted=None).values_list("rate_quoted", flat=True).first()
    return render(request, "copilot/call.html", {
        "posting": posting, "dh_o": dh_o, "target": target, "walk_away": walk_away,
        "script": script, "form": form, "calls": calls, "book_rate": last_rate or posting.rate,
        "ai_available": ai.ai_available(),
    })


@login_required
def call_log(request):
    _require_dispatcher(request.user)
    calls = CallLog.objects.filter(user=request.user).select_related("broker", "posting")
    page = Paginator(calls, 25).get_page(request.GET.get("page"))
    return render(request, "copilot/calls.html", {"page": page})


# --- Broker directory ------------------------------------------------------------

def _posting_stats():
    return {
        "posted": Count("postings", distinct=True),
        "open_loads": Count("postings", filter=Q(postings__status=LoadPosting.Status.OPEN), distinct=True),
        "avg_rpm": Avg(Cast("postings__rate", FloatField()) / F("postings__trip_miles")),
        "last_post": Max("postings__posted_at"),
    }


@login_required
def broker_directory(request):
    if not request.user.can_use_tms:
        raise PermissionDenied
    brokers = Broker.objects.annotate(**_posting_stats())
    query = request.GET.get("q", "").strip()
    if query:
        brokers = brokers.filter(Q(name__icontains=query) | Q(mc_number__icontains=query) | Q(city__icontains=query))
    state = request.GET.get("state", "")
    if state:
        # Exists, not a join: a join here would multiply the posting stats above.
        posts_from_state = LoadPosting.objects.filter(broker=OuterRef("pk"), origin_state=state)
        brokers = brokers.filter(Q(state=state) | Exists(posts_from_state))
    if request.GET.get("open"):
        brokers = brokers.filter(open_loads__gt=0)
    sort = request.GET.get("sort", "posted")
    order = {"posted": ["-posted", "name"], "rate": [F("avg_rpm").desc(nulls_last=True), "name"],
             "recent": [F("last_post").desc(nulls_last=True)], "name": ["name"]}.get(sort, ["-posted", "name"])
    page = Paginator(brokers.order_by(*order), 25).get_page(request.GET.get("page"))
    return render(request, "copilot/brokers.html", {
        "page": page, "query": query, "state": state, "sort": sort, "open": request.GET.get("open", ""),
        "states": US_STATES, "total": page.paginator.count,
    })


@login_required
def broker_detail(request, pk):
    if not request.user.can_use_tms:
        raise PermissionDenied
    broker = get_object_or_404(Broker.objects.annotate(**_posting_stats()), pk=pk)
    lanes = (
        broker.postings.values("origin_state", "destination_state")
        .annotate(n=Count("id"), avg=Avg(Cast("rate", FloatField()) / F("trip_miles")))
        .order_by("-n")[:8]
    )
    return render(request, "copilot/broker_detail.html", {
        "broker": broker,
        "lanes": lanes,
        "open_postings": broker.postings.filter(status=LoadPosting.Status.OPEN).order_by("pickup_date")[:20],
        "booked": broker.loads.order_by("-pickup_at")[:10],
        "emails": broker.emails.filter(user=request.user)[:10],
        "calls": broker.calls.filter(user=request.user)[:10],
    })


@login_required
def profile(request):
    form = ProfileForm(request.POST or None, instance=request.user)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Profile saved. Sean AI uses it in your emails and call scripts.")
        return redirect("profile")
    return render(request, "form.html", {"form": form, "title": "My profile"})
