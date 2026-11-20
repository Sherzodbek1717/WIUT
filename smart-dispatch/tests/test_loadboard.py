"""Load board tests: distances, load and truck search, booking and posting."""

from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from dispatch.models import Load
from engine.models import CompanySettings
from loadboard import geo
from loadboard.models import Equipment, LoadPosting, RecentSearch, TruckPosting
from loadboard.search import search_loads, search_trucks


def user(role, username=None, company=""):
    username = username or role
    return User.objects.create_user(username, f"{username}@example.com", "x", role=role, company_name=company)


def post_load(broker, origin, destination, rate="2000", days=0, equipment=Equipment.VAN, **extra):
    posting = LoadPosting(
        posted_by=broker, company_name=broker.company_name or "Broker Co", contact_phone="555",
        pickup_date=timezone.localdate() + timedelta(days=days), equipment=equipment,
        weight_lbs=extra.pop("weight_lbs", 40000), rate=Decimal(rate) if rate else None, **extra,
    )
    posting.set_origin(origin)
    posting.set_destination(destination)
    posting.save()
    return posting


def params(**kw):
    base = {"origin": "Dallas, TX", "dh_o": 100, "destination": "", "dh_d": 100, "sort": "age"}
    base.update(kw)
    return base


class GeoTests(TestCase):
    def test_city_lookup_is_forgiving(self):
        self.assertEqual(geo.find_city("  dallas ,tx")[:2], ("Dallas", "TX"))
        self.assertIsNone(geo.find_city("Atlantis, ZZ"))
        self.assertIsNone(geo.find_city("Dallas"))

    def test_road_miles_are_realistic(self):
        dallas, houston = geo.find_city("Dallas, TX"), geo.find_city("Houston, TX")
        miles = geo.road_miles(dallas[2], dallas[3], houston[2], houston[3])
        self.assertTrue(220 < miles < 280, miles)  # real road distance is about 240 mi


class SearchTests(TestCase):
    def setUp(self):
        self.broker = user(User.Role.BROKER, company="Broker Co")
        self.engine = CompanySettings.load().to_engine_settings()
        self.near = post_load(self.broker, "Fort Worth, TX", "Atlanta, GA", rate="2400")   # ~35 mi from Dallas
        self.far = post_load(self.broker, "Houston, TX", "Atlanta, GA", rate="2400")       # ~240 mi
        self.reefer = post_load(self.broker, "Dallas, TX", "Memphis, TN", equipment=Equipment.REEFER)
        self.no_rate = post_load(self.broker, "Dallas, TX", "Chicago, IL", rate=None)

    def ids(self, results):
        return {r.posting.pk for r in results}

    def test_origin_radius(self):
        found = self.ids(search_loads(params(), self.engine))
        self.assertIn(self.near.pk, found)
        self.assertNotIn(self.far.pk, found)
        self.assertIn(self.far.pk, self.ids(search_loads(params(dh_o=300), self.engine)))

    def test_destination_and_equipment_filters(self):
        found = self.ids(search_loads(params(destination="Memphis, TN"), self.engine))
        self.assertEqual(found, {self.reefer.pk})
        found = self.ids(search_loads(params(equipment=Equipment.VAN), self.engine))
        self.assertNotIn(self.reefer.pk, found)

    def test_deadhead_and_verdict_on_results(self):
        result = next(r for r in search_loads(params(), self.engine) if r.posting == self.near)
        self.assertGreater(result.dh_o, 20)
        self.assertEqual(result.verdict.total_miles, self.near.trip_miles + result.dh_o)
        no_rate = next(r for r in search_loads(params(), self.engine) if r.posting == self.no_rate)
        self.assertIsNone(no_rate.verdict)

    def test_min_rate_per_mile_and_sorting(self):
        cheap = post_load(self.broker, "Dallas, TX", "Austin, TX", rate="300")
        found = self.ids(search_loads(params(min_rpm=Decimal("2.00")), self.engine))
        self.assertNotIn(cheap.pk, found)
        self.assertNotIn(self.no_rate.pk, found)
        by_dh = search_loads(params(sort="dho"), self.engine)
        self.assertEqual([r.dh_o for r in by_dh], sorted(r.dh_o for r in by_dh))

    def test_past_and_booked_loads_are_hidden(self):
        old = post_load(self.broker, "Dallas, TX", "Austin, TX", days=-1)
        self.near.status = LoadPosting.Status.BOOKED
        self.near.save()
        found = self.ids(search_loads(params(), self.engine))
        self.assertNotIn(old.pk, found)
        self.assertNotIn(self.near.pk, found)


class TruckSearchTests(TestCase):
    def test_finds_nearby_available_trucks(self):
        carrier = user(User.Role.DISPATCHER)
        today = timezone.localdate()

        def truck(origin, destination="", start=0, end=1):
            t = TruckPosting(posted_by=carrier, company_name="Carrier", equipment=Equipment.VAN,
                             available_from=today + timedelta(days=start), available_to=today + timedelta(days=end))
            t.set_origin(origin)
            t.set_destination(destination)
            t.save()
            return t

        anywhere = truck("Fort Worth, TX")
        to_atlanta = truck("Dallas, TX", "Atlanta, GA")
        to_seattle = truck("Dallas, TX", "Seattle, WA")
        later = truck("Dallas, TX", start=5, end=6)
        far = truck("Denver, CO")
        found = {r.posting.pk for r in search_trucks({"origin": "Dallas, TX", "dh_o": 150, "destination": "Atlanta, GA", "dh_d": 150})}
        self.assertEqual(found, {anywhere.pk, to_atlanta.pk})
        self.assertNotIn(to_seattle.pk, found)
        self.assertNotIn(later.pk, found)
        self.assertNotIn(far.pk, found)


class WebTests(TestCase):
    def setUp(self):
        self.broker = user(User.Role.BROKER, "broker", company="Broker Co")
        self.dispatcher = user(User.Role.DISPATCHER, "disp", company="My Carrier")
        self.posting = post_load(self.broker, "Dallas, TX", "Atlanta, GA", rate="2500")

    def test_search_page_shows_results_and_remembers_search(self):
        self.client.force_login(self.dispatcher)
        response = self.client.get(reverse("load_search"), {"origin": "Dallas, TX", "dh_o": 100})
        self.assertContains(response, "Atlanta, GA")
        self.assertContains(response, "Book load")
        self.assertEqual(RecentSearch.objects.get(user=self.dispatcher).label, "Dallas, TX → Anywhere")
        self.assertContains(self.client.get(reverse("load_search")), "Recent searches")

    def test_unknown_city_shows_error(self):
        self.client.force_login(self.dispatcher)
        response = self.client.get(reverse("load_search"), {"origin": "Nowhere"})
        self.assertContains(response, "Pick a city from the list")

    def test_booking_creates_tms_load_and_closes_posting(self):
        self.client.force_login(self.dispatcher)
        response = self.client.post(reverse("book_load", args=[self.posting.pk]), {"rate": "2600", "dh_o": "12"})
        load = Load.objects.get()
        self.assertRedirects(response, load.get_absolute_url())
        self.assertEqual((load.rate, load.deadhead_miles, load.broker.name), (Decimal("2600"), 12, "Broker Co"))
        self.posting.refresh_from_db()
        self.assertEqual(self.posting.status, LoadPosting.Status.BOOKED)
        self.assertEqual(self.posting.booked_load, load)
        # A second booking of the same load is refused.
        self.client.post(reverse("book_load", args=[self.posting.pk]), {"rate": "2600"})
        self.assertEqual(Load.objects.count(), 1)

    def test_broker_posts_load_and_dispatcher_cannot(self):
        data = {
            "origin": "Chicago, IL", "destination": "Columbus, OH", "pickup_date": timezone.localdate().isoformat(),
            "equipment": Equipment.VAN, "load_type": "full", "length_ft": 53, "weight_lbs": 30000, "rate": "1200",
        }
        self.client.force_login(self.broker)
        self.client.post(reverse("post_load"), data)
        posting = LoadPosting.objects.get(origin_city="Chicago")
        self.assertEqual((posting.company_name, posting.destination_state), ("Broker Co", "OH"))
        self.assertTrue(300 < posting.trip_miles < 420)
        self.client.force_login(self.dispatcher)
        self.assertEqual(self.client.get(reverse("post_load")).status_code, 403)
        self.assertEqual(self.client.post(reverse("book_load", args=[posting.pk]), {"rate": "1"}).status_code, 302)
        self.client.force_login(self.broker)
        self.assertEqual(self.client.post(reverse("book_load", args=[posting.pk]), {"rate": "1"}).status_code, 403)

    def test_dispatcher_posts_truck_and_broker_finds_it(self):
        self.client.force_login(self.dispatcher)
        today = timezone.localdate().isoformat()
        self.client.post(reverse("post_truck"), {
            "origin": "Denver, CO", "available_from": today, "available_to": today, "equipment": Equipment.VAN,
            "load_type": "full", "length_ft": 53, "max_weight_lbs": 45000,
        })
        self.client.force_login(self.broker)
        response = self.client.get(reverse("truck_search"), {"origin": "Denver, CO", "dh_o": 150})
        self.assertContains(response, "My Carrier")

    def test_home_sends_each_role_to_its_start_page(self):
        for account, target in ((self.dispatcher, "load_search"), (self.broker, "truck_search")):
            self.client.force_login(account)
            self.assertRedirects(self.client.get(reverse("home")), reverse(target), fetch_redirect_response=False)

    def test_seed_marketplace(self):
        from django.core.management import call_command
        call_command("seed_marketplace", "--loads", "50", "--trucks", "10", stdout=open("/dev/null", "w"))
        self.assertGreater(LoadPosting.objects.filter(status="open").count(), 40)
        self.assertEqual(TruckPosting.objects.filter(posted_by__username="demo_carriers").count(), 10)


class LaneMarketTests(TestCase):
    def test_lane_rate_is_not_truncated(self):
        from loadboard.search import lane_market
        broker = user(User.Role.BROKER)
        a = post_load(broker, "Dallas, TX", "Atlanta, GA", rate="2000")
        b = post_load(broker, "Dallas, TX", "Atlanta, GA", rate="2500")
        expected = (Decimal(2000) / a.trip_miles + Decimal(2500) / b.trip_miles) / 2
        market = lane_market({"origin": "Dallas, TX", "destination": "Atlanta, GA"})
        self.assertEqual(market["count"], 2)
        self.assertAlmostEqual(float(market["rate_per_mile"]), float(expected), places=2)
