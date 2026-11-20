from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from dispatch.models import Broker, Load
from engine.models import CompanySettings

from . import geo
from .forms import BookForm, LoadPostingForm, LoadSearchForm, TruckPostingForm, TruckSearchForm
from .models import LoadPosting, RecentSearch, TruckPosting
from .search import lane_market, query_label, search_loads, search_trucks

MAX_RESULTS = 200
RECENT_LIMIT = 6


def _require(condition):
    if not condition:
        raise PermissionDenied


def _remember(user, kind, form):
    query = urlencode({k: v for k, v in form.data.items() if v and k != "page"})
    RecentSearch.objects.update_or_create(
        user=user, kind=kind, query=query, defaults={"label": query_label(form.cleaned_data)}
    )
    stale = RecentSearch.objects.filter(user=user, kind=kind).values_list("pk", flat=True)[RECENT_LIMIT:]
    RecentSearch.objects.filter(pk__in=list(stale)).delete()


def _base_context(kind, form):
    return {
        "form": form,
        "city_labels": geo.CITY_LABELS,
        "recent": None,
        "kind": kind,
    }


@login_required
def load_search(request):
    _require(not request.user.is_broker)
    form = LoadSearchForm(request.GET or None, initial={"dh_o": 100, "dh_d": 100})
    context = _base_context("loads", form)
    if not request.GET:
        context["recent"] = request.user.recent_searches.filter(kind="loads")
        return render(request, "loadboard/load_search.html", context)

    if form.is_valid():
        settings = CompanySettings.load()
        results = search_loads(form.cleaned_data, settings.to_engine_settings())
        _remember(request.user, "loads", form)
        context.update(
            results=results[:MAX_RESULTS],
            total=len(results),
            market=lane_market(form.cleaned_data),
            target_rpm=settings.cost_per_mile + settings.target_profit_per_mile,
            can_book=request.user.can_edit_operations,
            searched=True,
        )
    return render(request, "loadboard/load_search.html", context)


@login_required
def truck_search(request):
    form = TruckSearchForm(request.GET or None, initial={"dh_o": 150, "dh_d": 150})
    context = _base_context("trucks", form)
    if not request.GET:
        context["recent"] = request.user.recent_searches.filter(kind="trucks")
        return render(request, "loadboard/truck_search.html", context)
    if form.is_valid():
        results = search_trucks(form.cleaned_data)
        _remember(request.user, "trucks", form)
        context.update(results=results[:MAX_RESULTS], total=len(results), searched=True)
    return render(request, "loadboard/truck_search.html", context)


@require_POST
@login_required
def book_load(request, pk):
    """Book a marketplace load: it becomes a Load in the carrier's TMS, ready to assign."""
    _require(request.user.can_edit_operations)
    form = BookForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Enter the agreed rate to book this load.")
        back = request.META.get("HTTP_REFERER", "")
        if url_has_allowed_host_and_scheme(back, allowed_hosts={request.get_host()}):
            return redirect(back)
        return redirect("load_search")

    with transaction.atomic():
        posting = get_object_or_404(LoadPosting.objects.select_for_update(), pk=pk)
        if posting.status != LoadPosting.Status.OPEN:
            messages.error(request, "Sorry, this load has already been booked or removed.")
            return redirect("load_search")
        broker, _ = Broker.objects.get_or_create(
            name=posting.company_name,
            defaults={"contact_phone": posting.contact_phone, "contact_email": posting.contact_email},
        )
        settings = CompanySettings.load()
        load = Load.objects.create(
            reference=posting.reference,
            broker=broker,
            origin_city=posting.origin_city, origin_state=posting.origin_state,
            destination_city=posting.destination_city, destination_state=posting.destination_state,
            pickup_at=posting.pickup_datetime(),
            delivery_at=posting.delivery_datetime(settings.average_speed_mph),
            rate=form.cleaned_data["rate"],
            loaded_miles=posting.trip_miles,
            deadhead_miles=form.cleaned_data.get("dh_o") or 0,
            commodity=posting.commodity,
            weight_lbs=posting.weight_lbs,
            created_by=request.user,
        )
        posting.status = LoadPosting.Status.BOOKED
        posting.booked_by = request.user
        posting.booked_load = load
        posting.save(update_fields=["status", "booked_by", "booked_load"])

    messages.success(request, "Load booked! Assign a driver and truck to dispatch it.")
    return redirect(load)


# --- Broker side: my load postings ---------------------------------------------

@login_required
def my_loads(request):
    _require(request.user.can_post_loads)
    postings = LoadPosting.objects.filter(posted_by=request.user).select_related("booked_by")
    return render(request, "loadboard/my_loads.html", {"postings": postings, "today": timezone.localdate()})


@login_required
def post_load(request, pk=None):
    _require(request.user.can_post_loads)
    posting = get_object_or_404(LoadPosting, pk=pk, posted_by=request.user) if pk else None
    if posting and posting.status != LoadPosting.Status.OPEN:
        messages.error(request, "Booked or cancelled loads cannot be edited.")
        return redirect("my_loads")
    initial = {"contact_phone": request.user.phone, "contact_email": request.user.email}
    form = LoadPostingForm(request.POST or None, instance=posting, initial=initial)
    if request.method == "POST" and form.is_valid():
        new = form.save(commit=False)
        if not posting:
            new.posted_by = request.user
            new.company_name = request.user.company_name or str(request.user)
        new.save()
        messages.success(request, "Load posted to the marketplace." if not posting else "Load updated.")
        return redirect("my_loads")
    return render(request, "loadboard/posting_form.html", {
        "form": form, "city_labels": geo.CITY_LABELS,
        "title": "Edit load" if posting else "Post a load",
    })


@require_POST
@login_required
def cancel_load(request, pk):
    _require(request.user.can_post_loads)
    posting = get_object_or_404(LoadPosting, pk=pk, posted_by=request.user, status=LoadPosting.Status.OPEN)
    posting.status = LoadPosting.Status.CANCELLED
    posting.save(update_fields=["status"])
    messages.success(request, "Load removed from the marketplace.")
    return redirect("my_loads")


# --- Carrier side: my truck postings ---------------------------------------------

@login_required
def my_trucks(request):
    _require(request.user.can_edit_operations)
    postings = TruckPosting.objects.filter(posted_by=request.user).select_related("truck")
    return render(request, "loadboard/my_trucks.html", {"postings": postings, "today": timezone.localdate()})


@login_required
def post_truck(request, pk=None):
    _require(request.user.can_edit_operations)
    posting = get_object_or_404(TruckPosting, pk=pk, posted_by=request.user) if pk else None
    initial = {
        "contact_phone": request.user.phone, "contact_email": request.user.email,
        "available_from": timezone.localdate(), "available_to": timezone.localdate(),
    }
    form = TruckPostingForm(request.POST or None, instance=posting, initial=initial)
    if request.method == "POST" and form.is_valid():
        new = form.save(commit=False)
        if not posting:
            new.posted_by = request.user
            new.company_name = request.user.company_name or str(request.user)
        new.active = True
        new.save()
        messages.success(request, "Truck posted. Brokers can now find it." if not posting else "Truck post updated.")
        return redirect("my_trucks")
    return render(request, "loadboard/posting_form.html", {
        "form": form, "city_labels": geo.CITY_LABELS,
        "title": "Edit truck post" if posting else "Post a truck",
    })


@require_POST
@login_required
def remove_truck(request, pk):
    _require(request.user.can_edit_operations)
    posting = get_object_or_404(TruckPosting, pk=pk, posted_by=request.user)
    posting.active = False
    posting.save(update_fields=["active"])
    messages.success(request, "Truck post removed.")
    return redirect("my_trucks")
