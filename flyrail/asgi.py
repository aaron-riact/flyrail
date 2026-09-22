"""Framework-free ASGI websocket adapter: the async-host recipe.

One state + Driver + Layout per connection; no dependency beyond stdlib.
FastAPI/Starlette/Django-Channels users mount this where they handle
websockets (see README Hosting); everyone else copies the 30-line shape.
"""
from __future__ import annotations
import asyncio
import inspect
import json
import logging
from typing import Any, Callable

from .driver import Driver
from .layout import Layout

log = logging.getLogger("flyrail")


def create_ws_app(
    render_fn: Callable[[Any], dict],
    *,
    state_factory: Callable[[], Any] = dict,
    version_fn: Callable[[], Any] | None = None,
    allowed_types: set[str] | None = None,
    strict: bool = False,
    on_message: Callable[[dict, Any], Any] | None = None,
):
    """Return an ASGI websocket app serving one flyrail session per connection."""
    _version_of = version_fn or (lambda: None)

    async def app(scope, receive, send):
        if scope["type"] != "websocket":
            raise RuntimeError("flyrail ASGI app handles websocket scope only")
        layout = Layout(render_fn, allowed_types=allowed_types, strict=strict)
        driver = Driver(layout)
        state = state_factory()

        async def send_json(env: dict) -> None:
            await send({"type": "websocket.send", "text": json.dumps(env)})

        await send({"type": "websocket.accept"})
        snap = layout.snapshot(state, seq=1)
        driver.seq = 1
        await send_json(snap)

        run_task = asyncio.create_task(
            driver.run(lambda: state, send_json, _version_of)
        )
        try:
            while True:
                msg = await receive()
                if msg["type"] == "websocket.disconnect":
                    break
                if msg["type"] != "websocket.receive":
                    continue
                try:
                    data = json.loads(msg.get("text") or msg.get("bytes") or "{}")
                except ValueError:
                    log.warning("ignoring a message that is not JSON")
                    continue
                if not isinstance(data, dict):
                    log.warning("ignoring a message that is not a JSON object")
                    continue
                if data.get("chan") != "ui":
                    if on_message is not None:
                        res = on_message(data, state)
                        if inspect.isawaitable(res):
                            await res
                    continue
                kind = data.get("type")
                if kind == "action":
                    hid = data.get("handlerId")
                    if not isinstance(hid, str) or hid not in layout.registry:
                        # Ids are rebuilt every render, so a click on something
                        # the last patch removed is ordinary, not an error.
                        log.info("ignoring action for stale handler %r", hid)
                        continue
                    try:
                        await layout.adispatch(hid, state, data.get("event"))
                    except Exception:
                        # One bad handler must not close the page: a closed
                        # socket is a reload, and a reload loses the session.
                        # It may have changed state before raising, so still
                        # render.
                        log.exception("handler %r raised", hid)
                    driver.invalidate()
                elif kind == "resync-request":
                    driver.seq += 1
                    await send_json(layout.snapshot(state, driver.seq))
                # Unknown ui subtypes ignored (forward-compat, mirrors store).
        finally:
            run_task.cancel()
            try:
                await run_task
            except asyncio.CancelledError:
                pass

    return app
