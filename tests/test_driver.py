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
            d.invalidate()  # from the loop itself: direct set
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

    async def test_set_state_outside_a_handler_wakes_the_loop(self):
        """A hook setter marked the layout dirty and nothing else, so a
        set_state from a timer, a task or an effect never woke run() and sat
        unrendered until something else called invalidate()."""
        from flyrail import component, use_state

        setters = []

        @component
        def Clock(_state):
            now, set_now = use_state("12:00")
            setters.append(set_now)
            return Text(now)

        d = Driver(Layout(Clock))
        arrived = asyncio.get_running_loop().create_future()

        async def send(env):
            if not arrived.done():
                arrived.set_result(env)

        d.layout.snapshot(None, seq=0)  # first paint, as create_ws_app does
        task = asyncio.create_task(d.run(lambda: None, send))
        try:
            await asyncio.sleep(0)
            setters[-1]("12:01")  # no invalidate(): the hook has to do it

            env = await asyncio.wait_for(arrived, timeout=1.0)
            self.assertIn("12:01", repr(env["ops"]))
        finally:
            task.cancel()
            await asyncio.wait({task}, timeout=1.0)


class ThreadWakeTest(unittest.TestCase):
    def test_invalidate_from_another_thread_wakes_the_loop(self):
        """From a thread with no running loop, invalidate() used to set the
        asyncio.Event directly. That is not thread-safe and does not wake a
        loop blocked in select, so with no timer due the flush never came.

        The loop runs on its own daemon thread so a regression fails here
        after a second instead of hanging the suite.
        """
        import threading
        import time

        state = {"v": 1}
        d = Driver(Layout(lambda s: Stack(Text(f"v={s['v']}"))))
        sent = threading.Event()
        envs = []

        async def send(env):
            envs.append(env)
            sent.set()

        loop = asyncio.new_event_loop()
        runner = threading.Thread(target=loop.run_forever, daemon=True)
        runner.start()
        asyncio.run_coroutine_threadsafe(d.run(lambda: state, send), loop)
        try:
            time.sleep(0.05)  # let run() reach its wait
            state["v"] = 2
            d.invalidate()  # this thread, not the loop's

            self.assertTrue(sent.wait(1.0), "invalidate() did not wake the loop")
            self.assertIn("v=2", repr(envs[0]["ops"]))
        finally:
            async def shutdown():
                pending = asyncio.all_tasks() - {asyncio.current_task()}
                for t in pending:
                    t.cancel()
                await asyncio.gather(*pending, return_exceptions=True)

            try:
                asyncio.run_coroutine_threadsafe(shutdown(), loop).result(1.0)
            except TimeoutError:
                pass  # the stuck task of a regression; the thread is a daemon
            loop.call_soon_threadsafe(loop.stop)
            runner.join(1.0)
            if not runner.is_alive():
                loop.close()


if __name__ == "__main__":
    unittest.main()
