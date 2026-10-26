"""Messages the platform sends to drivers on its own (not in reply to them)."""

import logging

from django.conf import settings

from .client import TelegramClient, TelegramError
from .handlers import describe_load, status_buttons

logger = logging.getLogger(__name__)


def get_client():
    return TelegramClient(settings.TELEGRAM_BOT_TOKEN) if settings.TELEGRAM_BOT_TOKEN else None


def notify_assignment(assignment, client=None):
    """Tell a linked driver about a newly assigned load. Returns True if a message was sent.

    Failures are logged, never raised: a Telegram outage must not stop dispatching.
    """
    driver, load = assignment.driver, assignment.load
    client = client or get_client()
    if client is None or not driver.telegram_linked:
        return False
    try:
        client.send_message(
            driver.telegram_chat_id,
            f"📦 <b>New load assigned</b> (truck {assignment.truck.unit_number})\n\n{describe_load(load)}",
            buttons=status_buttons(load),
        )
    except TelegramError:
        logger.exception("Could not notify driver %s", driver.pk)
        return False
    return True
