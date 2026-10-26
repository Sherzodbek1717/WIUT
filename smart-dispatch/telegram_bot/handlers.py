"""What the bot does with each Telegram update.

Drivers can:
- link their chat with `/start CODE` (code from the dispatcher's Drivers page),
- see their current load with /load,
- move it to In transit or Delivered with buttons,
- send a photo or document of the signed POD, which is attached to the load.

Status changes go through dispatch.services, so the same rules apply as in the web app.
"""

import logging
from datetime import timedelta
from html import escape

from django.core.files.base import ContentFile
from django.db import IntegrityError
from django.utils import timezone

from dispatch.models import Driver, Load, ProofOfDelivery
from dispatch.services import DispatchError, change_status

from .client import TelegramError

logger = logging.getLogger(__name__)

# How long after delivery a driver can still send the POD for that load.
POD_GRACE_PERIOD = timedelta(hours=72)

HELP_TEXT = (
    "<b>Smart Dispatch driver bot</b>\n"
    "/load – your current load\n"
    "Send a <b>photo or PDF of the signed POD</b> and it is attached to your load.\n"
    "/help – this message"
)
NOT_LINKED_TEXT = (
    "This chat is not linked to a driver yet.\n"
    "Ask your dispatcher for your link code, then send:\n<code>/start YOURCODE</code>"
)

NEXT_STEP = {
    Load.Status.DISPATCHED: (Load.Status.IN_TRANSIT, "🚚 Picked up – in transit"),
    Load.Status.IN_TRANSIT: (Load.Status.DELIVERED, "✅ Delivered"),
}


def describe_load(load):
    e = escape
    lines = [
        f"<b>{e(load.origin_city)}, {load.origin_state} → {e(load.destination_city)}, {load.destination_state}</b>",
        f"Status: {load.get_status_display()}",
        f"Pickup: {timezone.localtime(load.pickup_at):%a %b %d, %H:%M}",
        f"Delivery: {timezone.localtime(load.delivery_at):%a %b %d, %H:%M}",
        f"Miles: {load.loaded_miles} loaded + {load.deadhead_miles} empty",
    ]
    if load.reference:
        lines.insert(1, f"Ref: {e(load.reference)}")
    if load.commodity:
        lines.append(f"Commodity: {e(load.commodity)}")
    return "\n".join(lines)


def status_buttons(load):
    step = NEXT_STEP.get(load.status)
    return [(step[1], f"status:{load.pk}:{step[0]}")] if step else None


def pod_target(driver):
    """Load a POD should attach to: the current load, else one delivered recently."""
    current = driver.current_load()
    if current:
        return current
    recent = (
        driver.assignments.filter(
            active=True, load__status=Load.Status.DELIVERED,
            load__delivered_at__gte=timezone.now() - POD_GRACE_PERIOD,
        )
        .select_related("load")
        .order_by("-load__delivered_at")
        .first()
    )
    return recent.load if recent else None


def handle_update(update, client):
    if "callback_query" in update:
        return _handle_callback(update["callback_query"], client)
    message = update.get("message")
    if not message:
        return
    chat_id = message["chat"]["id"]
    text = (message.get("text") or "").strip()

    if text.startswith("/start"):
        return _link(chat_id, text.removeprefix("/start").strip(), client)

    driver = Driver.objects.filter(telegram_chat_id=chat_id).first()
    if driver is None:
        return client.send_message(chat_id, NOT_LINKED_TEXT)

    if "photo" in message or "document" in message:
        return _save_pod(driver, message, client)
    if text.startswith("/load"):
        return _send_current_load(driver, client)
    return client.send_message(chat_id, HELP_TEXT)


def _link(chat_id, code, client):
    if not code:
        driver = Driver.objects.filter(telegram_chat_id=chat_id).first()
        if driver:
            return client.send_message(chat_id, f"Hi {escape(driver.first_name)}! You are linked.\n\n{HELP_TEXT}")
        return client.send_message(chat_id, NOT_LINKED_TEXT)

    driver = Driver.objects.filter(telegram_link_code=code.upper()).first()
    if driver is None:
        return client.send_message(chat_id, "That code is not valid. Ask your dispatcher for a new one.")

    # A chat belongs to one driver: unlink it from anyone else first.
    Driver.objects.filter(telegram_chat_id=chat_id).exclude(pk=driver.pk).update(telegram_chat_id=None)
    driver.telegram_chat_id = chat_id
    driver.telegram_link_code = None  # one-time code
    try:
        driver.save(update_fields=["telegram_chat_id", "telegram_link_code"])
    except IntegrityError:
        return client.send_message(chat_id, "Could not link this chat. Ask your dispatcher for help.")
    client.send_message(chat_id, f"✅ Linked to <b>{escape(str(driver))}</b>.\n\n{HELP_TEXT}")
    load = driver.current_load()
    if load:
        client.send_message(chat_id, describe_load(load), buttons=status_buttons(load))


def _send_current_load(driver, client):
    load = driver.current_load()
    if load is None:
        return client.send_message(driver.telegram_chat_id, "You have no active load right now.")
    return client.send_message(driver.telegram_chat_id, describe_load(load), buttons=status_buttons(load))


def _handle_callback(callback, client):
    chat_id = callback["message"]["chat"]["id"]
    driver = Driver.objects.filter(telegram_chat_id=chat_id).first()
    try:
        action, load_id, new_status = callback.get("data", "").split(":")
    except ValueError:
        return client.answer_callback(callback["id"], "Unknown action.")

    load = driver.current_load() if driver else None
    if action != "status" or load is None or str(load.pk) != load_id:
        return client.answer_callback(callback["id"], "This load is no longer assigned to you.")

    try:
        load = change_status(load, new_status)
    except DispatchError as exc:
        return client.answer_callback(callback["id"], str(exc))

    client.answer_callback(callback["id"], f"Marked {load.get_status_display().lower()}.")
    if load.status == Load.Status.DELIVERED:
        client.send_message(chat_id, "✅ Delivered. Please send a <b>photo of the signed POD</b> now.")
    else:
        client.send_message(chat_id, describe_load(load), buttons=status_buttons(load))


def _save_pod(driver, message, client):
    chat_id = driver.telegram_chat_id
    load = pod_target(driver)
    if load is None:
        return client.send_message(chat_id, "You have no current or recently delivered load to attach this to.")

    if "photo" in message:
        file_id = message["photo"][-1]["file_id"]  # last size is the largest
        name = f"pod_{load.pk}_{timezone.now():%Y%m%d_%H%M%S}.jpg"
    else:
        document = message["document"]
        file_id = document["file_id"]
        name = document.get("file_name") or f"pod_{load.pk}.bin"

    try:
        content = client.download_file(file_id)
    except TelegramError:
        logger.exception("POD download failed")
        return client.send_message(chat_id, "Sorry, I could not download that file. Please try again.")

    pod = ProofOfDelivery(load=load, driver=driver, original_name=name[:200])
    pod.file.save(name, ContentFile(content), save=True)
    count = load.pods.count()
    client.send_message(chat_id, f"📄 POD received for {escape(load.lane)} ({count} file{'s' if count > 1 else ''}). Thank you!")
