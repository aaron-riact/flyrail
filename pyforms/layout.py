"""Transport-agnostic layout: handler registry, wire serialization, diffing."""
from __future__ import annotations
import copy
import hashlib
import json
from typing import Any, Callable


def _hash(tree: Any) -> str:
    return hashlib.sha256(json.dumps(tree, sort_keys=True, default=str).encode()).hexdigest()


def _escape(path: str) -> str:
    return path.replace("~", "~0").replace("/", "~1")


def _diff(old: Any, new: Any, path: str = "") -> list[dict]:
    """Minimal RFC6902 diff. Dicts recurse; lists replace wholesale (React
    reconciles arrays via `key` client-side, so index patches would be waste).
    Hot per-tick values bypass this entirely via Slots (next commit)."""
    ops: list[dict] = []
    if old == new:
        return ops
    if isinstance(old, dict) and isinstance(new, dict):
        for k in old:
            if k not in new:
                ops.append({"op": "remove", "path": f"{path}/{_escape(k)}" or "/"})
        for k, v in new.items():
            p = f"{path}/{_escape(k)}"
            if k not in old:
                ops.append({"op": "add", "path": p, "value": v})
            else:
                ops.extend(_diff(old[k], v, p))
        return ops
    return [{"op": "replace", "path": path or "/", "value": new}]


class Layout:
    """One per session. Bring your own socket/tick.

    ``render(state)`` serializes callables to ``{"handlerId": ...}``;
    ``diff_and_commit(tree)`` returns RFC6902-ish ops, or ``[]`` when nothing
    changed so the tick loop sends nothing; ``tick(state)`` does both.
    Dispatch/slots follow in the next commit.
    """

    def __init__(self, render_fn: Callable[[Any], dict], allowed_types: set[str] | None = None):
        self.render_fn = render_fn
        self.allowed_types = allowed_types
        self.registry: dict[str, Callable] = {}
        self._last_tree: Any = None
        self._last_hash: str | None = None

    def render(self, state: Any) -> dict:
        self.registry.clear()
        raw = self.render_fn(state)
        tree = copy.deepcopy(raw)
        self._serialize(tree, path="0")
        if self.allowed_types:
            self._check_allowlist(tree)
        return tree

    def _serialize(self, node: Any, path: str) -> None:
        if not isinstance(node, dict):
            return
        key = node.get("key", "")
        for evt in ("on_click", "on_change"):
            fn = node.get(evt)
            if callable(fn):
                # Path keeps ids unique per position; key keeps them stable
                # across list reorders (client reconciles via `key` too).
                hid = f"{path}:{evt}:{key}"
                self.registry[hid] = fn
                node[evt] = {"handlerId": hid}
        for i, c in enumerate(node.get("children", []) or []):
            self._serialize(c, f"{path}.{i}")

    def _check_allowlist(self, node: Any) -> None:
        if isinstance(node, dict):
            t = node.get("type")
            if t not in ("__Slot__",) and t not in (self.allowed_types or set()):
                raise ValueError(f"node type {t!r} not in allowlist")
            for c in node.get("children", []) or []:
                self._check_allowlist(c)

    def diff_and_commit(self, tree: dict) -> list[dict]:
        h = _hash(tree)
        if h == self._last_hash:
            return []
        old = self._last_tree if self._last_tree is not None else {}
        ops = _diff(old, tree, path="")
        self._last_tree = copy.deepcopy(tree)
        self._last_hash = h
        return ops

    def tick(self, state: Any) -> list[dict]:
        """Convenience for fixed-tick loops: render + diff."""
        return self.diff_and_commit(self.render(state))
