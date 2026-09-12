"""Focused tests for @pure, version-skipping, and strict double-render."""
import unittest

from flyrail import Layout, Stack, Text
from flyrail.core import pure


class PlainPanel:
    """Unmarked render: always re-renders (correct by default)."""

    def __init__(self, fn):
        self.calls = 0
        self._fn = fn

    def render(self, s):
        self.calls += 1
        return self._fn(s)


class PurePanel:
    """@pure render: output is a pure function of arguments."""

    def __init__(self, fn):
        self.calls = 0
        self._fn = fn

    @pure
    def render(self, s):
        self.calls += 1
        return self._fn(s)


class PureContractTest(unittest.TestCase):
    def test_unmarked_always_renders(self):
        p = PlainPanel(lambda s: Stack(Text(f"v={s['v']}")))
        layout = Layout(p.render)
        layout.tick({"v": 1}, version=1)
        layout.tick({"v": 1}, version=1)
        self.assertEqual(p.calls, 2)

    def test_pure_skips_same_version(self):
        p = PurePanel(lambda s: Stack(Text(f"v={s['v']}")))
        layout = Layout(p.render)
        self.assertTrue(layout.tick({"v": 1}, version=1))
        self.assertEqual(layout.tick({"v": 1}, version=1), [])
        self.assertEqual(layout.tick({"v": 1}, version=1), [])
        self.assertEqual(p.calls, 1)

    def test_version_bump_rerenders(self):
        p = PurePanel(lambda s: Stack(Text(f"v={s['v']}")))
        layout = Layout(p.render)
        layout.tick({"v": 1}, version=1)
        layout.tick({"v": 2}, version=2)
        self.assertEqual(p.calls, 2)

    def test_invalidate_forces_render(self):
        p = PurePanel(lambda s: Stack(Text(f"v={s['v']}")))
        layout = Layout(p.render)
        layout.tick({"v": 1}, version=1)
        layout.tick({"v": 1}, version=1)
        layout.invalidate()
        layout.tick({"v": 1}, version=1)
        self.assertEqual(p.calls, 2)

    def test_version_none_always_renders(self):
        p = PurePanel(lambda s: Stack(Text(f"v={s['v']}")))
        layout = Layout(p.render)
        layout.tick({"v": 1})
        layout.tick({"v": 1})
        self.assertEqual(p.calls, 2)

    def test_snapshot_ignores_skip_and_resets_baseline(self):
        p = PurePanel(lambda s: Stack(Text(f"v={s['v']}")))
        layout = Layout(p.render)
        layout.tick({"v": 1}, version=1)
        snap = layout.snapshot({"v": 1}, seq=9)
        self.assertEqual(snap["type"], "snapshot")
        self.assertEqual(p.calls, 2)
        self.assertEqual(layout.tick({"v": 1}, version=1), [])
        self.assertEqual(p.calls, 2)


class StrictModeTest(unittest.TestCase):
    def test_strict_passes_deterministic(self):
        p = PurePanel(lambda s: Stack(Text(f"v={s['v']}")))
        layout = Layout(p.render, strict=True)
        layout.tick({"v": 1}, version=1)
        self.assertEqual(p.calls, 2)  # render + verification pass

    def test_strict_catches_nondeterminism(self):
        n = {"i": 0}

        @pure
        def flaky(s):
            n["i"] += 1
            return Stack(Text(f"i={n['i']}"))

        layout = Layout(flaky, strict=True)
        with self.assertRaises(AssertionError):
            layout.tick({}, version=1)

    def test_strict_ignores_unmarked(self):
        n = {"i": 0}

        def flaky(s):
            n["i"] += 1
            return Stack(Text(f"i={n['i']}"))

        layout = Layout(flaky, strict=True)
        layout.tick({}, version=1)  # no raise: never promised purity


if __name__ == "__main__":
    unittest.main()
