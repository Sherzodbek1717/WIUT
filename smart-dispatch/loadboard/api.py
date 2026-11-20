"""Read-only JSON API (the PID's application/API layer). Uses the logged-in session, like the web pages."""

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from django.views.decorators.http import require_GET

from dispatch.models import Load
from engine.models import CompanySettings

from .forms import LoadSearchForm
from .search import lane_market, search_loads

MAX_RESULTS = 200


def _money(value):
    return None if value is None else str(value)


@require_GET
@login_required
def load_search_api(request):
    """GET /api/loadboard/search/?origin=Dallas, TX&dh_o=100&... – same filters as Search Loads."""
    if request.user.is_broker:
        raise PermissionDenied
    form = LoadSearchForm(request.GET)
    if not form.is_valid():
        return JsonResponse({"errors": form.errors}, status=400)
    results = search_loads(form.cleaned_data, CompanySettings.load().to_engine_settings())
    market = lane_market(form.cleaned_data)
    return JsonResponse({
        "count": len(results),
        "lane_rate_per_mile": _money(market["rate_per_mile"]) if market else None,
        "results": [{
            "id": r.posting.pk,
            "origin": r.posting.origin_label,
            "destination": r.posting.destination_label,
            "pickup_date": r.posting.pickup_date.isoformat(),
            "equipment": r.posting.get_equipment_display(),
            "trip_miles": r.posting.trip_miles,
            "dh_o": r.dh_o,
            "dh_d": r.dh_d,
            "weight_lbs": r.posting.weight_lbs,
            "rate": _money(r.posting.rate),
            "rate_per_mile": _money(r.rate_per_mile),
            "real_rate_per_mile": _money(r.real_rate_per_mile),
            "recommendation": r.verdict.recommendation if r.verdict else None,
            "company": r.posting.company_name,
            "contact_phone": r.posting.contact_phone,
            "contact_email": r.posting.contact_email,
        } for r in results[:MAX_RESULTS]],
    })


@require_GET
@login_required
def booked_loads_api(request):
    """GET /api/loads/?status=in_transit – the carrier's booked loads (TMS)."""
    if not request.user.can_use_tms:
        raise PermissionDenied
    loads = Load.objects.select_related("broker").prefetch_related("assignments__driver", "assignments__truck")
    status = request.GET.get("status")
    if status:
        if status not in Load.Status.values:
            return JsonResponse({"errors": {"status": [f"Use one of: {', '.join(Load.Status.values)}"]}}, status=400)
        loads = loads.filter(status=status)
    data = []
    for load in loads[:MAX_RESULTS]:
        active = next((a for a in load.assignments.all() if a.active), None)
        data.append({
            "id": load.pk, "reference": load.reference, "broker": load.broker.name,
            "origin": f"{load.origin_city}, {load.origin_state}",
            "destination": f"{load.destination_city}, {load.destination_state}",
            "pickup_at": load.pickup_at.isoformat(), "delivery_at": load.delivery_at.isoformat(),
            "rate": _money(load.rate), "loaded_miles": load.loaded_miles, "deadhead_miles": load.deadhead_miles,
            "real_rate_per_mile": _money(load.real_rate_per_mile), "status": load.status,
            "driver": str(active.driver) if active else None,
            "truck": active.truck.unit_number if active else None,
        })
    return JsonResponse({"count": len(data), "results": data})
