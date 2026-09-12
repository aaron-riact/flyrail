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


#: Wire defaults for event descriptors. preventDefault is True because a
#: socket-driven control must never trigger browser navigation (reload =
#: dead session); opt out explicitly with prevent_default=False. Shape
#: mirrors reactpy's eventHandlers entries for cross-compat.
EVENT_DEFAULTS = {"preventDefault": True, "stopPropagation": False}


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
    ``dispatch(handlerId, state, event)`` routes client actions back to the
    registered Python callable; ``set_slot(name, value)`` pushes hot per-tick
    values past the diff entirely.
    """

    def __init__(self, render_fn: Callable[[Any], dict], allowed_types: set[str] | None = None,
                 strict: bool = False):
        self.render_fn = render_fn
        self.allowed_types = allowed_types
        self.strict = strict
        self.registry: dict[str, Callable] = {}
        self._last_tree: Any = None
        self._last_hash: str | None = None
        self._slots: dict[str, Any] = {}
        self._version: Any = None
        self._dirty = True

    def invalidate(self) -> None:
        """Mark dirty: the next tick() re-renders regardless of version.
        Scheduling seam for hook dispatch and the future Driver."""
        self._dirty = True

    def render(self, state: Any) -> dict:
        self.registry.clear()
        raw = self.render_fn(state)
        tree = copy.deepcopy(raw)
        self._serialize(tree, path="0")
        if self.allowed_types:
            self._check_allowlist(tree)
        if self.strict and getattr(self.render_fn, "_flyrail_pure", False):
            self._check_deterministic(state, tree)
        self._dirty = False
        return tree

    def _check_deterministic(self, state: Any, first: dict) -> None:
        # Compare serialized trees: raw trees hold fresh closures per render
        # (identity-unequal by construction), while handlerIds are
        # deterministic. Second pass overwrites identical registry entries.
        again = copy.deepcopy(self.render_fn(state))
        self._serialize(again, path="0")
        if again != first:
            raise AssertionError(
                "render_fn marked @pure produced different trees across two "
                "immediate renders; remove @pure or eliminate the "
                "nondeterminism (time, random, counters, unversioned reads)")

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
                node[evt] = {"handlerId": hid,
                             **{**EVENT_DEFAULTS,
                                **node.get("event_options", {}).get(evt, {})}}
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

    def tick(self, state: Any, version: Any = None) -> list[dict]:
        """Render + diff. Pure renders skip render CPU when the host version
        matches the last rendered version and nothing invalidated since.
        Unmarked renders always re-render (correct by default)."""
        if (version is not None
                and version == self._version
                and not self._dirty
                and getattr(self.render_fn, "_flyrail_pure", False)):
            return []
        tree = self.render(state)
        self._version = version
        return self.diff_and_commit(tree)

    def snapshot(self, state: Any, seq: int) -> dict:
        """Full-tree recovery message answering a client resync-request.

        Re-renders, re-registers handlers, and resets the diff baseline so
        subsequent ticks stay incremental from the snapshot point.
        """
        tree = self.render(state)
        self._last_tree = copy.deepcopy(tree)
        self._last_hash = _hash(tree)
        return {"chan": "ui", "type": "snapshot", "seq": seq, "tree": tree}

    def dispatch(self, handler_id: str, state: Any, event: Any = None) -> None:
        fn = self.registry.get(handler_id)
        if fn is None:
            raise KeyError(f"unknown handler {handler_id!r}")
        fn(state, event)

    def set_slot(self, name: str, value: Any) -> dict | None:
        """Hot path bypassing the diff: unchanged values return None."""
        h = _hash(value)
        if self._slots.get(name, {}).get("hash") == h:
            return None
        self._slots[name] = {"hash": h, "value": value}
        return {"chan": "ui", "type": "slot", "name": name, "value": value}
