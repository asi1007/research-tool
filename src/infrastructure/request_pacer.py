from __future__ import annotations

import time
from collections.abc import Callable


class RequestPacer:
    def __init__(
        self,
        min_interval_seconds: float,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self.min_interval_seconds = min_interval_seconds
        self.sleep = sleep
        self.monotonic = monotonic
        self._last_started_at: float | None = None

    def wait(self) -> None:
        now = self.monotonic()

        if self._last_started_at is not None and self.min_interval_seconds > 0:
            remaining = self.min_interval_seconds - (now - self._last_started_at)
            if remaining > 0:
                self.sleep(remaining)
                now = self.monotonic()

        self._last_started_at = now
