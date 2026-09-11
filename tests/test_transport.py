"""Focused tests for transport envelope helpers."""
import unittest

from pyforms.transport import ui_envelope_patch


class EnvelopeTest(unittest.TestCase):
    def test_patch_envelope_shape(self):
        ops = [{"op": "replace", "path": "/children", "value": []}]
        self.assertEqual(
            ui_envelope_patch(ops, seq=7),
            {"chan": "ui", "type": "patch", "seq": 7, "ops": ops},
        )

    def test_seq_orders_patches(self):
        self.assertLess(
            ui_envelope_patch([], seq=1)["seq"],
            ui_envelope_patch([], seq=2)["seq"],
        )


if __name__ == "__main__":
    unittest.main()
