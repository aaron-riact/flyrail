"""Host scheduling seam: one primitive for tick, async, and naive hosts."""
from __future__ import annotations
import asyncio
from typing import Any, Callable

from .layout import Layout


class Driver:
    """Wraps Layout with dirty-flag scheduling and caller-owned seq.

    Tick hosts:   invalidate() per tick (or on sim change); flush(state, version).
    Async hosts:  invalidate() from event handlers; await run(state_fn, send).
    Naive hosts:  invalidate() + flush() around every message.
    Thread-safe invalidate: safe to call from any thread; the run loop
    (single asyncio loop assumption) wakes via call_soon_threadsafe.
    """

    def __init__(self, layout: Layout):
        self.layout = layout
        self.seq = 0
        self._event = asyncio.Event()

    def invalidate(self) -> None:
        self.layout.invalidate()
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop is None:
            self._event.set()
        else:
            loop.call_soon_threadsafe(self._event.set)

    def flush(self, state: Any, version: Any = None) -> dict | None:
        """Render+diff if dirty/version-changed; seq-numbered envelope or None."""
        ops = self.layout.tick(state, version)
        if not ops:
            return None
        self.seq += 1
        return {"chan": "ui", "type": "patch", "seq": self.seq, "ops": ops}

    async def run(
        self,
        state_fn: Callable[[], Any],
        send: Callable[[dict], Any],
        version_fn: Callable[[], Any] = lambda: None,
    ) -> None:
        """Never returns; cancel to stop. Bursts coalesce into one flush."""
        while True:
            await self._event.wait()
            self._event.clear()
            env = self.flush(state_fn(), version_fn())
            if env is not None:
                await send(env)
