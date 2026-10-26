"""Workflow and permission tests for the web application."""

import json
from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from dispatch.models import Assignment, Broker, Driver, Load, Truck
from dispatch.services import DispatchError, assign_load, change_status


def make_user(role, username=None):
    username = username or role
    return User.objects.create_user(username, f"{username}@example.com", "pass12345!", role=role)


class Fixtures(TestCase):
    def setUp(self):
        self.broker = Broker.objects.create(name="Broker A")
        self.driver = Driver.objects.create(first_name="Test", last_name="Driver", phone="1")
        self.truck = Truck.objects.create(unit_number="101", truck_type=Truck.TruckType.DRY_VAN)
        now = timezone.now()
        self.load = Load.objects.create(
            broker=self.broker, origin_city="Dallas", origin_state="TX",
            destination_city="Atlanta", destination_state="GA",
            pickup_at=now, delivery_at=now + timedelta(days=2),
            rate=Decimal("2500"), loaded_miles=780, deadhead_miles=50,
        )


class WorkflowTests(Fixtures):
    def test_assign_dispatches_load_and_marks_resources_busy(self):
        assign_load(self.load, self.driver, self.truck)
        self.load.refresh_from_db(); self.driver.refresh_from_db(); self.truck.refresh_from_db()
        self.assertEqual(self.load.status, Load.Status.DISPATCHED)
        self.assertEqual(self.driver.status, Driver.Status.ON_LOAD)
        self.assertEqual(self.truck.status, Truck.Status.IN_USE)

    def test_busy_driver_cannot_be_assigned_twice(self):
        assign_load(self.load, self.driver, self.truck)
        other = Load.objects.create(
            broker=self.broker, origin_city="A", origin_state="TX", destination_city="B",
            destination_state="GA", pickup_at=self.load.pickup_at, delivery_at=self.load.delivery_at,
            rate=1000, loaded_miles=400,
        )
        truck2 = Truck.objects.create(unit_number="102", truck_type=Truck.TruckType.REEFER)
        with self.assertRaises(DispatchError):
            assign_load(other, self.driver, truck2)

    def test_delivery_frees_driver_and_truck_and_keeps_history(self):
        assign_load(self.load, self.driver, self.truck)
        change_status(self.load, Load.Status.IN_TRANSIT)
        change_status(self.load, Load.Status.DELIVERED)
        self.load.refresh_from_db(); self.driver.refresh_from_db()
        self.assertIsNotNone(self.load.delivered_at)
        self.assertEqual(self.driver.status, Driver.Status.AVAILABLE)
        self.assertTrue(Assignment.objects.filter(load=self.load, active=True).exists())

    def test_cannot_skip_stages(self):
        with self.assertRaises(DispatchError):
            change_status(self.load, Load.Status.DELIVERED)

    def test_reassign_releases_previous_driver(self):
        assign_load(self.load, self.driver, self.truck)
        driver2 = Driver.objects.create(first_name="Second", last_name="Driver", phone="2")
        assign_load(self.load, driver2, self.truck)
        self.driver.refresh_from_db()
        self.assertEqual(self.driver.status, Driver.Status.AVAILABLE)
        self.assertEqual(self.load.assignments.filter(active=True).get().driver, driver2)


class PermissionTests(Fixtures):
    def test_anonymous_redirected_to_login(self):
        response = self.client.get(reverse("board"))
        self.assertRedirects(response, f"{reverse('login')}?next={reverse('board')}")

    def test_manager_cannot_create_loads_but_sees_dashboard(self):
        self.client.force_login(make_user(User.Role.MANAGER))
        self.assertEqual(self.client.get(reverse("load_create")).status_code, 403)
        self.assertEqual(self.client.get(reverse("dashboard")).status_code, 200)
        self.assertEqual(self.client.get(reverse("reports")).status_code, 200)

    def test_dispatcher_cannot_see_dashboard_or_users(self):
        self.client.force_login(make_user(User.Role.DISPATCHER))
        self.assertEqual(self.client.get(reverse("dashboard")).status_code, 403)
        self.assertEqual(self.client.get(reverse("user_list")).status_code, 403)

    def test_registration_creates_dispatcher(self):
        self.client.post(reverse("register"), {
            "username": "newbie", "email": "n@example.com",
            "password1": "Str0ng-pass-123", "password2": "Str0ng-pass-123",
        })
        self.assertEqual(User.objects.get(username="newbie").role, User.Role.DISPATCHER)


class PageTests(Fixtures):
    def setUp(self):
        super().setUp()
        self.client.force_login(make_user(User.Role.ADMIN))

    def test_all_pages_render(self):
        for name in ("board", "load_list", "load_create", "driver_list", "truck_list",
                     "broker_list", "dashboard", "reports", "user_list", "engine_settings"):
            self.assertEqual(self.client.get(reverse(name)).status_code, 200, name)
        self.assertContains(self.client.get(self.load.get_absolute_url()), "Decision engine")

    def test_evaluate_button_shows_result_without_saving(self):
        data = {
            "broker": self.broker.pk, "origin_city": "Dallas", "origin_state": "TX",
            "destination_city": "Memphis", "destination_state": "TN",
            "pickup_at": "2026-11-02T08:00", "delivery_at": "2026-11-03T08:00",
            "rate": "1300", "loaded_miles": "450", "deadhead_miles": "30", "evaluate": "1",
        }
        response = self.client.post(reverse("load_create"), data)
        self.assertContains(response, "ACCEPT".lower())
        self.assertEqual(Load.objects.count(), 1)
        del data["evaluate"]
        self.client.post(reverse("load_create"), data)
        self.assertEqual(Load.objects.count(), 2)

    def test_evaluate_api(self):
        response = self.client.post(
            reverse("api_evaluate"),
            json.dumps({"rate": "2200", "loaded_miles": 1000, "pickup_at": "", "delivery_at": ""}),
            content_type="application/json",
        )
        self.assertEqual(response.json()["recommendation"], "negotiate")
        bad = self.client.post(reverse("api_evaluate"), "{}", content_type="application/json")
        self.assertEqual(bad.status_code, 400)

    def test_seed_demo_and_dashboard_numbers(self):
        from django.core.management import call_command
        call_command("seed_demo", "--reset", stdout=open("/dev/null", "w"))
        response = self.client.get(reverse("dashboard") + "?weeks=12")
        self.assertGreater(response.context["summary"]["count"], 10)
        self.assertTrue(response.context["lanes"])
