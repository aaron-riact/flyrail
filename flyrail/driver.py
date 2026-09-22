"""Host scheduling seam: one primitive for tick, async, and naive hosts."""
from __future__ import annotations
import asyncio
import logging
from typing import Any, Callable

from .layout import Layout

log = logging.getLogger("flyrail")


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
        #: The loop run() waits on, so another thread can reach it. Asking for
        #: the running loop from that thread finds none, and setting the Event
        #: directly from there neither is thread-safe nor wakes the loop.
        self._loop: asyncio.AbstractEventLoop | None = None
        layout.on_schedule = self._wake

    def invalidate(self) -> None:
        self.layout.invalidate()
        self._wake()

    def _wake(self) -> None:
        """Let run() know there is work, from whichever thread this is."""
        loop = self._loop
        if loop is None or loop.is_closed():
            self._event.set()  # nothing is waiting yet
            return
        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None
        if running is loop:
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
        """Never returns; cancel to stop. Bursts coalesce into one flush.

        A render that raises is logged and the loop carries on. Letting it
        end the task left the session looking connected with nothing ever
        rendering again; this way the next invalidate() tries once more, and
        the page recovers as soon as the state that broke it moves.
        """
        self._loop = asyncio.get_running_loop()
        while True:
            await self._event.wait()
            self._event.clear()
            try:
                env = self.flush(state_fn(), version_fn())
            except Exception:
                log.exception("render failed")
                continue
            if env is not None:
                await send(env)
