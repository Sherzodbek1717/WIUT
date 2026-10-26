"""Run the driver bot with long polling: python manage.py run_telegram_bot"""

import logging
import time

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import close_old_connections

from telegram_bot.client import TelegramClient, TelegramError
from telegram_bot.handlers import handle_update

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Run the Telegram bot for drivers (long polling). Stop with Ctrl+C."

    def handle(self, *args, **options):
        if not settings.TELEGRAM_BOT_TOKEN:
            raise CommandError("Set the TELEGRAM_BOT_TOKEN environment variable first (token from @BotFather).")
        client = TelegramClient(settings.TELEGRAM_BOT_TOKEN)
        try:
            me = client.call("getMe")
        except TelegramError as exc:
            raise CommandError(f"Could not reach Telegram: {exc}") from exc
        self.stdout.write(self.style.SUCCESS(f"Bot @{me['username']} is running. Press Ctrl+C to stop."))

        offset = None
        try:
            while True:
                try:
                    updates = client.get_updates(offset=offset)
                except TelegramError as exc:
                    self.stderr.write(f"{exc}; retrying in 5 s")
                    time.sleep(5)
                    continue
                for update in updates:
                    offset = update["update_id"] + 1
                    close_old_connections()
                    try:
                        handle_update(update, client)
                    except Exception:  # one bad update must not stop the bot
                        logger.exception("Failed to handle update %s", update.get("update_id"))
        except KeyboardInterrupt:
            self.stdout.write("Bot stopped.")
