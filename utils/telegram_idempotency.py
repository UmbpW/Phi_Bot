"""LRU/TTL кеш обработанных update_id — убирает дубли при Telegram retries."""

import time
from collections import OrderedDict
from typing import Optional

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject


class SeenUpdates:
    """Кеш обработанных update_id. При retry — skip обработки."""

    def __init__(self, max_size: int = 5000, ttl_seconds: int = 3600):
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        self._cache: OrderedDict[int, float] = OrderedDict()
        self._last_clean = time.monotonic()

    def seen(self, update_id: int) -> bool:
        """True если update_id уже обработан."""
        self._maybe_clean()
        return update_id in self._cache

    def mark(self, update_id: int) -> None:
        """Отметить update_id как обработанный."""
        self._maybe_clean()
        if update_id in self._cache:
            self._cache.move_to_end(update_id)
        self._cache[update_id] = time.monotonic()
        if len(self._cache) > self.max_size:
            self._evict_oldest()

    def _maybe_clean(self) -> None:
        """Периодическая очистка по TTL."""
        now = time.monotonic()
        if now - self._last_clean < 60:
            return
        self._last_clean = now
        expire = now - self.ttl_seconds
        to_del = [uid for uid, ts in self._cache.items() if ts < expire]
        for uid in to_del:
            del self._cache[uid]

    def _evict_oldest(self) -> None:
        while len(self._cache) > self.max_size:
            self._cache.popitem(last=False)


_seen = SeenUpdates()


class IdempotencyMiddleware(BaseMiddleware):
    """Пропускает дубликаты update при Telegram retries. Регистрировать: dp.update.outer_middleware(IdempotencyMiddleware())."""

    async def __call__(
        self,
        handler,
        event: TelegramObject,
        data: dict,
    ):
        # event = Update при регистрации на dp.update
        update_id = getattr(event, "update_id", None)
        if update_id is not None:
            if _seen.seen(update_id):
                return  # дубликат — не обрабатываем, не вызываем handler
            _seen.mark(update_id)
            data["update_id"] = update_id  # BUG3: для логирования в handlers
        return await handler(event, data)
