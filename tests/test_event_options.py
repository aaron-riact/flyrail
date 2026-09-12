"""Focused tests for event-option descriptors and safe defaults."""
import unittest

from flyrail import Layout, Stack, Button, TextField


class DefaultsTest(unittest.TestCase):
    def test_click_defaults_prevent_reload(self):
        layout = Layout(lambda s: Stack(Button("Save", on_click=lambda s, e: None)))
        btn = layout.render({})["children"][0]
        self.assertEqual(btn["on_click"]["preventDefault"], True)
        self.assertEqual(btn["on_click"]["stopPropagation"], False)
        self.assertNotIn("throttleMs", btn["on_click"])

    def test_change_defaults_match(self):
        layout = Layout(
            lambda s: Stack(TextField(on_change=lambda s, e: None, key="q"))
        )
        field = layout.render({})["children"][0]
        self.assertEqual(field["on_change"]["preventDefault"], True)
        self.assertNotIn("throttleMs", field["on_change"])

    def test_opt_outs_honored(self):
        layout = Layout(lambda s: Stack(Button(
            "Go", on_click=lambda s, e: None,
            prevent_default=False, stop_propagation=True, throttle_ms=200,
        )))
        desc = layout.render({})["children"][0]["on_click"]
        self.assertEqual(desc["preventDefault"], False)
        self.assertEqual(desc["stopPropagation"], True)
        self.assertEqual(desc["throttleMs"], 200)

    def test_hand_built_trees_get_safe_defaults(self):
        # Nodes assembled without constructors still serialize safely.
        layout = Layout(lambda s: {"type": "Button",
                                   "props": {"label": "X"},
                                   "on_click": lambda s, e: None})
        desc = layout.render({})["on_click"]
        self.assertEqual(
            desc, {"handlerId": desc["handlerId"],
                   "preventDefault": True, "stopPropagation": False})

    def test_options_do_not_leak_into_props(self):
        layout = Layout(lambda s: Stack(Button("Save", on_click=lambda s, e: None)))
        btn = layout.render({})["children"][0]
        self.assertNotIn("prevent_default", btn["props"])
        self.assertNotIn("event_options", btn.get("children", {}))


if __name__ == "__main__":
    unittest.main()
