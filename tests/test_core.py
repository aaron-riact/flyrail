"""Focused tests for pyforms.core element constructors."""
import unittest

from pyforms.core import Slot, Stack, Text, Button, TextField, component


class ComponentMarkerTest(unittest.TestCase):
    def test_bare_decorator_marks_function(self):
        @component
        def MyPanel(state):
            ...

        self.assertTrue(MyPanel._is_pyforms_component)

    def test_parametrized_decorator_keeps_key_arg(self):
        @component(key_arg="id")
        def Other(state):
            ...

        self.assertTrue(Other._is_pyforms_component)
        self.assertEqual(Other._key_arg, "id")


class ConstructorsTest(unittest.TestCase):
    def test_text_shape(self):
        self.assertEqual(Text("hi"), {"type": "Text", "props": {"value": "hi"}})

    def test_key_attaches(self):
        self.assertEqual(Text("x", key="a1")["key"], "a1")

    def test_absent_key_and_children_stay_absent(self):
        node = Button("Save")
        self.assertNotIn("children", node)
        self.assertNotIn("key", node)

    def test_children_flatten_one_level(self):
        node = Stack(Text("z"), [Text("a"), Text("b")])
        self.assertEqual(len(node["children"]), 3)

    def test_on_click_kept_as_callable(self):
        # Serialization to handlerIds is Layout's job (commit 3); core
        # must not stringify callables.
        fn = lambda s, e: None  # noqa: E731
        self.assertIs(Button("Stop", on_click=fn)["on_click"], fn)

    def test_textfield_on_change_and_props(self):
        fn = lambda s, e: None  # noqa: E731
        node = TextField(on_change=fn, label="Email")
        self.assertIs(node["on_change"], fn)
        self.assertEqual(node["props"], {"label": "Email"})

    def test_slot_shape(self):
        self.assertEqual(
            Slot("rows", default=[]),
            {"type": "__Slot__", "props": {"name": "rows", "default": []}},
        )


if __name__ == "__main__":
    unittest.main()
