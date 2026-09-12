"""Guards docs/how-it-works.md against protocol drift.

Not a style check: asserts every wire token the code emits or consumes is
named in the doc, so renames break loudly instead of rotting silently.
"""
import unittest
from pathlib import Path

DOC = Path(__file__).resolve().parent.parent / "docs" / "how-it-works.md"

WIRE_TOKENS = [
    "patch", "slot", "snapshot", "action", "resync-request",
    "handlerId", "seq", "ops", "tree",
    "applyOps", "invalidate", "use_state", "@pure", "adispatch",
]


class DocsTest(unittest.TestCase):
    def test_doc_exists(self):
        self.assertTrue(DOC.exists(), "docs/how-it-works.md missing")

    def test_wire_tokens_documented(self):
        text = DOC.read_text()
        missing = [t for t in WIRE_TOKENS if t not in text]
        self.assertEqual(missing, [], f"undocumented wire tokens: {missing}")

    def test_diagram_fences_balanced(self):
        text = DOC.read_text()
        self.assertEqual(text.count("```mermaid") >= 5, True,
                         "expected at least 5 diagrams")
        self.assertEqual(text.count("```") % 2, 0, "unbalanced code fences")


if __name__ == "__main__":
    unittest.main()
