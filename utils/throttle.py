import time

from aiogram import BaseMiddleware


class ThrottleMiddleware(BaseMiddleware):
    """Защита бота от флуда: не чаще одного обновления за `interval` секунд от одного пользователя."""

    def __init__(self, interval: float = 0.4):
        self.interval = interval
        self._last: dict[int, float] = {}

    async def __call__(self, handler, event, data):
        user = data.get("event_from_user")
        if user:
            now = time.monotonic()
            if now - self._last.get(user.id, 0) < self.interval:
                return None
            self._last[user.id] = now
            if len(self._last) > 20000:   # не даём словарю расти бесконечно
                cutoff = now - 60
                self._last = {k: v for k, v in self._last.items() if v > cutoff}
        return await handler(event, data)
