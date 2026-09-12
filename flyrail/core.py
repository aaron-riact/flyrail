"""Declarative element constructors. No VDOM dependency."""
from __future__ import annotations
from typing import Any, Callable


def component(fn=None, *, key_arg: str | None = None):
    """Mark a function/class-method as a component. Keeps reactpy feel.
    Usage:
      @component
      def MyPanel(state): ...
      class P:
        @component
        def render(self, state): ...
    """
    def wrap(f):
        f._is_flyrail_component = True
        f._key_arg = key_arg
        return f
    return wrap(fn) if fn else wrap


def pure(fn=None):
    """Opt-in contract: output is a pure function of (arguments, hook slots).

    Declares, not verifies: Layout may skip re-renders when the host version
    is unchanged, and strict mode double-renders to spot-check. Unmarked
    renders always re-render. If you lie, the stale UI is your bug.
    """
    def wrap(f):
        f._flyrail_pure = True
        return f
    return wrap(fn) if fn else wrap


def _opts(event: str, prevent_default: bool, stop_propagation: bool,
          throttle_ms: int | None) -> dict:
    """Per-event wire options. throttleMs is omitted when unset (minimal wire)."""
    opts: dict[str, Any] = {"preventDefault": prevent_default,
                            "stopPropagation": stop_propagation}
    if throttle_ms is not None:
        opts["throttleMs"] = throttle_ms
    return {event: opts}


def _el(type_: str, *children: Any, key: Any = None, on_click: Callable | None = None,
        event_options: dict | None = None, **props: Any) -> dict:
    node: dict[str, Any] = {"type": type_, "props": props}
    if key is not None:
        node["key"] = key
    if children:
        # flatten one level of lists (for [... for ...] splats)
        flat: list[Any] = []
        for c in children:
            if isinstance(c, list):
                flat.extend(c)
            else:
                flat.append(c)
        node["children"] = flat
    if on_click is not None:
        node["on_click"] = on_click
    if event_options:
        node["event_options"] = event_options
    return node


def Stack(*children: Any, key: Any = None, **props: Any) -> dict:
    return _el("Stack", *children, key=key, **props)


def Text(value: str, key: Any = None, **props: Any) -> dict:
    return _el("Text", key=key, value=value, **props)


def Button(label: str, on_click: Callable | None = None, key: Any = None, *,
           prevent_default: bool = True, stop_propagation: bool = False,
           throttle_ms: int | None = None, **props: Any) -> dict:
    return _el("Button", key=key, on_click=on_click,
               event_options=_opts("on_click", prevent_default,
                                   stop_propagation, throttle_ms) if on_click else None,
               label=label, **props)


def TextField(key: Any = None, on_change: Callable | None = None, *,
              prevent_default: bool = True, stop_propagation: bool = False,
              throttle_ms: int | None = None, **props: Any) -> dict:
    node = _el("TextField", key=key, **props)
    if on_change is not None:
        node["on_change"] = on_change
        node["event_options"] = _opts("on_change", prevent_default,
                                      stop_propagation, throttle_ms)
    return node


def Slot(name: str, default: Any = None) -> dict:
    """Hot-path placeholder. Renderer subscribes by name; tick sends slot values
    directly instead of diffing the whole tree."""
    return {"type": "__Slot__", "props": {"name": name, "default": default}}
