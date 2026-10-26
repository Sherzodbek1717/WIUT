from decimal import Decimal

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from .core import EngineSettings


class CompanySettings(models.Model):
    """Editable benchmarks the decision engine uses. A single row (pk=1)."""

    cost_per_mile = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal("2.00"),
        validators=[MinValueValidator(Decimal("0.01"))],
        help_text="All-in operating cost per mile (fuel, driver pay, insurance, truck).",
    )
    target_profit_per_mile = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal("0.50"),
        validators=[MinValueValidator(Decimal("0"))],
        help_text="Profit per mile the company wants on top of cost.",
    )
    negotiate_band_pct = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal("15"),
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("100"))],
        help_text="How far below the target rate (%) an offer is still worth a counter-offer.",
    )
    max_deadhead_pct = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal("20"),
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("100"))],
        help_text="Empty miles above this share of the trip trigger a warning.",
    )
    average_speed_mph = models.FloatField(
        default=50, validators=[MinValueValidator(10), MaxValueValidator(75)],
        help_text="Average driving speed including traffic, used for hours-of-service checks.",
    )
    dock_hours = models.FloatField(
        default=4, validators=[MinValueValidator(0), MaxValueValidator(48)],
        help_text="Total hours for loading and unloading.",
    )

    class Meta:
        verbose_name_plural = "company settings"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def to_engine_settings(self):
        return EngineSettings(
            cost_per_mile=self.cost_per_mile,
            target_profit_per_mile=self.target_profit_per_mile,
            negotiate_band_pct=self.negotiate_band_pct,
            max_deadhead_pct=self.max_deadhead_pct,
            average_speed_mph=self.average_speed_mph,
            dock_hours=self.dock_hours,
        )

    def __str__(self):
        return "Company settings"
