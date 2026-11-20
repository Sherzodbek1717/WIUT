from datetime import datetime, time, timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone

from . import geo


class Equipment(models.TextChoices):
    VAN = "V", "Van"
    REEFER = "R", "Reefer"
    FLATBED = "F", "Flatbed"
    STEP_DECK = "SD", "Step deck"
    POWER_ONLY = "PO", "Power only"
    BOX_TRUCK = "BT", "Box truck"


class LoadType(models.TextChoices):
    FULL = "full", "Full"
    PARTIAL = "partial", "Partial"


class Place(models.Model):
    """Abstract origin/destination with coordinates, filled from the city list on save."""

    origin_city = models.CharField(max_length=80)
    origin_state = models.CharField(max_length=2)
    origin_lat = models.FloatField(editable=False)
    origin_lon = models.FloatField(editable=False)

    class Meta:
        abstract = True

    @property
    def origin_label(self):
        return f"{self.origin_city}, {self.origin_state}"

    def set_origin(self, label):
        city, state, lat, lon = geo.find_city(label)
        self.origin_city, self.origin_state, self.origin_lat, self.origin_lon = city, state, lat, lon

    def age(self):
        return timezone.now() - self.posted_at


class LoadPosting(Place):
    """A load a broker offers on the marketplace. Dispatchers search and book these."""

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        BOOKED = "booked", "Booked"
        CANCELLED = "cancelled", "Cancelled"

    posted_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="load_postings")
    company_name = models.CharField(max_length=120)
    contact_phone = models.CharField(max_length=30, blank=True)
    contact_email = models.EmailField(blank=True)
    reference = models.CharField(max_length=40, blank=True)

    destination_city = models.CharField(max_length=80)
    destination_state = models.CharField(max_length=2)
    destination_lat = models.FloatField(editable=False)
    destination_lon = models.FloatField(editable=False)
    trip_miles = models.PositiveIntegerField(editable=False)

    pickup_date = models.DateField()
    delivery_date = models.DateField(null=True, blank=True)
    equipment = models.CharField(max_length=2, choices=Equipment.choices)
    load_type = models.CharField(max_length=10, choices=LoadType.choices, default=LoadType.FULL)
    team_required = models.BooleanField(default=False)
    length_ft = models.PositiveIntegerField(default=53)
    weight_lbs = models.PositiveIntegerField()
    rate = models.DecimalField(
        max_digits=9, decimal_places=2, null=True, blank=True,
        help_text="Leave empty for “call for rate”.",
    )
    commodity = models.CharField(max_length=80, blank=True)
    comments = models.CharField(max_length=250, blank=True)

    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OPEN)
    posted_at = models.DateTimeField(default=timezone.now)
    booked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    booked_load = models.OneToOneField(
        "dispatch.Load", on_delete=models.SET_NULL, null=True, blank=True, related_name="posting"
    )

    class Meta:
        ordering = ["-posted_at"]
        indexes = [models.Index(fields=["status", "pickup_date", "equipment"])]

    @property
    def destination_label(self):
        return f"{self.destination_city}, {self.destination_state}"

    @property
    def rate_per_mile(self):
        return round(self.rate / self.trip_miles, 2) if self.rate and self.trip_miles else None

    def set_destination(self, label):
        city, state, lat, lon = geo.find_city(label)
        self.destination_city, self.destination_state = city, state
        self.destination_lat, self.destination_lon = lat, lon

    def save(self, *args, **kwargs):
        self.trip_miles = max(1, geo.road_miles(self.origin_lat, self.origin_lon, self.destination_lat, self.destination_lon))
        super().save(*args, **kwargs)

    def pickup_datetime(self):
        return timezone.make_aware(datetime.combine(self.pickup_date, time(8, 0)))

    def delivery_datetime(self, average_speed_mph=50):
        """Delivery date at 17:00, or an estimate from trip length when the broker gave none."""
        if self.delivery_date and self.delivery_date >= self.pickup_date:
            end = timezone.make_aware(datetime.combine(self.delivery_date, time(17, 0)))
            if end > self.pickup_datetime():
                return end
        days = 1 + self.trip_miles // 500
        return self.pickup_datetime() + timedelta(days=days, hours=9)

    def __str__(self):
        return f"{self.origin_label} → {self.destination_label} ({self.get_equipment_display()})"


class TruckPosting(Place):
    """A carrier's empty truck offered on the marketplace. Brokers search these."""

    posted_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="truck_postings")
    company_name = models.CharField(max_length=120)
    contact_phone = models.CharField(max_length=30, blank=True)
    contact_email = models.EmailField(blank=True)
    truck = models.ForeignKey("dispatch.Truck", on_delete=models.SET_NULL, null=True, blank=True)

    destination_city = models.CharField(max_length=80, blank=True)
    destination_state = models.CharField(max_length=2, blank=True)
    destination_lat = models.FloatField(null=True, editable=False)
    destination_lon = models.FloatField(null=True, editable=False)

    available_from = models.DateField()
    available_to = models.DateField()
    equipment = models.CharField(max_length=2, choices=Equipment.choices)
    load_type = models.CharField(max_length=10, choices=LoadType.choices, default=LoadType.FULL)
    team = models.BooleanField(default=False)
    length_ft = models.PositiveIntegerField(default=53)
    max_weight_lbs = models.PositiveIntegerField(default=45000)
    comments = models.CharField(max_length=250, blank=True)
    active = models.BooleanField(default=True)
    posted_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-posted_at"]

    @property
    def destination_label(self):
        return f"{self.destination_city}, {self.destination_state}" if self.destination_city else "Anywhere"

    def set_destination(self, label):
        found = geo.find_city(label) if label else None
        if found:
            self.destination_city, self.destination_state, self.destination_lat, self.destination_lon = found
        else:
            self.destination_city = self.destination_state = ""
            self.destination_lat = self.destination_lon = None

    def __str__(self):
        return f"{self.company_name}: {self.origin_label} → {self.destination_label}"


class RecentSearch(models.Model):
    """Last few searches per user, shown on the empty search page like Neblo."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="recent_searches")
    kind = models.CharField(max_length=10, choices=[("loads", "Loads"), ("trucks", "Trucks")])
    label = models.CharField(max_length=200)
    query = models.CharField(max_length=500)
    searched_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-searched_at"]
        constraints = [models.UniqueConstraint(fields=["user", "kind", "query"], name="unique_recent_search")]
