from __future__ import annotations

from .base import get_assistant_adapter, list_assistant_adapters

# Import concrete adapters so CLI entry points can resolve them by name.
from . import claude_code as _claude_code  # noqa: F401
from . import codex as _codex  # noqa: F401

__all__ = ["get_assistant_adapter", "list_assistant_adapters"]
