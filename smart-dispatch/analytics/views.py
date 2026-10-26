from datetime import date, datetime, time, timedelta

from django.utils import timezone
from django.views.generic import TemplateView

from accounts.permissions import AnalyticsMixin
from engine.models import CompanySettings

from . import metrics

PERIODS = {"4": 4, "8": 8, "12": 12, "26": 26}


def _start_of_week(day):
    return day - timedelta(days=day.weekday())


def _aware(day):
    return timezone.make_aware(datetime.combine(day, time.min))


class DashboardView(AnalyticsMixin, TemplateView):
    template_name = "analytics/dashboard.html"

    def get_context_data(self, **kwargs):
        weeks = PERIODS.get(self.request.GET.get("weeks"), 8)
        this_monday = _start_of_week(timezone.localdate())
        start = _aware(this_monday - timedelta(weeks=weeks - 1))
        end = _aware(this_monday + timedelta(weeks=1))
        loads = metrics.loads_between(start, end)
        cpm = CompanySettings.load().cost_per_mile

        weekly = metrics.weekly(loads, cpm)
        chart = {
            "labels": [r["week"].strftime("%b %d") for r in weekly],
            "revenue": [float(r["revenue"]) for r in weekly],
            "profit": [float(r["profit"]) for r in weekly],
        }
        return super().get_context_data(
            weeks=weeks,
            periods=PERIODS.values(),
            summary=metrics.summary(loads, cpm),
            lanes=metrics.best_lanes(loads, cpm),
            brokers=metrics.best_brokers(loads, cpm),
            weekly=weekly,
            chart=chart,
            status_counts=metrics.loads_by_status(loads),
            cost_per_mile=cpm,
            **kwargs,
        )


class ReportsView(AnalyticsMixin, TemplateView):
    template_name = "analytics/reports.html"

    def get_context_data(self, **kwargs):
        week_param = self.request.GET.get("week", "")
        try:
            year, week = week_param.split("-W")
            monday = date.fromisocalendar(int(year), int(week), 1)
        except ValueError:
            monday = _start_of_week(timezone.localdate())
        start, end = metrics.week_bounds(monday)
        loads = metrics.loads_between(_aware(start), _aware(end))
        cpm = CompanySettings.load().cost_per_mile
        iso = monday.isocalendar()
        return super().get_context_data(
            week_value=f"{iso.year}-W{iso.week:02d}",
            week_start=start,
            week_end=end - timedelta(days=1),
            summary=metrics.summary(loads, cpm),
            status_counts=metrics.loads_by_status(loads),
            drivers=metrics.loads_per_driver(loads),
            loads=loads.select_related("broker").order_by("pickup_at"),
            **kwargs,
        )
