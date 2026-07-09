"""Optional adapter for MaxMind GeoIP2 MMDB files."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from .models import SourceResult


class GeoIp2Adapter:
    def __init__(self, geoip2_python_root: Path, mmdb_path: Path | None) -> None:
        self.geoip2_python_root = geoip2_python_root
        self.mmdb_path = mmdb_path
        self._reader = None

    def lookup(self, ip: str) -> SourceResult:
        if self.mmdb_path is None:
            return SourceResult(
                source="geoip2",
                ok=True,
                data=None,
                error="GEOIP2_MMDB is not configured",
            )

        try:
            reader = self._get_reader()
            for method in ("city", "country", "asn"):
                func = getattr(reader, method, None)
                if not func:
                    continue
                try:
                    response = func(ip)
                    return SourceResult(
                        source="geoip2",
                        ok=True,
                        data={"method": method, "record": self._to_plain(response)},
                    )
                except Exception:
                    continue
            return SourceResult(source="geoip2", ok=True, data=None)
        except Exception as exc:
            return SourceResult(source="geoip2", ok=False, error=str(exc))

    def close(self) -> None:
        if self._reader is not None:
            self._reader.close()
            self._reader = None

    def _get_reader(self) -> object:
        if self._reader is not None:
            return self._reader

        src = self.geoip2_python_root / "src"
        if src.exists():
            sys.path.insert(0, str(src))

        import geoip2.database

        if self.mmdb_path is None or not self.mmdb_path.exists():
            raise FileNotFoundError(f"GeoIP2 MMDB file not found: {self.mmdb_path}")

        self._reader = geoip2.database.Reader(str(self.mmdb_path))
        return self._reader

    def _to_plain(self, value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, (list, tuple)):
            return [self._to_plain(item) for item in value]
        if isinstance(value, dict):
            return {str(key): self._to_plain(item) for key, item in value.items()}

        attrs = {}
        for name in dir(value):
            if name.startswith("_"):
                continue
            try:
                item = getattr(value, name)
            except Exception:
                continue
            if callable(item):
                continue
            if isinstance(item, (str, int, float, bool, dict, list, tuple)) or item is None:
                attrs[name] = self._to_plain(item)
        return attrs
