"""Black-box tests for the decision engine (pure Python, no database)."""

from datetime import datetime, timedelta
from decimal import Decimal
from unittest import TestCase

from engine import core

SETTINGS = core.EngineSettings(
    cost_per_mile=Decimal("2.00"),
    target_profit_per_mile=Decimal("0.50"),
    negotiate_band_pct=Decimal("15"),
    max_deadhead_pct=Decimal("20"),
    average_speed_mph=50,
    dock_hours=4,
)
PICKUP = datetime(2026, 11, 2, 8, 0)


def offer(rate, loaded, deadhead=0, hours=None, cycle=None):
    return core.LoadOffer(
        rate=Decimal(rate), loaded_miles=loaded, deadhead_miles=deadhead,
        pickup_at=PICKUP if hours else None,
        delivery_at=PICKUP + timedelta(hours=hours) if hours else None,
        driver_hours_available=cycle,
    )


class RateTests(TestCase):
    def test_real_rate_includes_empty_miles(self):
        result = core.evaluate(offer("2500", 900, 100, hours=48), SETTINGS)
        self.assertEqual(result.total_miles, 1000)
        self.assertEqual(result.posted_rate_per_mile, Decimal("2.78"))
        self.assertEqual(result.real_rate_per_mile, Decimal("2.50"))
        self.assertEqual(result.estimated_cost, Decimal("2000.00"))
        self.assertEqual(result.estimated_profit, Decimal("500.00"))
        self.assertEqual(result.deadhead_pct, Decimal("10.00"))

    def test_rejects_zero_miles(self):
        with self.assertRaises(ValueError):
            core.evaluate(offer("1000", 0), SETTINGS)


class RecommendationTests(TestCase):
    def test_accept_at_target(self):
        self.assertEqual(core.evaluate(offer("2500", 1000, hours=48), SETTINGS).recommendation, core.ACCEPT)

    def test_negotiate_within_band_with_counter_offer(self):
        result = core.evaluate(offer("2200", 1000, hours=48), SETTINGS)
        self.assertEqual(result.recommendation, core.NEGOTIATE)
        self.assertEqual(result.counter_offer, Decimal("2500"))

    def test_reject_far_below_target(self):
        result = core.evaluate(offer("1500", 1000, hours=48), SETTINGS)
        self.assertEqual(result.recommendation, core.REJECT)
        self.assertTrue(any("Below break-even" in w for w in result.warnings))

    def test_empty_miles_turn_a_good_posted_rate_into_negotiate(self):
        # $2.90 posted per loaded mile, but 300 empty miles (23%) drop it to $2.23 real.
        result = core.evaluate(offer("2900", 1000, 300, hours=48), SETTINGS)
        self.assertEqual(result.recommendation, core.NEGOTIATE)
        self.assertTrue(any("Empty miles" in w for w in result.warnings))

    def test_counter_offer_rounds_up_to_25(self):
        result = core.evaluate(offer("1000", 410, hours=24), SETTINGS)  # target 1025
        self.assertEqual(result.target_rate, Decimal("1025"))


class HoursOfServiceTests(TestCase):
    def test_single_shift_transit(self):
        # 400 mi at 50 mph = 8 h driving, no break needed, + 4 h dock.
        self.assertEqual(core.minimum_transit_hours(8, 4), 12)

    def test_multi_shift_adds_breaks_and_rest(self):
        # 22 h driving = two 11 h shifts, two 30-min breaks, one 10 h rest.
        self.assertEqual(core.minimum_transit_hours(22, 0), 33)

    def test_window_too_short_rejects_even_a_great_rate(self):
        result = core.evaluate(offer("5000", 1100, hours=24), SETTINGS)  # needs 37 h
        self.assertEqual(result.hos.status, core.HOS_INFEASIBLE)
        self.assertEqual(result.recommendation, core.REJECT)

    def test_tight_window_warns(self):
        result = core.evaluate(offer("1500", 400, hours=13), SETTINGS)  # needs 12 h
        self.assertEqual(result.hos.status, core.HOS_TIGHT)
        self.assertEqual(result.recommendation, core.ACCEPT)

    def test_not_enough_cycle_hours_rejects(self):
        result = core.evaluate(offer("3000", 1000, hours=72, cycle=10), SETTINGS)
        self.assertFalse(result.hos.cycle_ok)
        self.assertEqual(result.recommendation, core.REJECT)

    def test_unknown_without_dates(self):
        result = core.evaluate(offer("2500", 1000), SETTINGS)
        self.assertEqual(result.hos.status, core.HOS_UNKNOWN)
