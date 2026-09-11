"""Loopback through the public API the way a real tick loop would use it.

Stands in for wiring into the host app: fixed-tick renders, seq-numbered
patch envelopes, client actions routed by handlerId, slot fast-path, and
snapshot recovery - all through Layout + transport, no internals touched.
"""
import unittest

from pyforms import Layout, Stack, Text, Button, TextField
from pyforms.transport import ui_envelope_patch


class Sim:
    def __init__(self):
        self.speed = 10
        self.name = "rig-1"
        self.items = [
            {"id": "a1", "name": "box A"},
            {"id": "a2", "name": "box B"},
        ]


class Panel:
    def render(self, s):
        return Stack(
            Text(f"{s.name}: {s.speed}"),
            Button("Stop", on_click=self.stop),
            TextField(value=s.name, on_change=self.rename, key="name"),
            Stack(*[Text(i["name"], key=i["id"]) for i in s.items], key="items"),
        )

    def stop(self, state, event):
        state.speed = 0

    def rename(self, state, event):
        state.name = event["value"]


def click(layout, suffix):
    hid = next(h for h in layout.registry if h.endswith(suffix))
    return hid


class LoopTest(unittest.TestCase):
    def test_tick_action_slot_snapshot_loop(self):
        s = Sim()
        layout = Layout(
            Panel().render, allowed_types={"Stack", "Text", "Button", "TextField"}
        )
        seq = 0

        # First tick: full patch, seq 1.
        ops = layout.tick(s)
        self.assertTrue(ops)
        seq += 1
        env = ui_envelope_patch(ops, seq)
        self.assertEqual(env["seq"], 1)

        # Idle ticks: silence on the shared channel.
        for _ in range(5):
            self.assertEqual(layout.tick(s), [])

        # Click Stop: action mutates sim state, next tick emits.
        layout.dispatch(click(layout, ":on_click:"), s)
        self.assertEqual(s.speed, 0)
        ops = layout.tick(s)
        self.assertTrue(ops)

        # Rename via change event value; reorder stays a single replace.
        layout.dispatch(
            click(layout, ":on_change:name"), s, {"value": "rig-2"}
        )
        self.assertEqual(s.name, "rig-2")
        s.items.reverse()
        ops = layout.tick(s)
        self.assertEqual(len(ops), 1)
        self.assertEqual(ops[0]["op"], "replace")

        # Hot path: slot message bypasses the tree entirely.
        msg = layout.set_slot("rows", [r for r in range(3)])
        self.assertEqual(msg["type"], "slot")
        self.assertIsNone(layout.set_slot("rows", [r for r in range(3)]))

        # Recovery: snapshot answers a resync-request, loop continues.
        snap = layout.snapshot(s, seq=99)
        self.assertEqual(snap["type"], "snapshot")
        self.assertEqual(layout.tick(s), [])
        s.speed = 42
        self.assertTrue(layout.tick(s))


if __name__ == "__main__":
    unittest.main()
