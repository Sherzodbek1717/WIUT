"""Telegram driver bot tests. A fake client stands in for the Telegram API."""

import shutil
import tempfile
from datetime import timedelta
from decimal import Decimal

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from dispatch.models import Broker, Driver, Load, Truck
from dispatch.services import assign_load, change_status
from telegram_bot.client import TelegramError
from telegram_bot.handlers import handle_update
from telegram_bot.notifications import notify_assignment

CHAT = 555001


class FakeClient:
    def __init__(self, file_bytes=b"fake-image"):
        self.sent, self.answers, self.file_bytes = [], [], file_bytes

    def send_message(self, chat_id, text, buttons=None):
        self.sent.append({"chat_id": chat_id, "text": text, "buttons": buttons})

    def answer_callback(self, callback_id, text=None):
        self.answers.append(text)

    def download_file(self, file_id):
        if self.file_bytes is None:
            raise TelegramError("boom")
        return self.file_bytes

    @property
    def last(self):
        return self.sent[-1]


def message(text=None, chat=CHAT, **extra):
    return {"update_id": 1, "message": {"chat": {"id": chat}, "text": text, **extra}}


def callback(data, chat=CHAT):
    return {"update_id": 2, "callback_query": {"id": "cb1", "data": data, "message": {"chat": {"id": chat}}}}


class BotTestCase(TestCase):
    def setUp(self):
        self.media = tempfile.mkdtemp()
        self.override = override_settings(MEDIA_ROOT=self.media)
        self.override.enable()
        self.client_bot = FakeClient()
        self.driver = Driver.objects.create(first_name="Test", last_name="Driver", phone="1")
        self.truck = Truck.objects.create(unit_number="101", truck_type=Truck.TruckType.DRY_VAN)
        now = timezone.now()
        self.load = Load.objects.create(
            broker=Broker.objects.create(name="Broker A"),
            origin_city="Dallas", origin_state="TX", destination_city="Atlanta", destination_state="GA",
            pickup_at=now, delivery_at=now + timedelta(days=2),
            rate=Decimal("2500"), loaded_miles=780, deadhead_miles=50, reference="RC1",
        )

    def tearDown(self):
        self.override.disable()
        shutil.rmtree(self.media, ignore_errors=True)

    def link(self):
        code = self.driver.new_telegram_link_code()
        handle_update(message(f"/start {code}"), self.client_bot)
        self.driver.refresh_from_db()


class LinkingTests(BotTestCase):
    def test_start_with_code_links_chat_and_uses_up_code(self):
        self.link()
        self.assertEqual(self.driver.telegram_chat_id, CHAT)
        self.assertIsNone(self.driver.telegram_link_code)
        self.assertIn("Linked", self.client_bot.sent[0]["text"])

    def test_wrong_code_is_refused(self):
        handle_update(message("/start NOPE"), self.client_bot)
        self.assertIn("not valid", self.client_bot.last["text"])
        self.assertFalse(Driver.objects.filter(telegram_chat_id=CHAT).exists())

    def test_unlinked_chat_is_told_how_to_link(self):
        handle_update(message("/load"), self.client_bot)
        self.assertIn("not linked", self.client_bot.last["text"])


class LoadAndStatusTests(BotTestCase):
    def setUp(self):
        super().setUp()
        self.link()
        assign_load(self.load, self.driver, self.truck)

    def test_load_command_shows_load_with_next_step_button(self):
        handle_update(message("/load"), self.client_bot)
        self.assertIn("Dallas, TX", self.client_bot.last["text"])
        self.assertEqual(self.client_bot.last["buttons"][0][1], f"status:{self.load.pk}:in_transit")

    def test_buttons_move_load_to_in_transit_then_delivered(self):
        handle_update(callback(f"status:{self.load.pk}:in_transit"), self.client_bot)
        self.load.refresh_from_db()
        self.assertEqual(self.load.status, Load.Status.IN_TRANSIT)
        handle_update(callback(f"status:{self.load.pk}:delivered"), self.client_bot)
        self.load.refresh_from_db(); self.driver.refresh_from_db()
        self.assertEqual(self.load.status, Load.Status.DELIVERED)
        self.assertEqual(self.driver.status, Driver.Status.AVAILABLE)
        self.assertIn("POD", self.client_bot.last["text"])

    def test_cannot_skip_to_delivered(self):
        handle_update(callback(f"status:{self.load.pk}:delivered"), self.client_bot)
        self.load.refresh_from_db()
        self.assertEqual(self.load.status, Load.Status.DISPATCHED)

    def test_other_chat_cannot_change_this_load(self):
        handle_update(callback(f"status:{self.load.pk}:in_transit", chat=999), self.client_bot)
        self.load.refresh_from_db()
        self.assertEqual(self.load.status, Load.Status.DISPATCHED)
        self.assertIn("no longer assigned", self.client_bot.answers[-1])


class PodTests(BotTestCase):
    def setUp(self):
        super().setUp()
        self.link()
        assign_load(self.load, self.driver, self.truck)

    def test_photo_is_saved_as_pod_on_current_load(self):
        handle_update(message(photo=[{"file_id": "small"}, {"file_id": "big"}]), self.client_bot)
        pod = self.load.pods.get()
        self.assertEqual(pod.driver, self.driver)
        self.assertEqual(pod.file.read(), b"fake-image")

    def test_pod_after_delivery_attaches_to_delivered_load(self):
        change_status(self.load, Load.Status.IN_TRANSIT)
        change_status(self.load, Load.Status.DELIVERED)
        handle_update(message(document={"file_id": "d1", "file_name": "pod.pdf"}), self.client_bot)
        self.assertEqual(self.load.pods.get().original_name, "pod.pdf")

    def test_download_failure_is_reported(self):
        self.client_bot.file_bytes = None
        with self.assertLogs("telegram_bot.handlers", "ERROR"):
            handle_update(message(photo=[{"file_id": "x"}]), self.client_bot)
        self.assertFalse(self.load.pods.exists())
        self.assertIn("could not download", self.client_bot.last["text"])

    def test_pod_visible_only_to_logged_in_users(self):
        handle_update(message(photo=[{"file_id": "x"}]), self.client_bot)
        url = reverse("pod_file", args=[self.load.pods.get().pk])
        self.assertEqual(self.client.get(url).status_code, 302)
        self.client.force_login(User.objects.create_user("m", "m@example.com", "x", role=User.Role.MANAGER))
        self.assertEqual(b"".join(self.client.get(url).streaming_content), b"fake-image")


class NotificationAndWebTests(BotTestCase):
    def test_linked_driver_is_notified_of_new_assignment(self):
        self.link()
        assignment = assign_load(self.load, self.driver, self.truck)
        self.assertTrue(notify_assignment(assignment, client=self.client_bot))
        self.assertIn("New load assigned", self.client_bot.last["text"])

    def test_no_notification_without_link_or_token(self):
        assignment = assign_load(self.load, self.driver, self.truck)
        self.assertFalse(notify_assignment(assignment, client=self.client_bot))
        self.assertFalse(notify_assignment(assignment))  # no TELEGRAM_BOT_TOKEN in tests

    @override_settings(TELEGRAM_BOT_USERNAME="demo_dispatch_bot")
    def test_dispatcher_creates_link_code_and_sees_deep_link(self):
        self.client.force_login(User.objects.create_user("d", "d@example.com", "x", role=User.Role.DISPATCHER))
        url = reverse("driver_telegram", args=[self.driver.pk])
        self.client.post(url, {"action": "code"})
        self.driver.refresh_from_db()
        self.assertContains(self.client.get(url), f"https://t.me/demo_dispatch_bot?start={self.driver.telegram_link_code}")

    def test_manager_cannot_create_link_code(self):
        self.client.force_login(User.objects.create_user("m", "m@example.com", "x", role=User.Role.MANAGER))
        response = self.client.post(reverse("driver_telegram", args=[self.driver.pk]), {"action": "code"})
        self.assertEqual(response.status_code, 403)
