"""Focused tests for Layout diffing and tick suppression."""
import unittest

from pyforms import Layout, Stack, Text


class DiffTest(unittest.TestCase):
    def test_first_tick_emits(self):
        layout = Layout(lambda s: Stack(Text(f"speed: {s['speed']}")))
        self.assertTrue(layout.tick({"speed": 1}))

    def test_unchanged_tick_sends_nothing(self):
        layout = Layout(lambda s: Stack(Text(f"speed: {s['speed']}")))
        layout.tick({"speed": 1})
        self.assertEqual(layout.tick({"speed": 1}), [])

    def test_changed_leaf_replaces_children_wholesale(self):
        # Arrays patch by replace, never by index: React reconciles via `key`
        # client-side, so index ops would be pure overhead. Pin that here.
        layout = Layout(lambda s: Stack(Text(s["label"])))
        layout.tick({"label": "a"})
        ops = layout.tick({"label": "b"})
        self.assertEqual(len(ops), 1)
        self.assertEqual(ops[0]["op"], "replace")
        self.assertEqual(ops[0]["path"], "/children")

    def test_reorder_is_single_replace(self):
        layout = Layout(lambda s: Stack(*[Text(n, key=n) for n in s["items"]]))
        layout.tick({"items": ["a", "b"]})
        ops = layout.tick({"items": ["b", "a"]})
        self.assertEqual(len(ops), 1)
        self.assertEqual(ops[0]["op"], "replace")

    def test_ops_are_json_serializable(self):
        import json

        layout = Layout(lambda s: Stack(Text(f"speed: {s['speed']}")))
        ops = layout.tick({"speed": 1})
        json.dumps(ops)


if __name__ == "__main__":
    unittest.main()
