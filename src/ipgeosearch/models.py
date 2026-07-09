"""Shared result models."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SourceResult:
    source: str
    ok: bool
    data: Any = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "ok": self.ok,
            "data": self.data,
            "error": self.error,
        }
