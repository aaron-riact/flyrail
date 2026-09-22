"""Focused tests for Layout action dispatch and slot fast-path."""
import unittest

from flyrail import Layout, Stack, Text, Button


class DispatchTest(unittest.TestCase):
    def test_dispatch_calls_handler_with_state_and_event(self):
        seen = {}

        def stop(state, event):
            seen["state"] = state
            seen["event"] = event

        layout = Layout(lambda s: Stack(Button("Stop", on_click=stop)))
        layout.render({})
        hid = next(iter(layout.registry))
        layout.dispatch(hid, {"speed": 1}, {"value": "x"})
        self.assertEqual(seen["state"], {"speed": 1})
        self.assertEqual(seen["event"], {"value": "x"})

    def test_unknown_handler_raises(self):
        layout = Layout(lambda s: Stack(Text("a")))
        layout.render({})
        with self.assertRaises(KeyError):
            layout.dispatch("9:999:on_click:", {}, None)

    def test_a_failed_render_keeps_the_last_handlers(self):
        """The client still shows the last tree that rendered, so its handlers
        must stay reachable. render() cleared the registry before rendering,
        and a render that raised left it empty: every click was then unknown
        and the panel could not be clicked back out of the bad state."""
        clicked = []

        def render(s):
            if s["broken"]:
                raise ValueError("render bug")
            return Stack(Button("Fix", on_click=lambda st, e: clicked.append(1)))

        layout = Layout(render)
        layout.render({"broken": False})
        hid = next(iter(layout.registry))

        with self.assertRaises(ValueError):
            layout.render({"broken": True})

        layout.dispatch(hid, {})
        self.assertEqual(clicked, [1])

    def test_closure_binds_per_row_args(self):
        # on_click=lambda st,ev,_id=i: ... carries row args without wire data.
        calls = []
        items = ["a1", "a2"]

        def render(s):
            return Stack(*[
                Button(n, on_click=lambda st, ev, _id=n: calls.append(_id), key=n)
                for n in items
            ])

        layout = Layout(render)
        layout.render({})
        for hid in sorted(layout.registry):
            layout.dispatch(hid, {}, None)
        self.assertEqual(sorted(calls), ["a1", "a2"])


class SlotsTest(unittest.TestCase):
    def test_first_set_emits_slot_message(self):
        layout = Layout(lambda s: Stack(Text("a")))
        self.assertEqual(
            layout.set_slot("rows", [1, 2, 3]),
            {"chan": "ui", "type": "slot", "name": "rows", "value": [1, 2, 3]},
        )

    def test_repeat_value_suppressed(self):
        layout = Layout(lambda s: Stack(Text("a")))
        layout.set_slot("rows", [1, 2, 3])
        self.assertIsNone(layout.set_slot("rows", [1, 2, 3]))

    def test_changed_value_reemits(self):
        layout = Layout(lambda s: Stack(Text("a")))
        layout.set_slot("rows", [1])
        self.assertIsNotNone(layout.set_slot("rows", [1, 2]))


if __name__ == "__main__":
    unittest.main()
