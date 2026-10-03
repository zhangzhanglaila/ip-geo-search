"""Configuration helpers for sibling project integration."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

IP2REGION_DIR = "ip2region"
IP_LOCATION_DB_DIR = "ip-location-db"
GEOIP2_PYTHON_DIR = "GeoIP2-python"
DATA_DIR_NAMES = (IP2REGION_DIR, IP_LOCATION_DB_DIR, GEOIP2_PYTHON_DIR)

# 每个配置项都接受新的 IPGEOSEARCH_ 前缀名，并保留旧名以兼容既有部署脚本。
_ENV_ALIASES: dict[str, tuple[str, ...]] = {
    "data_root": ("IPGEOSEARCH_DATA_ROOT", "IP_UNIFIED_WORKSPACE"),
    "ip2region_root": ("IPGEOSEARCH_IP2REGION_ROOT", "IP2REGION_ROOT"),
    "ip_location_db_root": ("IPGEOSEARCH_IP_LOCATION_DB_ROOT", "IP_LOCATION_DB_ROOT"),
    "geoip2_python_root": ("IPGEOSEARCH_GEOIP2_PYTHON_ROOT", "GEOIP2_PYTHON_ROOT"),
    "geoip2_mmdb": ("IPGEOSEARCH_GEOIP2_MMDB", "GEOIP2_MMDB"),
}


def _read_env(name: str) -> str | None:
    for key in _ENV_ALIASES[name]:
        value = os.getenv(key)
        if value:
            return value
    return None


def _resolve(override: str | None, default: Path) -> Path:
    return Path(override).expanduser().resolve() if override else default.resolve()


def _ancestor(path: Path, level: int) -> Path:
    parents = path.parents
    return parents[level] if len(parents) > level else path


def _candidate_workspaces() -> list[Path]:
    """按优先级列出可能存放数据仓库的目录，去重后返回。"""
    package_root = Path(__file__).resolve().parent
    candidates = [
        _ancestor(package_root, 1),
        _ancestor(package_root, 2),
        _ancestor(package_root, 3),
        Path.cwd(),
    ]
    ordered: list[Path] = []
    for candidate in candidates:
        if candidate not in ordered:
            ordered.append(candidate)
    return ordered


def _default_workspace() -> Path:
    """优先选择真正含有数据仓库的目录，不再依赖固定的目录层级。

    旧实现固定取 `parents[3]`，只在"仓库与数据仓库并排放在同一父目录"时成立；
    容器内该路径会退化为 `/`，导致所有数据源都找不到。
    """
    for candidate in _candidate_workspaces():
        if any((candidate / name).is_dir() for name in DATA_DIR_NAMES):
            return candidate
    return _ancestor(Path(__file__).resolve().parent, 2)


@dataclass(frozen=True)
class Paths:
    workspace: Path
    ip2region_root: Path
    ip_location_db_root: Path
    geoip2_python_root: Path
    geoip2_mmdb: Path | None

    @classmethod
    def from_env(cls) -> "Paths":
        data_root = _read_env("data_root")
        workspace = Path(data_root).expanduser().resolve() if data_root else _default_workspace()
        geoip2_mmdb = _read_env("geoip2_mmdb")
        return cls(
            workspace=workspace,
            ip2region_root=_resolve(_read_env("ip2region_root"), workspace / IP2REGION_DIR),
            ip_location_db_root=_resolve(
                _read_env("ip_location_db_root"), workspace / IP_LOCATION_DB_DIR
            ),
            geoip2_python_root=_resolve(
                _read_env("geoip2_python_root"), workspace / GEOIP2_PYTHON_DIR
            ),
            geoip2_mmdb=Path(geoip2_mmdb).expanduser().resolve() if geoip2_mmdb else None,
        )

    def availability(self) -> list[tuple[str, Path, bool]]:
        """返回各数据源的 (名称, 目录, 是否可用)，用于启动时提示缺失依赖。"""
        return [
            ("ip2region", self.ip2region_root, (self.ip2region_root / "data").is_dir()),
            ("ip-location-db", self.ip_location_db_root, self.ip_location_db_root.is_dir()),
            (
                "geoip2",
                self.geoip2_python_root,
                self.geoip2_python_root.is_dir()
                or bool(self.geoip2_mmdb and self.geoip2_mmdb.exists()),
            ),
        ]

    def missing_sources(self) -> list[str]:
        return [name for name, _, ok in self.availability() if not ok]
