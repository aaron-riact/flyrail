"""Guards docs/how-it-works.md against protocol drift.

Not a style check: asserts every wire token the code emits or consumes is
named in the doc, so renames break loudly instead of rotting silently.
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOC = ROOT / "docs" / "how-it-works.md"
README = ROOT / "README.md"

WIRE_TOKENS = [
    "patch", "slot", "snapshot", "action", "resync-request",
    "handlerId", "seq", "ops", "tree",
    "applyOps", "invalidate", "use_state", "@pure", "adispatch",
    "use_effect", "use_memo", "memoisation", "identity",
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


class ReadmeQuickstartTest(unittest.TestCase):
    """Runs the README's Python quickstart, because people copy it."""

    def quickstart(self):
        text = README.read_text()
        block = re.search(r"## Python quickstart\n\n```python\n(.*?)```", text, re.S)
        self.assertIsNotNone(block, "README Python quickstart not found")
        sent = []
        scope = {"broadcast": sent.append}
        exec(block.group(1), scope)
        return scope, sent

    def test_every_message_after_a_resync_is_accepted(self):
        """The store drops any patch whose seq is not above the last one it
        saw, snapshots included. A snapshot that reuses the next patch's seq
        makes the client discard that patch and silently fall out of step."""
        scope, sent = self.quickstart()

        class State:
            speed = 1

        state = State()
        scope["on_tick"](state)
        scope["on_ws"]({"chan": "ui", "type": "resync-request"}, state)
        state.speed = 2
        scope["on_tick"](state)

        seqs = [msg["seq"] for msg in sent]
        self.assertEqual([m["type"] for m in sent], ["patch", "snapshot", "patch"])
        self.assertEqual(seqs, sorted(set(seqs)), f"seq not strictly rising: {seqs}")


class JsImportTest(unittest.TestCase):
    """Every documented flyrail-renderer import names something that entry
    point exports, so a copied snippet does not fail on its first line."""

    def test_documented_imports_resolve(self):
        import json

        pkg = ROOT / "js"
        exports = json.loads((pkg / "package.json").read_text())["exports"]
        sources = [README, pkg / "README.md", pkg / "ServerNode.tsx",
                   *sorted((ROOT / "docs").glob("*.md"))]
        pattern = re.compile(
            r"import\s*\{([^}]*)\}\s*from\s*['\"]flyrail-renderer(/[\w-]+)?['\"]")
        checked = 0
        for source in sources:
            for names, sub in pattern.findall(source.read_text()):
                target = pkg / exports["." + (sub or "")]
                code = target.read_text()
                for name in (n.split(" as ")[0].strip() for n in names.split(",")):
                    if not name:
                        continue
                    checked += 1
                    exported = re.search(
                        rf"export\s+(async\s+)?(function|const|let|class)\s+{name}\b", code)
                    self.assertTrue(
                        exported, f"{source.name}: {name!r} is not exported by "
                                  f"flyrail-renderer{sub} ({target.name})")
        self.assertGreater(checked, 0, "no documented imports found")


if __name__ == "__main__":
    unittest.main()
