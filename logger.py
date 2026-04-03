"""Logging setup — RotatingFileHandler + stdout + optional Discord webhook."""
import asyncio
import logging
import os
import sys
from logging.handlers import RotatingFileHandler

import aiohttp


class DiscordWebhookHandler(logging.Handler):
    """Async logging handler that forwards log records to a Discord webhook."""

    def __init__(self, webhook_url: str):
        super().__init__(level=logging.WARNING)
        self.webhook_url = webhook_url
        self._session: aiohttp.ClientSession | None = None
        self._tasks: set[asyncio.Task] = set()

    def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    def emit(self, record: logging.LogRecord):
        try:
            loop = asyncio.get_running_loop()
            task = loop.create_task(self._send(self.format(record)))
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)
        except RuntimeError:
            pass  # No running loop (e.g. during startup) — skip silently

    async def _send(self, message: str):
        try:
            session = self._get_session()
            await session.post(self.webhook_url, json={"content": f"```\n{message[:1990]}\n```"})
        except Exception:
            pass  # Never let the log handler crash the bot


def setup_logging():
    log_formatter = logging.Formatter('%(asctime)s:%(levelname)s:%(name)s: %(message)s')

    # File Handler
    file_handler = RotatingFileHandler('bot.log', maxBytes=5*1024*1024, backupCount=2)
    file_handler.setFormatter(log_formatter)
    file_handler.setLevel(logging.INFO)

    # Stream Handler - use stdout so Railway doesn't mark INFO as errors
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(log_formatter)
    stream_handler.setLevel(logging.INFO)

    # Root Logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(stream_handler)

    # Discord webhook handler (WARNING+), if configured
    webhook_url = os.getenv("LOG_WEBHOOK_URL")
    if webhook_url:
        webhook_handler = DiscordWebhookHandler(webhook_url)
        webhook_handler.setFormatter(log_formatter)
        root_logger.addHandler(webhook_handler)
