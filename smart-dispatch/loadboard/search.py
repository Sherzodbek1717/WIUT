"""Load and truck search: radius filters on origin/destination, plus the decision engine on each result."""

from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal

from django.db.models import Avg, Count, F, FloatField
from django.db.models.functions import Cast
from django.utils import timezone

from engine.core import LoadOffer, evaluate

from . import geo
from .models import Equipment, LoadPosting, TruckPosting


@dataclass
class LoadResult:
    posting: LoadPosting
    dh_o: int
    dh_d: int | None
    verdict: object  # engine.core.EngineResult, or None when there is no posted rate

    @property
    def rate_per_mile(self):
        return self.posting.rate_per_mile

    @property
    def real_rate_per_mile(self):
        return self.verdict.real_rate_per_mile if self.verdict else None


@dataclass
class TruckResult:
    posting: TruckPosting
    dh_o: int
    dh_d: int | None


def _in_box(queryset, prefix, lat, lon, radius):
    lat_min, lat_max, lon_min, lon_max = geo.bounding_box(lat, lon, radius)
    return queryset.filter(**{
        f"{prefix}_lat__gte": lat_min, f"{prefix}_lat__lte": lat_max,
        f"{prefix}_lon__gte": lon_min, f"{prefix}_lon__lte": lon_max,
    })


def search_loads(params, engine_settings):
    """Open load postings matching the search. `params` is LoadSearchForm.cleaned_data."""
    _, _, o_lat, o_lon = geo.find_city(params["origin"])
    dh_o = params.get("dh_o") if params.get("dh_o") is not None else 100
    loads = _in_box(LoadPosting.objects.filter(status=LoadPosting.Status.OPEN), "origin", o_lat, o_lon, dh_o)

    destination = geo.find_city(params.get("destination"))
    dh_d = params.get("dh_d") if params.get("dh_d") is not None else 100
    if destination:
        loads = _in_box(loads, "destination", destination[2], destination[3], dh_d)

    today = timezone.localdate()
    loads = loads.filter(pickup_date__gte=params.get("date_from") or today)
    if params.get("date_to"):
        loads = loads.filter(pickup_date__lte=params["date_to"])
    if params.get("equipment"):
        loads = loads.filter(equipment=params["equipment"])
    if params.get("load_type"):
        loads = loads.filter(load_type=params["load_type"])
    if params.get("driver_type") == "solo":
        loads = loads.filter(team_required=False)
    elif params.get("driver_type") == "team":
        loads = loads.filter(team_required=True)
    if params.get("max_weight"):
        loads = loads.filter(weight_lbs__lte=params["max_weight"])
    if params.get("min_rpm"):
        loads = loads.filter(rate__isnull=False, rate__gte=params["min_rpm"] * F("trip_miles"))

    results = []
    for posting in loads:
        deadhead = geo.road_miles(o_lat, o_lon, posting.origin_lat, posting.origin_lon)
        if deadhead > dh_o:
            continue
        deadhead_d = None
        if destination:
            deadhead_d = geo.road_miles(destination[2], destination[3], posting.destination_lat, posting.destination_lon)
            if deadhead_d > dh_d:
                continue
        verdict = None
        if posting.rate:
            verdict = evaluate(
                LoadOffer(
                    rate=posting.rate, loaded_miles=posting.trip_miles, deadhead_miles=deadhead,
                    pickup_at=posting.pickup_datetime(),
                    delivery_at=posting.delivery_datetime(engine_settings.average_speed_mph),
                ),
                engine_settings,
            )
        results.append(LoadResult(posting, deadhead, deadhead_d, verdict))
    return sort_loads(results, params.get("sort") or "age")


def sort_loads(results, sort):
    none_last = Decimal("-1")
    keys = {
        "age": (lambda r: r.posting.posted_at, True),
        "rpm": (lambda r: r.real_rate_per_mile or none_last, True),
        "rate": (lambda r: r.posting.rate or none_last, True),
        "dho": (lambda r: r.dh_o, False),
        "trip": (lambda r: r.posting.trip_miles, True),
        "pickup": (lambda r: r.posting.pickup_date, False),
    }
    key, reverse = keys.get(sort, keys["age"])
    return sorted(results, key=key, reverse=reverse)


def lane_market(params, days=30):
    """Average posted rate per mile for the searched lane (or outbound from the origin state)."""
    origin = geo.find_city(params["origin"])
    destination = geo.find_city(params.get("destination"))
    postings = LoadPosting.objects.filter(
        rate__isnull=False, origin_state=origin[1], posted_at__gte=timezone.now() - timedelta(days=days)
    )
    label = f"{origin[1]} outbound"
    if destination:
        postings = postings.filter(destination_state=destination[1])
        label = f"{origin[1]} → {destination[1]}"
    if params.get("equipment"):
        postings = postings.filter(equipment=params["equipment"])
    # Cast to float: SQLite would otherwise do integer division here.
    stats = postings.aggregate(n=Count("id"), avg=Avg(Cast("rate", FloatField()) / F("trip_miles")))
    if not stats["n"]:
        return None
    return {"label": label, "count": stats["n"], "rate_per_mile": Decimal(stats["avg"]).quantize(Decimal("0.01")), "days": days}


def search_trucks(params):
    _, _, o_lat, o_lon = geo.find_city(params["origin"])
    dh_o = params.get("dh_o") if params.get("dh_o") is not None else 150
    trucks = _in_box(TruckPosting.objects.filter(active=True), "origin", o_lat, o_lon, dh_o)

    today = timezone.localdate()
    start = params.get("date_from") or today
    end = params.get("date_to") or start
    trucks = trucks.filter(available_to__gte=start, available_from__lte=end)
    if params.get("equipment"):
        trucks = trucks.filter(equipment=params["equipment"])
    if params.get("driver_type") == "solo":
        trucks = trucks.filter(team=False)
    elif params.get("driver_type") == "team":
        trucks = trucks.filter(team=True)

    destination = geo.find_city(params.get("destination"))
    dh_d = params.get("dh_d") if params.get("dh_d") is not None else 150

    results = []
    for posting in trucks:
        deadhead = geo.road_miles(o_lat, o_lon, posting.origin_lat, posting.origin_lon)
        if deadhead > dh_o:
            continue
        deadhead_d = None
        if destination and posting.destination_lat is not None:
            deadhead_d = geo.road_miles(destination[2], destination[3], posting.destination_lat, posting.destination_lon)
            if deadhead_d > dh_d:
                continue  # truck wants to go somewhere else; "Anywhere" trucks always match
        results.append(TruckResult(posting, deadhead, deadhead_d))
    return sorted(results, key=lambda r: r.posting.posted_at, reverse=True)


def query_label(params):
    label = f"{params['origin']} → {params.get('destination') or 'Anywhere'}"
    if params.get("equipment"):
        label += f" · {Equipment(params['equipment']).label}"
    return label

