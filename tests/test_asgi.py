"""Focused tests for the ASGI websocket adapter (fake transport)."""
import asyncio
import json
import unittest

from flyrail import Stack, Text, Button
from flyrail.asgi import create_ws_app


def panel(s):
    return Stack(
        Text(f"v={s['v']}", key="label"),
        Button("Bump", on_click=lambda st, ev: st.update(v=st["v"] + 1), key="bump"),
    )


SCOPE = {"type": "websocket", "path": "/", "query_string": b""}


class Channel:
    def __init__(self):
        self.incoming = asyncio.Queue()
        self.sent = []

    async def receive(self):
        return await self.incoming.get()

    async def send(self, msg):
        self.sent.append(msg)

    def ui(self):
        out = []
        for m in self.sent:
            if m.get("type") == "websocket.send":
                d = json.loads(m["text"])
                if d.get("chan") == "ui":
                    out.append(d)
        return out

    async def wait_ui(self, n, timeout=2.0):
        async def poll():
            while len(self.ui()) < n:
                await asyncio.sleep(0.01)
        await asyncio.wait_for(poll(), timeout)


class AdapterTest(unittest.IsolatedAsyncioTestCase):
    async def run_app(self, ch, **kw):
        app = create_ws_app(panel, **kw)
        task = asyncio.create_task(app(SCOPE, ch.receive, ch.send))
        await ch.wait_ui(1)  # snapshot lands first
        return task

    async def stop(self, task, ch):
        await ch.incoming.put({"type": "websocket.disconnect"})
        await asyncio.wait_for(task, 2.0)

    async def test_snapshot_then_action_then_patch(self):
        ch = Channel()
        task = await self.run_app(ch, state_factory=lambda: {"v": 1})
        snap = ch.ui()[0]
        self.assertEqual(snap["type"], "snapshot")
        self.assertEqual(snap["seq"], 1)

        hid = snap["tree"]["children"][1]["on_click"]["handlerId"]
        await ch.incoming.put({"type": "websocket.receive", "text": json.dumps(
            {"chan": "ui", "type": "action", "handlerId": hid})})
        await ch.wait_ui(2)
        patch = ch.ui()[1]
        self.assertEqual(patch["type"], "patch")
        self.assertEqual(patch["seq"], 2)
        await self.stop(task, ch)
        self.assertTrue(task.done())

    async def test_resync_request_gets_snapshot(self):
        ch = Channel()
        task = await self.run_app(ch, state_factory=lambda: {"v": 1})
        await ch.incoming.put({"type": "websocket.receive", "text": json.dumps(
            {"chan": "ui", "type": "resync-request"})})
        await ch.wait_ui(2)
        snap = ch.ui()[1]
        self.assertEqual(snap["type"], "snapshot")
        self.assertEqual(snap["seq"], 2)
        await self.stop(task, ch)

    async def test_non_ui_goes_to_callback(self):
        seen = []
        ch = Channel()
        task = await self.run_app(
            ch, state_factory=lambda: {"v": 1},
            on_message=lambda data, state: seen.append(data))
        await ch.incoming.put({"type": "websocket.receive", "text": json.dumps(
            {"chan": "telemetry", "speed": 42})})
        for _ in range(100):
            if seen:
                break
            await asyncio.sleep(0.01)
        self.assertEqual(seen, [{"chan": "telemetry", "speed": 42}])
        self.assertEqual(len(ch.ui()), 1)  # no ui response
        await self.stop(task, ch)

    async def test_a_stale_handler_id_does_not_end_the_session(self):
        """Handler ids are rebuilt every render, so a click on a button the
        last patch removed is ordinary traffic. It raised KeyError out of the
        receive loop and closed the connection."""
        ch = Channel()
        task = await self.run_app(ch, state_factory=lambda: {"v": 1})
        hid = ch.ui()[0]["tree"]["children"][1]["on_click"]["handlerId"]

        with self.assertLogs("flyrail", "INFO"):
            await ch.incoming.put({"type": "websocket.receive", "text": json.dumps(
                {"chan": "ui", "type": "action", "handlerId": "gone"})})
            await asyncio.sleep(0.05)
        self.assertFalse(task.done(), "session ended on a stale click")

        await ch.incoming.put({"type": "websocket.receive", "text": json.dumps(
            {"chan": "ui", "type": "action", "handlerId": hid})})
        await ch.wait_ui(2)
        self.assertEqual(ch.ui()[1]["type"], "patch")
        await self.stop(task, ch)

    async def test_a_raising_handler_is_logged_and_the_session_survives(self):
        def boom(state, event):
            raise ValueError("handler bug")

        app = create_ws_app(lambda s: Stack(
            Button("Boom", on_click=boom, key="boom"), *panel(s)["children"]),
            state_factory=lambda: {"v": 1})
        ch = Channel()
        task = asyncio.create_task(app(SCOPE, ch.receive, ch.send))
        await ch.wait_ui(1)
        children = ch.ui()[0]["tree"]["children"]

        with self.assertLogs("flyrail", "ERROR") as logs:
            await ch.incoming.put({"type": "websocket.receive", "text": json.dumps(
                {"chan": "ui", "type": "action",
                 "handlerId": children[0]["on_click"]["handlerId"]})})
            await asyncio.sleep(0.05)
        self.assertIn("handler bug", "\n".join(logs.output))
        self.assertFalse(task.done(), "session ended on a handler error")

        await ch.incoming.put({"type": "websocket.receive", "text": json.dumps(
            {"chan": "ui", "type": "action",
             "handlerId": children[2]["on_click"]["handlerId"]})})
        await ch.wait_ui(2)
        await self.stop(task, ch)

    async def test_a_malformed_message_is_logged_and_the_session_survives(self):
        ch = Channel()
        task = await self.run_app(ch, state_factory=lambda: {"v": 1})

        with self.assertLogs("flyrail", "WARNING"):
            await ch.incoming.put({"type": "websocket.receive", "text": "{not json"})
            await ch.incoming.put({"type": "websocket.receive", "text": "[1, 2]"})
            await asyncio.sleep(0.05)
        self.assertFalse(task.done(), "session ended on a malformed message")

        await ch.incoming.put({"type": "websocket.receive", "text": json.dumps(
            {"chan": "ui", "type": "resync-request"})})
        await ch.wait_ui(2)
        await self.stop(task, ch)

    async def test_a_render_error_is_logged_and_the_next_render_retries(self):
        """The render loop runs as its own task. A render that raised ended
        that task, the receive loop carried on, and the page looked connected
        but never updated again -- even once the state that broke it moved."""
        def fragile(s):
            if s["v"] == 2:
                raise ValueError("render bug")
            return panel(s)

        app = create_ws_app(fragile, state_factory=lambda: {"v": 1})
        ch = Channel()
        task = asyncio.create_task(app(SCOPE, ch.receive, ch.send))
        await ch.wait_ui(1)
        hid = ch.ui()[0]["tree"]["children"][1]["on_click"]["handlerId"]
        click = {"type": "websocket.receive", "text": json.dumps(
            {"chan": "ui", "type": "action", "handlerId": hid})}

        with self.assertLogs("flyrail", "ERROR") as logs:
            await ch.incoming.put(click)  # v -> 2: render raises
            await asyncio.sleep(0.05)
        self.assertIn("render bug", "\n".join(logs.output))

        await ch.incoming.put(click)  # v -> 3: renders again
        await ch.wait_ui(2)
        self.assertIn("v=3", json.dumps(ch.ui()[1]["ops"]))
        await self.stop(task, ch)

    async def test_a_resync_that_fails_to_render_keeps_the_session(self):
        state = {"v": 1}

        def fragile(s):
            if s["v"] == 2:
                raise ValueError("render bug")
            return panel(s)

        app = create_ws_app(fragile, state_factory=lambda: state)
        ch = Channel()
        task = asyncio.create_task(app(SCOPE, ch.receive, ch.send))
        await ch.wait_ui(1)
        resync = {"type": "websocket.receive", "text": json.dumps(
            {"chan": "ui", "type": "resync-request"})}

        state["v"] = 2
        with self.assertLogs("flyrail", "ERROR"):
            await ch.incoming.put(resync)
            await asyncio.sleep(0.05)
        self.assertFalse(task.done(), "session ended on a failed resync")

        state["v"] = 3
        await ch.incoming.put(resync)
        await ch.wait_ui(2)
        self.assertEqual(ch.ui()[1]["seq"], 2, "the failed resync used up a seq")
        await self.stop(task, ch)

    async def test_rejects_non_websocket_scope(self):
        ch = Channel()
        app = create_ws_app(panel)
        with self.assertRaises(RuntimeError):
            await app({"type": "http"}, ch.receive, ch.send)


if __name__ == "__main__":
    unittest.main()
