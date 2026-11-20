"""Fill the load board with fresh, invented load and truck postings for demos.

Postings are dated from today, so run it again on the day of a demo:
    python manage.py seed_marketplace
"""

import random
from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from accounts.models import User
from loadboard import geo
from loadboard.models import Equipment, LoadPosting, LoadType, TruckPosting

DEMO_PASSWORD = "demo12345"

# Busier markets appear more often as origins, like real freight.
HUBS = {
    "Los Angeles, CA": 6, "Ontario, CA": 5, "Dallas, TX": 6, "Houston, TX": 5, "Atlanta, GA": 6,
    "Chicago, IL": 6, "Joliet, IL": 3, "Memphis, TN": 4, "Nashville, TN": 3, "Indianapolis, IN": 4,
    "Columbus, OH": 4, "Charlotte, NC": 3, "Jacksonville, FL": 3, "Laredo, TX": 4, "Phoenix, AZ": 3,
    "Denver, CO": 3, "Kansas City, MO": 3, "St. Louis, MO": 3, "Savannah, GA": 3, "Newark, NJ": 3,
    "Harrisburg, PA": 3, "Fresno, CA": 3, "Seattle, WA": 2, "Salt Lake City, UT": 2, "Minneapolis, MN": 2,
}
BASE_RATE = {  # typical posted $/loaded mile per equipment type
    Equipment.VAN: 2.05, Equipment.REEFER: 2.45, Equipment.FLATBED: 2.65,
    Equipment.STEP_DECK: 2.75, Equipment.POWER_ONLY: 1.85, Equipment.BOX_TRUCK: 2.30,
}
EQUIPMENT_WEIGHTS = [
    (Equipment.VAN, 50), (Equipment.REEFER, 22), (Equipment.FLATBED, 14),
    (Equipment.STEP_DECK, 5), (Equipment.POWER_ONLY, 6), (Equipment.BOX_TRUCK, 3),
]
COMMODITIES = {
    Equipment.VAN: ["General freight", "Paper products", "Beverages", "Consumer goods", "Auto parts"],
    Equipment.REEFER: ["Produce", "Frozen food", "Dairy", "Meat", "Beverages"],
    Equipment.FLATBED: ["Steel coils", "Lumber", "Building materials", "Pipe", "Machinery"],
    Equipment.STEP_DECK: ["Machinery", "Tractor", "Construction equipment"],
    Equipment.POWER_ONLY: ["Trailer move", "Drop trailer"],
    Equipment.BOX_TRUCK: ["Furniture", "Appliances", "Retail freight"],
}
BROKERS = [
    ("Peregrine Freight Demo", "(555) 010-2001"), ("Bluewater Logistics Demo", "(555) 010-2002"),
    ("Northstar Brokerage Demo", "(555) 010-2003"), ("Redline Transport Demo", "(555) 010-2004"),
    ("Summit Supply Chain Demo", "(555) 010-2005"), ("Lone Oak Logistics Demo", "(555) 010-2006"),
    ("Prairie Freight Demo", "(555) 010-2007"), ("Harbor Point Shipping Demo", "(555) 010-2008"),
]
CARRIERS = [
    "Max Trans Demo LLC", "Eagle Road Demo Inc", "Silk Way Demo Trucking", "Mosier Demo Transport",
    "Blue Ridge Demo Carriers", "Desert Wind Demo Freight", "Great Lakes Demo Hauling", "Pioneer Demo Lines",
]


def weighted(rng, pairs):
    values, weights = zip(*pairs)
    return rng.choices(values, weights=weights)[0]


class Command(BaseCommand):
    help = "Replace marketplace postings with fresh invented loads and trucks dated from today."

    def add_arguments(self, parser):
        parser.add_argument("--loads", type=int, default=900)
        parser.add_argument("--trucks", type=int, default=200)
        parser.add_argument("--seed", type=int, default=7)

    @transaction.atomic
    def handle(self, *args, loads=900, trucks=200, seed=7, **options):
        rng = random.Random(seed)
        brokers = []
        for i, (company, phone) in enumerate(BROKERS):
            user, created = User.objects.get_or_create(
                username="broker" if i == 0 else f"broker{i + 1}",
                defaults={"email": f"broker{i + 1}@example.com", "role": User.Role.BROKER,
                          "company_name": company, "phone": phone, "first_name": company.split()[0]},
            )
            if created:
                user.set_password(DEMO_PASSWORD)
                user.save()
            brokers.append(user)
        # Owner of the invented carriers' truck posts; it cannot log in.
        carrier_user, created = User.objects.get_or_create(
            username="demo_carriers",
            defaults={"email": "carriers@example.com", "role": User.Role.DISPATCHER, "company_name": "Demo carriers"},
        )
        if created:
            carrier_user.set_unusable_password()
            carrier_user.save()

        LoadPosting.objects.filter(status=LoadPosting.Status.OPEN).delete()
        TruckPosting.objects.filter(posted_by=carrier_user).delete()

        hubs = [(label, weight) for label, weight in HUBS.items()]
        now, today = timezone.now(), timezone.localdate()
        everywhere = geo.CITY_LABELS

        postings = []
        for _ in range(loads):
            origin = weighted(rng, hubs) if rng.random() < 0.7 else rng.choice(everywhere)
            destination = rng.choice(everywhere) if rng.random() < 0.6 else weighted(rng, hubs)
            if destination == origin:
                continue
            o, d = geo.find_city(origin), geo.find_city(destination)
            trip = max(1, geo.road_miles(o[2], o[3], d[2], d[3]))
            if trip > 2800:
                continue
            equipment = weighted(rng, EQUIPMENT_WEIGHTS)
            rpm = BASE_RATE[equipment] * rng.uniform(0.78, 1.25) + (0.9 if trip < 300 else 0.3 if trip < 600 else 0)
            rate = None if rng.random() < 0.2 else Decimal(round(rpm * trip / 25) * 25)
            pickup = today + timedelta(days=rng.choice([0, 0, 1, 1, 1, 2, 2, 3]))
            broker = rng.choice(brokers)
            partial = rng.random() < 0.15
            postings.append(LoadPosting(
                posted_by=broker, company_name=broker.company_name, contact_phone=broker.phone,
                contact_email=broker.email if rng.random() < 0.4 else "",
                reference=f"{rng.randint(1000000, 9999999)}",
                origin_city=o[0], origin_state=o[1], origin_lat=o[2], origin_lon=o[3],
                destination_city=d[0], destination_state=d[1], destination_lat=d[2], destination_lon=d[3],
                trip_miles=trip, pickup_date=pickup,
                delivery_date=pickup + timedelta(days=1 + trip // 550) if rng.random() < 0.65 else None,
                equipment=equipment, load_type=LoadType.PARTIAL if partial else LoadType.FULL,
                team_required=trip > 1500 and rng.random() < 0.3,
                length_ft=rng.choice([24, 26, 48]) if partial or equipment == Equipment.BOX_TRUCK else rng.choice([48, 53, 53, 53]),
                weight_lbs=rng.randint(4, 15) * 1000 if partial else rng.randint(18, 45) * 1000,
                rate=rate, commodity=rng.choice(COMMODITIES[equipment]),
                comments=rng.choice(["", "", "Tarps required" if equipment == Equipment.FLATBED else "", "Drop and hook", "Appointment at pickup", "Must have TWIC"]),
                posted_at=now - timedelta(minutes=rng.randint(2, 22 * 60)),
            ))
        LoadPosting.objects.bulk_create(postings)

        truck_posts = []
        for _ in range(trucks):
            origin = weighted(rng, hubs) if rng.random() < 0.6 else rng.choice(everywhere)
            o = geo.find_city(origin)
            d = geo.find_city(rng.choice(everywhere)) if rng.random() < 0.3 else None
            start = today + timedelta(days=rng.choice([0, 0, 1, 2]))
            company = rng.choice(CARRIERS)
            truck_posts.append(TruckPosting(
                posted_by=carrier_user, company_name=company,
                contact_phone=f"(555) 020-{rng.randint(1000, 9999)}",
                origin_city=o[0], origin_state=o[1], origin_lat=o[2], origin_lon=o[3],
                destination_city=d[0] if d else "", destination_state=d[1] if d else "",
                destination_lat=d[2] if d else None, destination_lon=d[3] if d else None,
                available_from=start, available_to=start + timedelta(days=rng.choice([0, 1, 1, 2])),
                equipment=weighted(rng, EQUIPMENT_WEIGHTS), team=rng.random() < 0.15,
                length_ft=53, max_weight_lbs=rng.choice([44000, 45000, 45000, 46000]),
                posted_at=now - timedelta(minutes=rng.randint(5, 20 * 60)),
            ))
        TruckPosting.objects.bulk_create(truck_posts)

        self.stdout.write(self.style.SUCCESS(
            f"Marketplace ready: {len(postings)} loads and {len(truck_posts)} trucks posted from {today:%b %d}. "
            f"Broker login: broker / {DEMO_PASSWORD}."
        ))
