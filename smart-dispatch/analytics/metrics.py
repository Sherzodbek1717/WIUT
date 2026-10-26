"""Aggregations for the manager dashboard and reports.

Profit is estimated as revenue minus total miles times the current cost-per-mile
benchmark, matching how the decision engine scores a single load.
"""

from datetime import timedelta
from decimal import Decimal

from django.db.models import Count, F, Q, Sum
from django.db.models.functions import TruncWeek

from dispatch.models import Driver, Load

ZERO = Decimal("0")


def _miles():
    return Sum(F("loaded_miles") + F("deadhead_miles"))


def _with_rates(rows, cost_per_mile):
    for row in rows:
        revenue = row["revenue"] or ZERO
        miles = row["miles"] or 0
        row["rate_per_mile"] = (revenue / miles).quantize(Decimal("0.01")) if miles else ZERO
        row["profit"] = (revenue - cost_per_mile * miles).quantize(Decimal("0.01"))
    return rows


def loads_between(start, end):
    return Load.objects.filter(pickup_at__gte=start, pickup_at__lt=end)


def summary(loads, cost_per_mile):
    totals = loads.aggregate(
        count=Count("id"), revenue=Sum("rate"),
        loaded=Sum("loaded_miles"), deadhead=Sum("deadhead_miles"),
    )
    revenue = totals["revenue"] or ZERO
    loaded, deadhead = totals["loaded"] or 0, totals["deadhead"] or 0
    miles = loaded + deadhead
    return {
        "count": totals["count"],
        "revenue": revenue,
        "miles": miles,
        "profit": revenue - cost_per_mile * miles,
        "rate_per_mile": (revenue / miles).quantize(Decimal("0.01")) if miles else ZERO,
        "empty_mile_pct": round(deadhead * 100 / miles, 1) if miles else 0,
    }


def best_lanes(loads, cost_per_mile, limit=5, min_loads=2):
    """Lanes ranked by real rate per mile. One-off lanes are skipped when repeat lanes exist."""
    rows = list(
        loads.values("origin_state", "destination_state")
        .annotate(count=Count("id"), revenue=Sum("rate"), miles=_miles())
    )
    rows = _with_rates(rows, cost_per_mile)
    repeated = [r for r in rows if r["count"] >= min_loads]
    rows = repeated or rows
    rows.sort(key=lambda r: (r["rate_per_mile"], r["count"]), reverse=True)
    return rows[:limit]


def best_brokers(loads, cost_per_mile, limit=5):
    rows = list(
        loads.values("broker__id", "broker__name")
        .annotate(count=Count("id"), revenue=Sum("rate"), miles=_miles())
    )
    rows = _with_rates(rows, cost_per_mile)
    rows.sort(key=lambda r: (r["rate_per_mile"], r["count"]), reverse=True)
    return rows[:limit]


def weekly(loads, cost_per_mile):
    rows = list(
        loads.annotate(week=TruncWeek("pickup_at"))
        .values("week")
        .annotate(count=Count("id"), revenue=Sum("rate"), miles=_miles())
        .order_by("week")
    )
    return _with_rates(rows, cost_per_mile)


def loads_by_status(loads):
    counts = dict(loads.values_list("status").annotate(n=Count("id")))
    return [(label, counts.get(value, 0)) for value, label in Load.Status.choices]


def loads_per_driver(loads):
    return Driver.objects.annotate(
        count=Count(
            "assignments",
            filter=Q(assignments__active=True, assignments__load__in=loads),
        ),
        miles=Sum(
            F("assignments__load__loaded_miles") + F("assignments__load__deadhead_miles"),
            filter=Q(assignments__active=True, assignments__load__in=loads),
        ),
    ).order_by("-count", "first_name")


def week_bounds(monday):
    return monday, monday + timedelta(days=7)
