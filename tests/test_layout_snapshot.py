"""Focused tests for Layout.snapshot resync recovery."""
import json
import unittest

from flyrail import Layout, Slot, Stack, Text, Button


class SnapshotTest(unittest.TestCase):
    def test_snapshot_carries_full_tree_and_seq(self):
        layout = Layout(lambda s: Stack(Text(f"speed: {s['speed']}")))
        msg = layout.snapshot({"speed": 3}, seq=9)
        self.assertEqual(msg["chan"], "ui")
        self.assertEqual(msg["type"], "snapshot")
        self.assertEqual(msg["seq"], 9)
        self.assertEqual(msg["tree"]["children"][0]["props"], {"value": "speed: 3"})
        json.dumps(msg)  # wire-safe

    def test_snapshot_resets_diff_baseline(self):
        layout = Layout(lambda s: Stack(Text(f"speed: {s['speed']}")))
        layout.tick({"speed": 1})
        layout.snapshot({"speed": 2}, seq=5)
        # Diff continues incrementally from the snapshot point.
        self.assertEqual(layout.tick({"speed": 2}), [])
        self.assertTrue(layout.tick({"speed": 3}))

    def test_handlers_live_after_snapshot(self):
        seen = []

        def stop(state, event):
            seen.append(True)

        layout = Layout(lambda s: Stack(Button("Stop", on_click=stop)))
        msg = layout.snapshot({}, seq=1)
        hid = msg["tree"]["children"][0]["on_click"]["handlerId"]
        layout.dispatch(hid, {})
        self.assertEqual(seen, [True])

    def test_snapshot_carries_the_last_slot_values(self):
        """The store clears its slots on a snapshot, and set_slot stays quiet
        about a value it has already sent, so a slot missing from the
        snapshot stays blank on the client until its value next changes."""
        layout = Layout(lambda s: Stack(Slot("rpm")))
        layout.set_slot("rpm", 1200)

        msg = layout.snapshot({}, seq=1)

        self.assertEqual(msg["slots"], {"rpm": 1200})
        self.assertIsNone(layout.set_slot("rpm", 1200))

    def test_snapshot_slots_are_a_copy(self):
        layout = Layout(lambda s: Stack(Slot("rpm")))
        msg = layout.snapshot({}, seq=1)
        layout.set_slot("rpm", 1)
        self.assertEqual(msg["slots"], {})


if __name__ == "__main__":
    unittest.main()
