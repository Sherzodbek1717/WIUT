"""Sean AI Co-Pilot tests: AI drafting (with a fake Claude client), email, calls and the broker directory."""

from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest import mock

from django.core import mail
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from copilot import ai
from copilot.models import CallLog, EmailMessage
from dispatch.models import Broker
from loadboard.models import Equipment, LoadPosting


def make_user(role, username, **extra):
    return User.objects.create_user(username, f"{username}@example.com", "x", role=role, **extra)


def post(broker_user, origin="Dallas, TX", destination="Atlanta, GA", rate="2500", email="loads@acme.example.com", **extra):
    posting = LoadPosting(
        posted_by=broker_user, company_name=extra.pop("company", "Acme Freight"), contact_phone="(555) 010-9999",
        contact_email=email, pickup_date=timezone.localdate() + timedelta(days=1), equipment=Equipment.VAN,
        weight_lbs=40000, rate=Decimal(rate) if rate else None, reference="RC77", **extra,
    )
    posting.set_origin(origin)
    posting.set_destination(destination)
    posting.save()
    return posting


class Base(TestCase):
    def setUp(self):
        self.broker_user = make_user(User.Role.BROKER, "broker", company_name="Acme Freight")
        self.dispatcher = make_user(
            User.Role.DISPATCHER, "disp", company_name="Silk Road Trucking", mc_number="123456",
            phone="(555) 777-0000", first_name="Sean", last_name="Driver",
        )
        self.posting = post(self.broker_user)
        self.client.force_login(self.dispatcher)


class TemplateTests(Base):
    def test_email_template_has_load_facts_target_and_signature(self):
        draft = ai.template_email(self.posting, self.dispatcher, dh_o=40, target_rate=Decimal("2600"))
        self.assertFalse(draft.ai_used)
        self.assertIn("Dallas, TX → Atlanta, GA", draft.subject)
        for text in ("40 miles", "$2,600", "RC77", "MC# 123456", "Sean Driver"):
            self.assertIn(text, draft.body)

    def test_call_script_has_walk_away(self):
        script = ai.template_call_script(self.posting, self.dispatcher, 40, Decimal("2600"), Decimal("2050"))
        self.assertIn("MC 123456", script.opening)
        self.assertTrue(any("$2,050" in line for line in script.negotiation))


def fake_response(stop_reason="end_turn", text='{"subject": "S", "body": "B"}'):
    return SimpleNamespace(stop_reason=stop_reason, content=[SimpleNamespace(type="text", text=text)])


class ClaudeRequestTests(Base):
    def run_with(self, response):
        client = mock.MagicMock()
        client.beta.messages.create.return_value = response
        with mock.patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test"}), \
                mock.patch("anthropic.Anthropic", return_value=client):
            draft = ai.draft_email(self.posting, self.dispatcher, dh_o=10, target_rate=Decimal("2600"))
        return draft, client.beta.messages.create.call_args.kwargs

    def test_request_shape_and_parsed_result(self):
        draft, kwargs = self.run_with(fake_response())
        self.assertEqual((draft.subject, draft.body, draft.ai_used), ("S", "B", True))
        self.assertEqual(kwargs["model"], "claude-opus-5-5")
        self.assertEqual(kwargs["fallbacks"], "default")
        self.assertEqual(kwargs["betas"], ["server-side-fallback-2026-07-01"])
        self.assertEqual(kwargs["output_config"]["format"]["type"], "json_schema")
        self.assertIn("Dallas, TX to Atlanta, GA", kwargs["messages"][0]["content"])

    def test_refusal_or_bad_json_falls_back_to_template(self):
        for response in (fake_response(stop_reason="refusal", text=""), fake_response(text="not json")):
            with self.assertLogs("copilot.ai", "WARNING"):
                draft, _ = self.run_with(response)
            self.assertFalse(draft.ai_used)
            self.assertIn("Atlanta", draft.subject)

    def test_api_error_falls_back_to_template(self):
        import anthropic
        client = mock.MagicMock()
        client.beta.messages.create.side_effect = anthropic.APIConnectionError(request=mock.MagicMock())
        with mock.patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test"}), \
                mock.patch("anthropic.Anthropic", return_value=client), self.assertLogs("copilot.ai", "WARNING"):
            self.assertFalse(ai.draft_email(self.posting, self.dispatcher).ai_used)


class EmailTests(Base):
    def test_compose_prefills_and_sends(self):
        url = reverse("compose_email", args=[self.posting.pk])
        page = self.client.get(url, {"dh_o": 25})
        self.assertContains(page, "loads@acme.example.com")
        self.assertContains(page, "25 miles")
        response = self.client.post(url, {
            "action": "send", "dh_o": 25, "to_email": "loads@acme.example.com",
            "subject": "Truck available", "body": "Hello",
        })
        self.assertRedirects(response, reverse("mailbox"))
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].reply_to, ["disp@example.com"])
        log = EmailMessage.objects.get()
        self.assertEqual((log.status, log.broker.name), ("sent", "Acme Freight"))
        self.assertContains(self.client.get(reverse("mailbox")), "Truck available")

    def test_ai_button_without_key_uses_template_and_says_so(self):
        response = self.client.post(reverse("compose_email", args=[self.posting.pk]), {
            "action": "ai", "to_email": "loads@acme.example.com", "subject": "x", "body": "y",
        }, follow=True)
        self.assertContains(response, "not connected")
        self.assertContains(response, "Atlanta")

    def test_bulk_email_preview_then_send(self):
        phone_only = post(self.broker_user, "Dallas, TX", "Memphis, TN", email="")
        data = {"pick": [f"{self.posting.pk}:40", f"{phone_only.pk}:30"]}
        preview = self.client.post(reverse("bulk_email"), data)
        self.assertContains(preview, "phone only")
        self.assertContains(preview, "Send 1 email")
        self.client.post(reverse("bulk_email"), {**data, "action": "send"})
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("40 miles from the pickup", mail.outbox[0].body)

    def test_bulk_email_rejects_unknown_placeholder(self):
        response = self.client.post(reverse("bulk_email"), {
            "pick": [f"{self.posting.pk}:1"], "template": "Hi {nope}", "action": "send",
        })
        self.assertContains(response, "unknown {placeholder}")
        self.assertEqual(len(mail.outbox), 0)

    def test_manager_cannot_email(self):
        self.client.force_login(make_user(User.Role.MANAGER, "boss"))
        self.assertEqual(self.client.get(reverse("compose_email", args=[self.posting.pk])).status_code, 403)


class CallTests(Base):
    def test_call_assistant_shows_targets_and_logs_call(self):
        url = reverse("call_assistant", args=[self.posting.pk])
        page = self.client.get(url, {"dh_o": 0})
        self.assertContains(page, "tel:(555) 010-9999")
        self.assertContains(page, "Walk away below")
        self.client.post(url, {"action": "log", "dh_o": 0, "outcome": "quoted", "rate_quoted": "2700", "notes": "call back 3pm"})
        call = CallLog.objects.get()
        self.assertEqual((call.broker.name, call.rate_quoted), ("Acme Freight", Decimal("2700")))
        page = self.client.get(url, {"dh_o": 0})
        self.assertContains(page, 'value="2700"')  # quoted rate pre-fills the booking box
        self.assertContains(self.client.get(reverse("call_log")), "Got a rate")


class DirectoryTests(Base):
    def test_postings_create_directory_entries_with_correct_stats(self):
        post(self.broker_user, "Houston, TX", "Atlanta, GA", rate="1000", email="")
        post(self.broker_user, "Chicago, IL", "Columbus, OH", rate=None, company="Other Co")
        acme = Broker.objects.get(name="Acme Freight")
        self.assertEqual(acme.contact_email, "loads@acme.example.com")
        page = self.client.get(reverse("broker_list"), {"state": "TX"})
        listed = {b.name: b for b in page.context["page"]}
        self.assertEqual(set(listed), {"Acme Freight"})
        self.assertEqual(listed["Acme Freight"].posted, 2)  # state filter must not double-count
        expected = (2500 / self.posting.trip_miles + 1000 / acme.postings.get(rate=1000).trip_miles) / 2
        self.assertAlmostEqual(listed["Acme Freight"].avg_rpm, expected, places=4)

    def test_search_and_detail(self):
        response = self.client.get(reverse("broker_list"), {"q": "acme"})
        self.assertContains(response, "Acme Freight")
        detail = self.client.get(reverse("broker_detail", args=[self.posting.broker.pk]))
        self.assertContains(detail, "TX → GA")
        self.assertContains(detail, reverse("call_assistant", args=[self.posting.pk]))

    def test_brokers_cannot_browse_directory(self):
        self.client.force_login(self.broker_user)
        self.assertEqual(self.client.get(reverse("broker_list")).status_code, 403)


class ProfileTests(Base):
    def test_profile_updates_signature_details(self):
        self.client.post(reverse("profile"), {
            "first_name": "Sean", "last_name": "D", "email": "disp@example.com",
            "company_name": "New Co", "mc_number": "999", "phone": "1",
        })
        self.dispatcher.refresh_from_db()
        self.assertEqual(self.dispatcher.mc_number, "999")
        self.assertIn("MC# 999", ai.template_email(self.posting, self.dispatcher).body)


class WordingTests(Base):
    def test_truck_already_at_pickup(self):
        self.assertIn("already in Dallas, TX", ai.template_email(self.posting, self.dispatcher, dh_o=0).body)
        self.assertIn("80 miles from the pickup", ai.template_email(self.posting, self.dispatcher, dh_o=80).body)
