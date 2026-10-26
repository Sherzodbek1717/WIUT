import json

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.urls import reverse_lazy
from django.views.decorators.http import require_POST
from django.views.generic import UpdateView

from accounts.permissions import AdminMixin

from .core import LoadOffer, evaluate
from .models import CompanySettings


class OfferInputForm(forms.Form):
    """Validates the engine inputs sent to the JSON API."""

    rate = forms.DecimalField(min_value=0, max_digits=9, decimal_places=2)
    loaded_miles = forms.IntegerField(min_value=1)
    deadhead_miles = forms.IntegerField(min_value=0, required=False)
    pickup_at = forms.DateTimeField(required=False)
    delivery_at = forms.DateTimeField(required=False)
    driver_hours_available = forms.FloatField(min_value=0, max_value=70, required=False)


@require_POST
@login_required
def evaluate_api(request):
    """POST JSON load-offer fields, get the engine's result back as JSON."""
    try:
        payload = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"errors": {"__all__": ["Invalid JSON."]}}, status=400)

    form = OfferInputForm({k: v for k, v in payload.items() if v not in ("", None)})
    if not form.is_valid():
        return JsonResponse({"errors": form.errors}, status=400)

    data = form.cleaned_data
    offer = LoadOffer(
        rate=data["rate"],
        loaded_miles=data["loaded_miles"],
        deadhead_miles=data["deadhead_miles"] or 0,
        pickup_at=data["pickup_at"],
        delivery_at=data["delivery_at"],
        driver_hours_available=data["driver_hours_available"],
    )
    result = evaluate(offer, CompanySettings.load().to_engine_settings())
    return JsonResponse(result.as_dict())


class SettingsView(AdminMixin, UpdateView):
    model = CompanySettings
    fields = (
        "cost_per_mile", "target_profit_per_mile", "negotiate_band_pct",
        "max_deadhead_pct", "average_speed_mph", "dock_hours",
    )
    template_name = "form.html"
    success_url = reverse_lazy("engine_settings")
    extra_context = {"title": "Decision engine settings"}

    def get_object(self, queryset=None):
        return CompanySettings.load()

    def form_valid(self, form):
        messages.success(self.request, "Settings saved. New evaluations use these benchmarks.")
        return super().form_valid(form)
