from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count, F, ProtectedError, Q, Sum
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from accounts.permissions import OperationsEditMixin
from engine.core import LoadOffer, evaluate
from engine.models import CompanySettings

from .forms import AssignForm, BrokerForm, DriverForm, LoadForm, TruckForm
from .models import Broker, Driver, Load, Truck
from .services import ALLOWED_TRANSITIONS, DispatchError, assign_load, change_status


@login_required
def home(request):
    if request.user.can_view_analytics and not request.user.can_edit_operations:
        return redirect("dashboard")
    return redirect("board")


@login_required
def board(request):
    loads = Load.objects.select_related("broker").prefetch_related("assignments__driver", "assignments__truck")
    columns = []
    for status in Load.Status:
        items = loads.filter(status=status)
        if status == Load.Status.DELIVERED:
            items = items.order_by("-delivered_at")[:10]
        else:
            items = items.order_by("pickup_at")
        columns.append({"status": status, "loads": items})
    return render(request, "dispatch/board.html", {"columns": columns})


# --- Generic create / edit / delete for the simple records -------------------

class RecordFormMixin(OperationsEditMixin):
    template_name = "form.html"
    title = ""

    def get_context_data(self, **kwargs):
        return super().get_context_data(title=self.title, **kwargs)

    def form_valid(self, form):
        messages.success(self.request, f"{self.model._meta.verbose_name.capitalize()} saved.")
        return super().form_valid(form)


class RecordDeleteView(OperationsEditMixin, DeleteView):
    template_name = "confirm_delete.html"

    def form_valid(self, form):
        try:
            response = super().form_valid(form)
        except ProtectedError:
            messages.error(self.request, "This record is used by loads and cannot be deleted.")
            return redirect(self.success_url)
        messages.success(self.request, f"{self.model._meta.verbose_name.capitalize()} deleted.")
        return response


class BrokerListView(LoginRequiredMixin, ListView):
    template_name = "dispatch/broker_list.html"

    def get_queryset(self):
        return Broker.objects.annotate(
            load_count=Count("loads"),
            revenue=Sum("loads__rate"),
            miles=Sum(F("loads__loaded_miles") + F("loads__deadhead_miles")),
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        for broker in context["object_list"]:
            broker.avg_rate_per_mile = (
                (broker.revenue / broker.miles).quantize(Decimal("0.01")) if broker.miles else None
            )
        return context


class BrokerCreateView(RecordFormMixin, CreateView):
    model, form_class, title = Broker, BrokerForm, "New broker"


class BrokerUpdateView(RecordFormMixin, UpdateView):
    model, form_class, title = Broker, BrokerForm, "Edit broker"


class BrokerDeleteView(RecordDeleteView):
    model, success_url = Broker, reverse_lazy("broker_list")


class DriverListView(LoginRequiredMixin, ListView):
    template_name = "dispatch/driver_list.html"

    def get_queryset(self):
        return Driver.objects.annotate(
            load_count=Count("assignments", filter=Q(assignments__active=True))
        )


class DriverCreateView(RecordFormMixin, CreateView):
    model, form_class, title = Driver, DriverForm, "New driver"


class DriverUpdateView(RecordFormMixin, UpdateView):
    model, form_class, title = Driver, DriverForm, "Edit driver"


class DriverDeleteView(RecordDeleteView):
    model, success_url = Driver, reverse_lazy("driver_list")


class TruckListView(LoginRequiredMixin, ListView):
    model = Truck
    template_name = "dispatch/truck_list.html"


class TruckCreateView(RecordFormMixin, CreateView):
    model, form_class, title = Truck, TruckForm, "New truck"


class TruckUpdateView(RecordFormMixin, UpdateView):
    model, form_class, title = Truck, TruckForm, "Edit truck"


class TruckDeleteView(RecordDeleteView):
    model, success_url = Truck, reverse_lazy("truck_list")


# --- Loads -------------------------------------------------------------------

class LoadListView(LoginRequiredMixin, ListView):
    template_name = "dispatch/load_list.html"
    paginate_by = 25

    def get_queryset(self):
        loads = Load.objects.select_related("broker")
        status = self.request.GET.get("status")
        if status in Load.Status.values:
            loads = loads.filter(status=status)
        query = self.request.GET.get("q", "").strip()
        if query:
            loads = loads.filter(
                Q(reference__icontains=query) | Q(broker__name__icontains=query)
                | Q(origin_city__icontains=query) | Q(destination_city__icontains=query)
                | Q(origin_state__iexact=query) | Q(destination_state__iexact=query)
            )
        return loads

    def get_context_data(self, **kwargs):
        return super().get_context_data(
            statuses=Load.Status.choices,
            current_status=self.request.GET.get("status", ""),
            query=self.request.GET.get("q", ""),
            **kwargs,
        )


class LoadOfferMixin(OperationsEditMixin):
    """Create/edit a load. 'Evaluate' runs the decision engine without saving."""

    model = Load
    form_class = LoadForm
    template_name = "dispatch/load_form.html"

    def post(self, request, *args, **kwargs):
        if "evaluate" not in request.POST:
            return super().post(request, *args, **kwargs)
        self.object = self.get_object() if "pk" in kwargs else None
        form = self.get_form()
        result = None
        if form.is_valid():
            data = form.cleaned_data
            offer = LoadOffer(
                rate=data["rate"],
                loaded_miles=data["loaded_miles"],
                deadhead_miles=data["deadhead_miles"] or 0,
                pickup_at=data["pickup_at"],
                delivery_at=data["delivery_at"],
                driver_hours_available=data.get("driver_hours_available"),
            )
            result = evaluate(offer, CompanySettings.load().to_engine_settings())
        return self.render_to_response(self.get_context_data(form=form, result=result))

    def form_valid(self, form):
        if form.instance.created_by_id is None:
            form.instance.created_by = self.request.user
        messages.success(self.request, "Load saved.")
        return super().form_valid(form)


class LoadCreateView(LoadOfferMixin, CreateView):
    extra_context = {"title": "New load offer"}


class LoadUpdateView(LoadOfferMixin, UpdateView):
    extra_context = {"title": "Edit load"}


class LoadDeleteView(RecordDeleteView):
    model, success_url = Load, reverse_lazy("load_list")

    def form_valid(self, form):
        if self.object.status in (Load.Status.DISPATCHED, Load.Status.IN_TRANSIT):
            messages.error(self.request, "Unassign the load (set it back to Available) before deleting it.")
            return redirect(self.object)
        return super().form_valid(form)


class LoadDetailView(LoginRequiredMixin, DetailView):
    template_name = "dispatch/load_detail.html"
    queryset = Load.objects.select_related("broker", "created_by")

    def get_context_data(self, **kwargs):
        load = self.object
        return super().get_context_data(
            result=load.evaluate(),
            assignment=load.active_assignment,
            history=load.assignments.select_related("driver", "truck", "assigned_by"),
            assign_form=AssignForm(load=load) if load.status in (Load.Status.AVAILABLE, Load.Status.DISPATCHED) else None,
            next_statuses=[s for s in Load.Status if s in ALLOWED_TRANSITIONS[load.status]],
            **kwargs,
        )


@require_POST
@login_required
def load_assign(request, pk):
    if not request.user.can_edit_operations:
        return HttpResponseForbidden()
    load = get_object_or_404(Load, pk=pk)
    form = AssignForm(request.POST, load=load)
    if form.is_valid():
        try:
            assign_load(load, form.cleaned_data["driver"], form.cleaned_data["truck"], request.user)
            messages.success(request, "Load dispatched.")
        except DispatchError as exc:
            messages.error(request, str(exc))
    else:
        messages.error(request, "Choose an available driver and truck.")
    return redirect(load)


@require_POST
@login_required
def load_status(request, pk):
    if not request.user.can_edit_operations:
        return HttpResponseForbidden()
    load = get_object_or_404(Load, pk=pk)
    try:
        change_status(load, request.POST.get("status"))
        messages.success(request, "Status updated.")
    except DispatchError as exc:
        messages.error(request, str(exc))
    next_url = request.POST.get("next", "")
    if url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
        return redirect(next_url)
    return redirect(load)
