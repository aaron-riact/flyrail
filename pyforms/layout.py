"""Transport-agnostic layout: handler registry and wire serialization."""
from __future__ import annotations
import copy
from typing import Any, Callable


class Layout:
    """One per session. Bring your own socket/tick.

    This commit covers rendering only: ``render(state)`` deep-copies the
    declarative tree, replaces Python callables with ``{"handlerId": ...}``
    descriptors, and registers the callables for later dispatch.
    Diffing (commit 4) and dispatch/slots (commit 5) build on top.
    """

    def __init__(self, render_fn: Callable[[Any], dict], allowed_types: set[str] | None = None):
        self.render_fn = render_fn
        self.allowed_types = allowed_types
        self.registry: dict[str, Callable] = {}

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
