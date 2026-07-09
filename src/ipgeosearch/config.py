"""Configuration helpers for sibling project integration."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _default_workspace() -> Path:
    return Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class Paths:
    workspace: Path
    ip2region_root: Path
    ip_location_db_root: Path
    geoip2_python_root: Path
    geoip2_mmdb: Path | None

    @classmethod
    def from_env(cls) -> "Paths":
        workspace = Path(os.getenv("IP_UNIFIED_WORKSPACE", _default_workspace())).resolve()
        geoip2_mmdb = os.getenv("GEOIP2_MMDB")
        return cls(
            workspace=workspace,
            ip2region_root=Path(os.getenv("IP2REGION_ROOT", workspace / "ip2region")).resolve(),
            ip_location_db_root=Path(
                os.getenv("IP_LOCATION_DB_ROOT", workspace / "ip-location-db")
            ).resolve(),
            geoip2_python_root=Path(
                os.getenv("GEOIP2_PYTHON_ROOT", workspace / "GeoIP2-python")
            ).resolve(),
            geoip2_mmdb=Path(geoip2_mmdb).resolve() if geoip2_mmdb else None,
        )
