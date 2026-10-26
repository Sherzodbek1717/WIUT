"""Fill the database with anonymised demo data for testing and the demo video.

Broker and driver names are invented, as the PID requires, so no real company
data appears in screenshots or the report.
"""

import random
from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from accounts.models import User
from dispatch.models import Assignment, Broker, Driver, Load, Truck
from engine.models import CompanySettings

CITIES = [
    ("Dallas", "TX"), ("Houston", "TX"), ("Atlanta", "GA"), ("Chicago", "IL"),
    ("Memphis", "TN"), ("Nashville", "TN"), ("Charlotte", "NC"), ("Jacksonville", "FL"),
    ("Phoenix", "AZ"), ("Los Angeles", "CA"), ("Indianapolis", "IN"), ("Columbus", "OH"),
    ("Kansas City", "MO"), ("Denver", "CO"), ("Laredo", "TX"), ("Savannah", "GA"),
]
COMMODITIES = ["General freight", "Paper products", "Beverages", "Auto parts", "Produce", "Building materials"]
BROKERS = ["Broker Alpha Logistics", "Broker Bravo Freight", "Broker Charlie Transport",
           "Broker Delta Brokerage", "Broker Echo Supply Chain"]
DRIVERS = [("Driver", "One"), ("Driver", "Two"), ("Driver", "Three"), ("Driver", "Four"), ("Driver", "Five")]
DEMO_PASSWORD = "demo12345"


class Command(BaseCommand):
    help = "Create demo users, brokers, drivers, trucks and about 12 weeks of loads."

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true", help="Delete existing loads, drivers, trucks and brokers first.")
        parser.add_argument("--seed", type=int, default=42)

    @transaction.atomic
    def handle(self, *args, reset=False, seed=42, **options):
        rng = random.Random(seed)
        if reset:
            Assignment.objects.all().delete()
            Load.objects.all().delete()
            Driver.objects.all().delete()
            Truck.objects.all().delete()
            Broker.objects.all().delete()

        for username, role in (("admin", User.Role.ADMIN), ("dispatcher", User.Role.DISPATCHER), ("manager", User.Role.MANAGER)):
            user, created = User.objects.get_or_create(
                username=username,
                defaults={"email": f"{username}@example.com", "role": role,
                          "first_name": username.capitalize(), "is_staff": role == User.Role.ADMIN,
                          "is_superuser": role == User.Role.ADMIN},
            )
            if created:
                user.set_password(DEMO_PASSWORD)
                user.save()
        dispatcher = User.objects.get(username="dispatcher")
        CompanySettings.load()

        brokers = [Broker.objects.get_or_create(name=name, defaults={"mc_number": f"MC{100000 + i}"})[0]
                   for i, name in enumerate(BROKERS)]
        # Each broker pays a different typical rate, so the dashboard has something to rank.
        broker_rpm = {b.pk: Decimal(str(rng.uniform(2.05, 2.95))) for b in brokers}
        drivers = [Driver.objects.get_or_create(first_name=f, last_name=l, defaults={"phone": f"+1-555-010{i}"})[0]
                   for i, (f, l) in enumerate(DRIVERS)]
        trucks = [Truck.objects.get_or_create(unit_number=f"{101 + i}", defaults={"truck_type": t})[0]
                  for i, t in enumerate([Truck.TruckType.DRY_VAN] * 3 + [Truck.TruckType.REEFER] * 2)]

        now = timezone.now()
        start = now - timedelta(weeks=12)
        count = 0
        for index, (driver, truck) in enumerate(zip(drivers, trucks)):
            pickup = start + timedelta(hours=rng.randint(0, 48) + index * 7)
            while pickup < now - timedelta(days=3):
                load = self._make_load(rng, brokers, broker_rpm, pickup, dispatcher)
                Assignment.objects.create(load=load, driver=driver, truck=truck, assigned_by=dispatcher)
                load.status = Load.Status.DELIVERED
                load.delivered_at = load.delivery_at
                load.save(update_fields=["status", "delivered_at"])
                pickup = load.delivery_at + timedelta(hours=rng.randint(10, 40))
                count += 1

        # Current work: two on the road, one dispatched, and a few open offers.
        for driver, truck, status in ((drivers[0], trucks[0], Load.Status.IN_TRANSIT),
                                      (drivers[1], trucks[1], Load.Status.IN_TRANSIT),
                                      (drivers[2], trucks[2], Load.Status.DISPATCHED)):
            load = self._make_load(rng, brokers, broker_rpm, now + timedelta(hours=rng.randint(-20, 20)), dispatcher)
            Assignment.objects.create(load=load, driver=driver, truck=truck, assigned_by=dispatcher)
            load.status = status
            load.save(update_fields=["status"])
            driver.status = Driver.Status.ON_LOAD
            driver.save(update_fields=["status"])
            truck.status = Truck.Status.IN_USE
            truck.save(update_fields=["status"])
            count += 1
        for _ in range(3):
            self._make_load(rng, brokers, broker_rpm, now + timedelta(hours=rng.randint(24, 72)), dispatcher)
            count += 1

        self.stdout.write(self.style.SUCCESS(
            f"Seeded {count} loads. Log in as admin, dispatcher or manager with password '{DEMO_PASSWORD}'."
        ))

    def _make_load(self, rng, brokers, broker_rpm, pickup, user):
        origin, destination = rng.sample(CITIES, 2)
        loaded = rng.randint(250, 1100)
        deadhead = rng.randint(0, 160)
        broker = rng.choice(brokers)
        rpm = broker_rpm[broker.pk] * Decimal(str(rng.uniform(0.85, 1.15)))
        rate = (rpm * loaded / 25).quantize(Decimal("1")) * 25
        transit_days = 1 + loaded // 500
        return Load.objects.create(
            reference=f"RC{rng.randint(100000, 999999)}",
            broker=broker,
            origin_city=origin[0], origin_state=origin[1],
            destination_city=destination[0], destination_state=destination[1],
            pickup_at=pickup,
            delivery_at=pickup + timedelta(days=transit_days, hours=rng.randint(2, 10)),
            rate=rate, loaded_miles=loaded, deadhead_miles=deadhead,
            commodity=rng.choice(COMMODITIES), weight_lbs=rng.randint(8000, 44000),
            created_by=user,
        )
