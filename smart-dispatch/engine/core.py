"""Load decision and profitability engine.

Pure Python with no Django imports, so the business rules can be unit tested
on their own (the business-logic layer in the PID's architecture).

Hours-of-service (HOS) rules are a simplified version of the FMCSA limits for
property-carrying drivers: at most 11 hours driving per shift, a 30-minute
break after 8 hours of driving, 10 hours off duty between shifts, and a
70-hour on-duty cycle. The 14-hour window, split sleeper berth and the
34-hour restart are not modelled.
"""

import math
from dataclasses import dataclass, field
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal

MAX_DRIVING_PER_SHIFT = 11.0
BREAK_AFTER_DRIVING = 8.0
BREAK_LENGTH = 0.5
OFF_DUTY_BETWEEN_SHIFTS = 10.0
TIGHT_SLACK_HOURS = 2.0
COUNTER_OFFER_STEP = Decimal("25")

ACCEPT = "accept"
NEGOTIATE = "negotiate"
REJECT = "reject"

HOS_FEASIBLE = "feasible"
HOS_TIGHT = "tight"
HOS_INFEASIBLE = "infeasible"
HOS_UNKNOWN = "unknown"


@dataclass(frozen=True)
class EngineSettings:
    cost_per_mile: Decimal
    target_profit_per_mile: Decimal
    negotiate_band_pct: Decimal
    max_deadhead_pct: Decimal
    average_speed_mph: float
    dock_hours: float

    @property
    def target_rate_per_mile(self):
        return self.cost_per_mile + self.target_profit_per_mile


@dataclass(frozen=True)
class LoadOffer:
    rate: Decimal
    loaded_miles: int
    deadhead_miles: int = 0
    pickup_at: datetime | None = None
    delivery_at: datetime | None = None
    driver_hours_available: float | None = None  # hours left in the 70-hour cycle

    @property
    def total_miles(self):
        return self.loaded_miles + self.deadhead_miles


@dataclass
class HosCheck:
    status: str
    driving_hours: float
    required_transit_hours: float
    available_window_hours: float | None
    slack_hours: float | None
    on_duty_hours: float
    cycle_ok: bool | None


@dataclass
class EngineResult:
    recommendation: str
    total_miles: int
    posted_rate_per_mile: Decimal
    real_rate_per_mile: Decimal
    estimated_cost: Decimal
    estimated_profit: Decimal
    profit_margin_pct: Decimal
    deadhead_pct: Decimal
    target_rate: Decimal
    counter_offer: Decimal | None
    hos: HosCheck
    reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def as_dict(self):
        return {
            "recommendation": self.recommendation,
            "total_miles": self.total_miles,
            "posted_rate_per_mile": str(self.posted_rate_per_mile),
            "real_rate_per_mile": str(self.real_rate_per_mile),
            "estimated_cost": str(self.estimated_cost),
            "estimated_profit": str(self.estimated_profit),
            "profit_margin_pct": str(self.profit_margin_pct),
            "deadhead_pct": str(self.deadhead_pct),
            "target_rate": str(self.target_rate),
            "counter_offer": str(self.counter_offer) if self.counter_offer is not None else None,
            "hos": {
                "status": self.hos.status,
                "driving_hours": round(self.hos.driving_hours, 1),
                "required_transit_hours": round(self.hos.required_transit_hours, 1),
                "available_window_hours": _round_or_none(self.hos.available_window_hours),
                "slack_hours": _round_or_none(self.hos.slack_hours),
                "on_duty_hours": round(self.hos.on_duty_hours, 1),
                "cycle_ok": self.hos.cycle_ok,
            },
            "reasons": self.reasons,
            "warnings": self.warnings,
        }


def _round_or_none(value):
    return None if value is None else round(value, 1)


def _money(value):
    return Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _round_up_to_step(value, step=COUNTER_OFFER_STEP):
    return Decimal(math.ceil(value / step)) * step


def minimum_transit_hours(driving_hours, dock_hours=0.0):
    """Shortest legal elapsed time to drive `driving_hours` plus loading and unloading."""
    remaining = driving_hours
    elapsed = dock_hours
    while remaining > 0:
        shift_driving = min(MAX_DRIVING_PER_SHIFT, remaining)
        elapsed += shift_driving
        if shift_driving > BREAK_AFTER_DRIVING:
            elapsed += BREAK_LENGTH
        remaining -= shift_driving
        if remaining > 0:
            elapsed += OFF_DUTY_BETWEEN_SHIFTS
    return elapsed


def check_hours_of_service(offer, settings):
    loaded_driving = offer.loaded_miles / settings.average_speed_mph
    required = minimum_transit_hours(loaded_driving, settings.dock_hours)
    on_duty = offer.total_miles / settings.average_speed_mph + settings.dock_hours

    cycle_ok = None
    if offer.driver_hours_available is not None:
        cycle_ok = on_duty <= offer.driver_hours_available

    window = slack = None
    if offer.pickup_at and offer.delivery_at:
        window = (offer.delivery_at - offer.pickup_at).total_seconds() / 3600
        slack = window - required

    if cycle_ok is False or (slack is not None and slack < 0):
        status = HOS_INFEASIBLE
    elif slack is None:
        status = HOS_UNKNOWN
    elif slack < TIGHT_SLACK_HOURS:
        status = HOS_TIGHT
    else:
        status = HOS_FEASIBLE

    return HosCheck(
        status=status,
        driving_hours=loaded_driving,
        required_transit_hours=required,
        available_window_hours=window,
        slack_hours=slack,
        on_duty_hours=on_duty,
        cycle_ok=cycle_ok,
    )


def evaluate(offer, settings):
    """Score a load offer and recommend Accept, Negotiate or Reject."""
    if offer.loaded_miles <= 0:
        raise ValueError("Loaded miles must be greater than zero.")
    if offer.rate < 0 or offer.deadhead_miles < 0:
        raise ValueError("Rate and deadhead miles cannot be negative.")

    total = offer.total_miles
    rate = Decimal(offer.rate)
    real_rpm = rate / total
    cost = settings.cost_per_mile * total
    profit = rate - cost
    target_rate = _round_up_to_step(settings.target_rate_per_mile * total)
    deadhead_pct = Decimal(offer.deadhead_miles * 100) / total
    margin = profit * 100 / rate if rate else Decimal("-100")
    hos = check_hours_of_service(offer, settings)

    reasons, warnings = [], []
    counter = None
    lowest_worth_countering = target_rate * (1 - settings.negotiate_band_pct / 100)

    if hos.status == HOS_INFEASIBLE:
        recommendation = REJECT
        if hos.cycle_ok is False:
            reasons.append(
                f"Driver needs about {hos.on_duty_hours:.1f} on-duty hours but has only "
                f"{offer.driver_hours_available:.1f} left in the 70-hour cycle."
            )
        if hos.slack_hours is not None and hos.slack_hours < 0:
            reasons.append(
                f"Legal transit needs about {hos.required_transit_hours:.1f} h but the "
                f"pickup-to-delivery window is only {hos.available_window_hours:.1f} h."
            )
    elif real_rpm >= settings.target_rate_per_mile:
        recommendation = ACCEPT
        reasons.append(
            f"Real rate ${real_rpm:.2f}/mi meets the target of "
            f"${settings.target_rate_per_mile:.2f}/mi (cost plus target profit)."
        )
    elif rate >= lowest_worth_countering:
        recommendation = NEGOTIATE
        counter = target_rate
        reasons.append(
            f"Real rate ${real_rpm:.2f}/mi is below the ${settings.target_rate_per_mile:.2f}/mi "
            f"target but close enough to counter at ${counter:,.0f}."
        )
    else:
        recommendation = REJECT
        reasons.append(
            f"Real rate ${real_rpm:.2f}/mi is more than {settings.negotiate_band_pct:.0f}% "
            f"below the ${settings.target_rate_per_mile:.2f}/mi target; the broker would need "
            f"to pay about ${target_rate:,.0f}."
        )

    if profit < 0:
        warnings.append(f"Below break-even: estimated loss of ${-profit:,.2f}.")
    if deadhead_pct > settings.max_deadhead_pct:
        warnings.append(
            f"Empty miles are {deadhead_pct:.0f}% of the trip "
            f"(limit {settings.max_deadhead_pct:.0f}%)."
        )
    if hos.status == HOS_TIGHT:
        warnings.append(f"Only {hos.slack_hours:.1f} h of slack: any delay risks a late delivery.")
    if hos.status == HOS_UNKNOWN:
        warnings.append("Enter pickup and delivery times to check hours of service.")

    return EngineResult(
        recommendation=recommendation,
        total_miles=total,
        posted_rate_per_mile=_money(rate / offer.loaded_miles),
        real_rate_per_mile=_money(real_rpm),
        estimated_cost=_money(cost),
        estimated_profit=_money(profit),
        profit_margin_pct=_money(margin),
        deadhead_pct=_money(deadhead_pct),
        target_rate=target_rate,
        counter_offer=counter,
        hos=hos,
        reasons=reasons,
        warnings=warnings,
    )
