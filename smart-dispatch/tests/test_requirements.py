"""One black-box test per PID functional requirement (FR1-FR10), named after the requirement.

These drive the system only through its web pages, the way a user would, and are the
evidence listed in docs/testing.md.
"""

from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from dispatch.models import Broker, Driver, Load, Truck


def make_user(role, username=None):
    return User.objects.create_user(username or role, f"{username or role}@example.com", "Str0ng-pass-123", role=role)


class RequirementTests(TestCase):
    def setUp(self):
        self.dispatcher = make_user(User.Role.DISPATCHER)
        self.broker = Broker.objects.create(name="Acme Freight")
        now = timezone.now()
        self.load = Load.objects.create(
            broker=self.broker, origin_city="Dallas", origin_state="TX", destination_city="Atlanta",
            destination_state="GA", pickup_at=now, delivery_at=now + timedelta(days=2),
            rate=Decimal("2500"), loaded_miles=780, deadhead_miles=20,
        )

    def load_data(self, **changes):
        data = {
            "broker": self.broker.pk, "origin_city": "Dallas", "origin_state": "TX",
            "destination_city": "Memphis", "destination_state": "TN",
            "pickup_at": "2026-12-01T08:00", "delivery_at": "2026-12-02T08:00",
            "rate": "1300", "loaded_miles": "450", "deadhead_miles": "30",
        }
        data.update(changes)
        return data

    def test_fr1_register_and_log_in_securely(self):
        self.client.post(reverse("register"), {
            "role": "dispatcher", "username": "newuser", "email": "new@example.com",
            "password1": "Str0ng-pass-123", "password2": "Str0ng-pass-123",
        })
        self.client.logout()
        self.assertFalse(self.client.login(username="newuser", password="wrong-password"))
        response = self.client.post(reverse("login"), {"username": "newuser", "password": "Str0ng-pass-123"})
        self.assertRedirects(response, reverse("home"), fetch_redirect_response=False)
        self.client.logout()
        weak = self.client.post(reverse("register"), {
            "role": "dispatcher", "username": "weak", "email": "w@example.com", "password1": "123", "password2": "123",
        })
        self.assertFalse(User.objects.filter(username="weak").exists())
        self.assertContains(weak, "too short")

    def test_fr2_add_edit_delete_and_list_loads(self):
        self.client.force_login(self.dispatcher)
        self.client.post(reverse("load_create"), self.load_data(reference="NEW1"))
        created = Load.objects.get(reference="NEW1")
        self.client.post(reverse("load_edit", args=[created.pk]), self.load_data(reference="NEW1", rate="1450"))
        created.refresh_from_db()
        self.assertEqual(created.rate, Decimal("1450"))
        self.assertContains(self.client.get(reverse("load_list")), "NEW1")
        self.client.post(reverse("load_delete", args=[created.pk]))
        self.assertFalse(Load.objects.filter(pk=created.pk).exists())
        bad = self.client.post(reverse("load_create"), self.load_data(delivery_at="2026-11-30T08:00"))
        self.assertContains(bad, "Delivery must be after pickup")

    def test_fr3_add_edit_and_list_drivers_and_trucks(self):
        self.client.force_login(self.dispatcher)
        self.client.post(reverse("driver_create"), {"first_name": "Ali", "last_name": "Karimov", "phone": "555", "status": "available"})
        driver = Driver.objects.get(first_name="Ali")
        self.client.post(reverse("driver_edit", args=[driver.pk]), {"first_name": "Ali", "last_name": "K", "phone": "556", "status": "off_duty"})
        driver.refresh_from_db()
        self.assertEqual((driver.phone, driver.status), ("556", "off_duty"))
        self.client.post(reverse("truck_create"), {"unit_number": "900", "truck_type": "reefer", "status": "available"})
        self.assertContains(self.client.get(reverse("truck_list")), "900")
        self.assertContains(self.client.get(reverse("driver_list")), "Ali K")

    def test_fr4_assign_load_to_driver_and_truck(self):
        driver = Driver.objects.create(first_name="Ali", last_name="K", phone="1")
        truck = Truck.objects.create(unit_number="101", truck_type="dry_van")
        self.client.force_login(self.dispatcher)
        self.client.post(reverse("load_assign", args=[self.load.pk]), {"driver": driver.pk, "truck": truck.pk})
        self.load.refresh_from_db()
        self.assertEqual(self.load.status, Load.Status.DISPATCHED)
        self.assertEqual(self.load.active_assignment.driver, driver)

    def test_fr5_update_load_status(self):
        driver = Driver.objects.create(first_name="Ali", last_name="K", phone="1")
        truck = Truck.objects.create(unit_number="101", truck_type="dry_van")
        self.client.force_login(self.dispatcher)
        self.client.post(reverse("load_assign", args=[self.load.pk]), {"driver": driver.pk, "truck": truck.pk})
        for status in ("in_transit", "delivered"):
            self.client.post(reverse("load_status", args=[self.load.pk]), {"status": status})
        self.load.refresh_from_db()
        self.assertEqual(self.load.status, Load.Status.DELIVERED)
        driver.refresh_from_db()
        self.assertEqual(driver.status, Driver.Status.AVAILABLE)

    def test_fr6_load_offer_gives_profit_and_recommendation(self):
        self.client.force_login(self.dispatcher)
        response = self.client.post(reverse("load_create"), self.load_data(rate="2000", evaluate="1"))
        result = response.context["result"]
        self.assertEqual(result.total_miles, 480)
        self.assertEqual(result.real_rate_per_mile, Decimal("4.17"))
        self.assertEqual(result.estimated_profit, Decimal("1040.00"))  # 2000 - 480 x $2.00
        self.assertEqual(result.recommendation, "accept")
        self.assertContains(response, "ACCEPT".lower())

    def test_fr7_status_board_shows_loads_by_stage(self):
        self.client.force_login(self.dispatcher)
        response = self.client.get(reverse("board"))
        columns = {c["status"].label: list(c["loads"]) for c in response.context["columns"]}
        self.assertEqual(list(columns), ["Available", "Dispatched", "In transit", "Delivered"])
        self.assertEqual(columns["Available"], [self.load])

    def test_fr8_manager_dashboard_lanes_brokers_profit(self):
        self.client.force_login(make_user(User.Role.MANAGER))
        response = self.client.get(reverse("dashboard"), {"weeks": 4})
        summary = response.context["summary"]
        self.assertEqual(summary["count"], 1)
        self.assertEqual(summary["revenue"], Decimal("2500"))
        self.assertEqual(summary["profit"], Decimal("2500") - Decimal("2.00") * 800)
        self.assertEqual(summary["empty_mile_pct"], 2.5)  # 20 of 800 miles
        self.assertEqual(response.context["brokers"][0]["broker__name"], "Acme Freight")
        self.assertEqual(response.context["lanes"][0]["origin_state"], "TX")
        self.assertEqual(sum(response.context["chart"]["revenue"]), 2500.0)

    def test_fr9_manager_reports_by_status_and_driver(self):
        driver = Driver.objects.create(first_name="Ali", last_name="K", phone="1")
        truck = Truck.objects.create(unit_number="101", truck_type="dry_van")
        self.client.force_login(self.dispatcher)
        self.client.post(reverse("load_assign", args=[self.load.pk]), {"driver": driver.pk, "truck": truck.pk})
        self.client.force_login(make_user(User.Role.MANAGER))
        iso = timezone.localdate().isocalendar()
        response = self.client.get(reverse("reports"), {"week": f"{iso.year}-W{iso.week:02d}"})
        self.assertIn(("Dispatched", 1), response.context["status_counts"])
        per_driver = {str(d): (d.count, d.miles) for d in response.context["drivers"]}
        self.assertEqual(per_driver["Ali K"], (1, 800))
        self.assertEqual(response.context["summary"]["miles"], 800)

    def test_fr10_admin_manages_user_accounts(self):
        target = make_user(User.Role.DISPATCHER, "staff1")
        self.client.force_login(make_user(User.Role.ADMIN))
        self.assertContains(self.client.get(reverse("user_list")), "staff1")
        self.client.post(reverse("user_edit", args=[target.pk]), {
            "first_name": "", "last_name": "", "email": "staff1@example.com", "company_name": "", "mc_number": "",
            "phone": "", "role": "manager", "is_active": "",
        })
        target.refresh_from_db()
        self.assertEqual((target.role, target.is_active), ("manager", False))
        self.client.force_login(self.dispatcher)
        self.assertEqual(self.client.get(reverse("user_list")).status_code, 403)
