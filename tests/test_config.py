"""配置解析测试。"""

from __future__ import annotations

from pathlib import Path

import pytest

from ipgeosearch import config
from ipgeosearch.config import Paths

CONFIG_ENV = (
    "IPGEOSEARCH_DATA_ROOT",
    "IP_UNIFIED_WORKSPACE",
    "IPGEOSEARCH_IP2REGION_ROOT",
    "IP2REGION_ROOT",
    "IPGEOSEARCH_IP_LOCATION_DB_ROOT",
    "IP_LOCATION_DB_ROOT",
    "IPGEOSEARCH_GEOIP2_PYTHON_ROOT",
    "GEOIP2_PYTHON_ROOT",
    "IPGEOSEARCH_GEOIP2_MMDB",
    "GEOIP2_MMDB",
)


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch):
    for name in CONFIG_ENV:
        monkeypatch.delenv(name, raising=False)


def test_data_root_env_drives_all_sub_roots(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("IPGEOSEARCH_DATA_ROOT", str(tmp_path))
    paths = Paths.from_env()
    assert paths.workspace == tmp_path.resolve()
    assert paths.ip2region_root == (tmp_path / "ip2region").resolve()
    assert paths.ip_location_db_root == (tmp_path / "ip-location-db").resolve()
    assert paths.geoip2_python_root == (tmp_path / "GeoIP2-python").resolve()
    assert paths.geoip2_mmdb is None


def test_legacy_workspace_env_still_supported(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("IP_UNIFIED_WORKSPACE", str(tmp_path))
    assert Paths.from_env().workspace == tmp_path.resolve()


def test_specific_roots_override_data_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("IPGEOSEARCH_DATA_ROOT", str(tmp_path))
    monkeypatch.setenv("IPGEOSEARCH_IP2REGION_ROOT", str(tmp_path / "custom"))
    monkeypatch.setenv("IPGEOSEARCH_GEOIP2_MMDB", str(tmp_path / "db.mmdb"))
    paths = Paths.from_env()
    assert paths.ip2region_root == (tmp_path / "custom").resolve()
    assert paths.geoip2_mmdb == (tmp_path / "db.mmdb").resolve()


def test_legacy_specific_roots_supported(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("IP2REGION_ROOT", str(tmp_path / "legacy"))
    assert Paths.from_env().ip2region_root == (tmp_path / "legacy").resolve()


def test_availability_reports_missing_sources(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("IPGEOSEARCH_DATA_ROOT", str(tmp_path))
    (tmp_path / "ip-location-db").mkdir()
    paths = Paths.from_env()
    assert paths.missing_sources() == ["ip2region", "geoip2"]
    assert ("ip-location-db", (tmp_path / "ip-location-db").resolve(), True) in paths.availability()


def test_ip2region_needs_data_directory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("IPGEOSEARCH_DATA_ROOT", str(tmp_path))
    (tmp_path / "ip2region").mkdir()
    assert "ip2region" in Paths.from_env().missing_sources()
    (tmp_path / "ip2region" / "data").mkdir()
    assert "ip2region" not in Paths.from_env().missing_sources()


def test_mmdb_file_satisfies_geoip2_requirement(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("IPGEOSEARCH_DATA_ROOT", str(tmp_path))
    mmdb = tmp_path / "db.mmdb"
    mmdb.write_bytes(b"mmdb")
    monkeypatch.setenv("IPGEOSEARCH_GEOIP2_MMDB", str(mmdb))
    assert "geoip2" not in Paths.from_env().missing_sources()


def test_default_workspace_prefers_directory_with_data(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """不再依赖固定层级：选中真正含数据仓库的目录。"""
    first = tmp_path / "first"
    first.mkdir()
    second = tmp_path / "second"
    (second / "ip-location-db").mkdir(parents=True)
    monkeypatch.setattr(config, "_candidate_workspaces", lambda: [first, second])
    assert config._default_workspace() == second


def test_default_workspace_falls_back_to_parent_of_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    empty = tmp_path / "empty"
    empty.mkdir()
    monkeypatch.setattr(config, "_candidate_workspaces", lambda: [empty])
    package_root = Path(config.__file__).resolve().parent
    assert config._default_workspace() == config._ancestor(package_root, 2)


def test_ancestor_handles_short_paths():
    root = Path(Path.cwd().anchor)
    assert config._ancestor(root, 3) == root
