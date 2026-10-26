import secrets
from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q
from django.urls import reverse

from engine.core import LoadOffer, evaluate
from engine.models import CompanySettings

US_STATES = [
    (code, code) for code in (
        "AL AK AZ AR CA CO CT DE DC FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO "
        "MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY"
    ).split()
]


class Broker(models.Model):
    name = models.CharField(max_length=120, unique=True)
    mc_number = models.CharField("MC number", max_length=20, blank=True)
    contact_email = models.EmailField(blank=True)
    contact_phone = models.CharField(max_length=30, blank=True)

    class Meta:
        ordering = ["name"]

    def get_absolute_url(self):
        return reverse("broker_list")

    def __str__(self):
        return self.name


class Driver(models.Model):
    class Status(models.TextChoices):
        AVAILABLE = "available", "Available"
        ON_LOAD = "on_load", "On load"
        OFF_DUTY = "off_duty", "Off duty"

    first_name = models.CharField(max_length=60)
    last_name = models.CharField(max_length=60)
    phone = models.CharField(max_length=30)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.AVAILABLE)
    telegram_chat_id = models.BigIntegerField(null=True, blank=True, unique=True)
    telegram_link_code = models.CharField(max_length=12, null=True, blank=True, unique=True)

    class Meta:
        ordering = ["first_name", "last_name"]

    def get_absolute_url(self):
        return reverse("driver_list")

    @property
    def telegram_linked(self):
        return self.telegram_chat_id is not None

    def new_telegram_link_code(self):
        """One-time code the driver sends to the bot (/start CODE) to link their chat."""
        self.telegram_link_code = secrets.token_hex(4).upper()
        self.save(update_fields=["telegram_link_code"])
        return self.telegram_link_code

    def current_load(self):
        """The load the driver is working now (dispatched or in transit), if any."""
        assignment = (
            self.assignments.filter(
                active=True, load__status__in=[Load.Status.DISPATCHED, Load.Status.IN_TRANSIT]
            )
            .select_related("load", "load__broker", "truck")
            .first()
        )
        return assignment.load if assignment else None

    def __str__(self):
        return f"{self.first_name} {self.last_name}"


class Truck(models.Model):
    class TruckType(models.TextChoices):
        DRY_VAN = "dry_van", "Dry van"
        REEFER = "reefer", "Reefer"
        FLATBED = "flatbed", "Flatbed"
        STEP_DECK = "step_deck", "Step deck"
        POWER_ONLY = "power_only", "Power only"
        BOX_TRUCK = "box_truck", "Box truck"

    class Status(models.TextChoices):
        AVAILABLE = "available", "Available"
        IN_USE = "in_use", "In use"
        MAINTENANCE = "maintenance", "Maintenance"

    unit_number = models.CharField(max_length=20, unique=True)
    truck_type = models.CharField("type", max_length=20, choices=TruckType.choices)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.AVAILABLE)

    class Meta:
        ordering = ["unit_number"]

    def get_absolute_url(self):
        return reverse("truck_list")

    def __str__(self):
        return f"Unit {self.unit_number} ({self.get_truck_type_display()})"


class Load(models.Model):
    class Status(models.TextChoices):
        AVAILABLE = "available", "Available"
        DISPATCHED = "dispatched", "Dispatched"
        IN_TRANSIT = "in_transit", "In transit"
        DELIVERED = "delivered", "Delivered"

    reference = models.CharField(
        max_length=40, blank=True, help_text="Broker's load or rate-confirmation number."
    )
    broker = models.ForeignKey(Broker, on_delete=models.PROTECT, related_name="loads")
    origin_city = models.CharField(max_length=80)
    origin_state = models.CharField(max_length=2, choices=US_STATES)
    destination_city = models.CharField(max_length=80)
    destination_state = models.CharField(max_length=2, choices=US_STATES)
    pickup_at = models.DateTimeField("pickup")
    delivery_at = models.DateTimeField("delivery")
    rate = models.DecimalField(
        max_digits=9, decimal_places=2, validators=[MinValueValidator(0)],
        help_text="Total line-haul rate in USD.",
    )
    loaded_miles = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    deadhead_miles = models.PositiveIntegerField(
        "empty (deadhead) miles", default=0,
        help_text="Empty miles from the truck's location to the pickup.",
    )
    commodity = models.CharField(max_length=80, blank=True)
    weight_lbs = models.PositiveIntegerField("weight (lbs)", null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.AVAILABLE)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    delivered_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-pickup_at"]
        constraints = [
            models.CheckConstraint(
                condition=Q(delivery_at__gt=models.F("pickup_at")),
                name="load_delivery_after_pickup",
            ),
        ]

    @property
    def total_miles(self):
        return self.loaded_miles + self.deadhead_miles

    @property
    def real_rate_per_mile(self):
        """Rate divided by all miles driven, including the empty miles to pickup."""
        return (self.rate / self.total_miles).quantize(Decimal("0.01"))

    @property
    def lane(self):
        return f"{self.origin_state} → {self.destination_state}"

    @property
    def active_assignment(self):
        return self.assignments.filter(active=True).select_related("driver", "truck").first()

    def to_offer(self, driver_hours_available=None):
        return LoadOffer(
            rate=self.rate,
            loaded_miles=self.loaded_miles,
            deadhead_miles=self.deadhead_miles,
            pickup_at=self.pickup_at,
            delivery_at=self.delivery_at,
            driver_hours_available=driver_hours_available,
        )

    def evaluate(self, company_settings=None):
        company_settings = company_settings or CompanySettings.load()
        return evaluate(self.to_offer(), company_settings.to_engine_settings())

    def get_absolute_url(self):
        return reverse("load_detail", args=[self.pk])

    def __str__(self):
        ref = self.reference or f"#{self.pk}"
        return f"{ref} {self.origin_city}, {self.origin_state} → {self.destination_city}, {self.destination_state}"


class Assignment(models.Model):
    """Links a load to one driver and one truck. Only one active assignment per load."""

    load = models.ForeignKey(Load, on_delete=models.CASCADE, related_name="assignments")
    driver = models.ForeignKey(Driver, on_delete=models.PROTECT, related_name="assignments")
    truck = models.ForeignKey(Truck, on_delete=models.PROTECT, related_name="assignments")
    assigned_at = models.DateTimeField(auto_now_add=True)
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+"
    )
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ["-assigned_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["load"], condition=Q(active=True), name="one_active_assignment_per_load"
            ),
        ]

    def __str__(self):
        return f"{self.load} → {self.driver} / {self.truck}"


class ProofOfDelivery(models.Model):
    """Signed POD photo or document, usually sent by the driver through the Telegram bot."""

    load = models.ForeignKey(Load, on_delete=models.CASCADE, related_name="pods")
    driver = models.ForeignKey(Driver, on_delete=models.SET_NULL, null=True, related_name="pods")
    file = models.FileField(upload_to="pod/%Y/%m/")
    original_name = models.CharField(max_length=200, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-uploaded_at"]
        verbose_name = "proof of delivery"
        verbose_name_plural = "proofs of delivery"

    def __str__(self):
        return f"POD for {self.load} ({self.uploaded_at:%Y-%m-%d})"
