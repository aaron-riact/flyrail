"""pyforms - BYOF server-driven UI core.

Python API is reactpy-style but transport/V DOM agnostic:
  - you build dict trees with helpers (Stack, Text, Button, ...)
  - Layout.render(state) replaces callables with {"handlerId": ...} descriptors
"""
from .core import component, Slot, Stack, Text, Button, TextField
from .layout import Layout

__all__ = ["component", "Slot", "Stack", "Text", "Button", "TextField", "Layout"]
