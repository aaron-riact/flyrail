"""pyforms - BYOF server-driven UI core.

Python API is reactpy-style but transport/V DOM agnostic:
  - you build dict trees with helpers (Stack, Text, Button, ...)
  - callables in on_click stay in Python (Layout serializes them later)
"""
from .core import component, Slot, Stack, Text, Button, TextField

__all__ = ["component", "Slot", "Stack", "Text", "Button", "TextField"]
