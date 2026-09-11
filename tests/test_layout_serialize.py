"""Focused tests for Layout.render handler serialization."""
import unittest

from pyforms import Layout, Slot, Stack, Text, Button


class SerializeTest(unittest.TestCase):
    def test_callable_becomes_handler_id(self):
        def stop(state, event):
            state["stopped"] = True

        layout = Layout(lambda s: Stack(Button("Stop", on_click=stop)))
        tree = layout.render({})
        btn = tree["children"][0]
        hid = btn["on_click"]["handlerId"]
        self.assertIs(layout.registry[hid], stop)

    def test_handler_id_embeds_path_and_key(self):
        layout = Layout(lambda s: Stack(Button("A", on_click=lambda s, e: None, key="k1")))
        tree = layout.render({})
        self.assertEqual(tree["children"][0]["on_click"]["handlerId"], "0.0:on_click:k1")

    def test_registry_cleared_per_render(self):
        layout = Layout(lambda s: Stack(Button("A", on_click=lambda s, e: None)))
        first = layout.render({})
        hid = first["children"][0]["on_click"]["handlerId"]
        layout.render({})
        # Same position/key re-registers (fresh closure); stale entries never linger.
        self.assertIn(hid, layout.registry)
        self.assertEqual(len(layout.registry), 1)

    def test_allowlist_rejects_unknown_type(self):
        layout = Layout(
            lambda s: Stack(Button("A", on_click=lambda s, e: None)),
            allowed_types={"Stack", "Text"},
        )
        with self.assertRaises(ValueError):
            layout.render({})

    def test_slot_exempt_from_allowlist(self):
        layout = Layout(lambda s: Stack(Slot("rows")), allowed_types={"Stack"})
        tree = layout.render({})
        self.assertEqual(tree["children"][0]["type"], "__Slot__")

    def test_wire_tree_contains_no_callables(self):
        import json

        layout = Layout(lambda s: Stack(Button("A", on_click=lambda s, e: None)))
        tree = layout.render({})
        json.dumps(tree)  # raises TypeError if a callable leaked onto the wire


if __name__ == "__main__":
    unittest.main()
