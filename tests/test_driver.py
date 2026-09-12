"""Focused tests for Driver scheduling across host models."""
import asyncio
import unittest

from flyrail import Layout, Stack, Text
from flyrail.core import pure
from flyrail.driver import Driver


class PurePanel:
    def __init__(self):
        self.calls = 0

    @pure
    def render(self, s):
        self.calls += 1
        return Stack(Text(f"v={s['v']}"))


class FlushTest(unittest.TestCase):
    def test_envelope_seq_bumps_only_on_change(self):
        d = Driver(Layout(PurePanel().render))
        env1 = d.flush({"v": 1}, version=1)
        self.assertEqual(env1["seq"], 1)
        self.assertIsNone(d.flush({"v": 1}, version=1))
        env2 = d.flush({"v": 2}, version=2)
        self.assertEqual(env2["seq"], 2)

    def test_invalidate_forces_render_but_not_send(self):
        p = PurePanel()
        d = Driver(Layout(p.render))
        d.flush({"v": 1}, version=1)
        d.invalidate()
        # Re-rendered (calls 2) yet tree identical, so nothing to send.
        self.assertIsNone(d.flush({"v": 1}, version=1))
        self.assertEqual(p.calls, 2)

    def test_unmarked_renders_rely_on_diff_gate(self):
        d = Driver(Layout(lambda s: Stack(Text(f"v={s['v']}"))))
        self.assertIsNotNone(d.flush({"v": 1}, version=1))
        self.assertIsNone(d.flush({"v": 1}, version=1))

    def test_invalidate_without_loop_does_not_raise(self):
        d = Driver(Layout(PurePanel().render))
        d.invalidate()  # no running loop: direct set path


class RunTest(unittest.IsolatedAsyncioTestCase):
    async def test_run_sends_on_invalidate_only(self):
        state = {"v": 1}
        d = Driver(Layout(PurePanel().render))
        sent = []

        async def send(env):
            sent.append(env)

        task = asyncio.create_task(d.run(lambda: state, send, lambda: state["v"]))
        try:
            d.invalidate()  # running-loop path (call_soon_threadsafe)
            for _ in range(100):
                if sent:
                    break
                await asyncio.sleep(0.01)
            self.assertEqual(len(sent), 1)
            self.assertEqual(sent[0]["seq"], 1)
            await asyncio.sleep(0.05)
            self.assertEqual(len(sent), 1)  # no spurious renders

            state["v"] = 2
            d.invalidate()
            for _ in range(100):
                if len(sent) == 2:
                    break
                await asyncio.sleep(0.01)
            self.assertEqual(len(sent), 2)
            self.assertEqual(sent[1]["seq"], 2)
        finally:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass


if __name__ == "__main__":
    unittest.main()
