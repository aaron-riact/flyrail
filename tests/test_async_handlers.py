"""Focused tests for async event handlers via adispatch."""
import asyncio
import unittest

from flyrail import Layout, Stack, Button


class AsyncDispatchTest(unittest.TestCase):
    def setUp(self):
        async def save(state, event):
            await asyncio.sleep(0)
            state["saved"].append(event["value"])

        def ping(state, event):
            state["pings"] += 1
            return "pong"

        layout = Layout(lambda s: Stack(
            Button("Save", on_click=save, key="save"),
            Button("Ping", on_click=ping, key="ping"),
        ))
        layout.tick({})
        self.hids = {h.split(":")[-1]: h for h in layout.registry}
        self.layout = layout

    def test_sync_dispatch_rejects_async_handler_loudly(self):
        with self.assertRaises(RuntimeError):
            self.layout.dispatch(self.hids["save"], {"saved": []})

    def test_sync_dispatch_still_works(self):
        state = {"pings": 0}
        self.layout.dispatch(self.hids["ping"], state)
        self.assertEqual(state["pings"], 1)


class AsyncDispatchAsyncTest(unittest.IsolatedAsyncioTestCase):
    async def test_adispatch_awaits_and_returns(self):
        async def save(state, event):
            await asyncio.sleep(0)
            state["saved"].append(event["value"])
            return "saved!"

        def ping(state, event):
            return "pong"

        layout = Layout(lambda s: Stack(
            Button("Save", on_click=save, key="save"),
            Button("Ping", on_click=ping, key="ping"),
        ))
        layout.tick({})
        hids = {h.split(":")[-1]: h for h in layout.registry}

        state = {"saved": []}
        res = await layout.adispatch(hids["save"], state, {"value": "a"})
        self.assertEqual(res, "saved!")
        self.assertEqual(state["saved"], ["a"])
        # Sync handlers work through the same path.
        self.assertEqual(await layout.adispatch(hids["ping"], state), "pong")

    async def test_adispatch_unknown_raises(self):
        layout = Layout(lambda s: Stack(Button("A", on_click=lambda s, e: None)))
        layout.tick({})
        with self.assertRaises(KeyError):
            await layout.adispatch("9:999:on_click:", {})


if __name__ == "__main__":
    unittest.main()
