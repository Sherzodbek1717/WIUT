"""Minimal Telegram Bot API client using only the standard library.

Only the handful of methods the driver bot needs. See https://core.telegram.org/bots/api
"""

import json
import urllib.error
import urllib.request

API_URL = "https://api.telegram.org/bot{token}/{method}"
FILE_URL = "https://api.telegram.org/file/bot{token}/{path}"


class TelegramError(Exception):
    pass


class TelegramClient:
    def __init__(self, token, timeout=40):
        if not token:
            raise TelegramError("TELEGRAM_BOT_TOKEN is not set.")
        self.token = token
        self.timeout = timeout

    def call(self, method, **params):
        data = json.dumps({k: v for k, v in params.items() if v is not None}).encode()
        request = urllib.request.Request(
            API_URL.format(token=self.token, method=method),
            data=data,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = json.load(response)
        except urllib.error.HTTPError as exc:
            body = json.load(exc)
        except (urllib.error.URLError, TimeoutError) as exc:
            raise TelegramError(f"Network error calling {method}: {exc}") from exc
        if not body.get("ok"):
            raise TelegramError(f"{method} failed: {body.get('description', 'unknown error')}")
        return body["result"]

    def get_updates(self, offset=None, timeout=30):
        return self.call(
            "getUpdates", offset=offset, timeout=timeout,
            allowed_updates=["message", "callback_query"],
        )

    def send_message(self, chat_id, text, buttons=None):
        markup = None
        if buttons:
            markup = {"inline_keyboard": [[{"text": label, "callback_data": data}] for label, data in buttons]}
        return self.call("sendMessage", chat_id=chat_id, text=text, parse_mode="HTML", reply_markup=markup)

    def answer_callback(self, callback_id, text=None):
        return self.call("answerCallbackQuery", callback_query_id=callback_id, text=text)

    def download_file(self, file_id):
        """Return the bytes of a file a user sent (photos and documents up to 20 MB)."""
        path = self.call("getFile", file_id=file_id)["file_path"]
        url = FILE_URL.format(token=self.token, path=path)
        try:
            with urllib.request.urlopen(url, timeout=self.timeout) as response:
                return response.read()
        except (urllib.error.URLError, TimeoutError) as exc:
            raise TelegramError(f"Could not download file: {exc}") from exc
