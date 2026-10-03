"""GeoIP2 适配器测试（不依赖真实 MMDB 文件）。"""

from __future__ import annotations

from pathlib import Path

from ipgeosearch.geoip2_adapter import GeoIp2Adapter


def test_unconfigured_mmdb_reports_failure(tmp_path: Path):
    """未配置 MMDB 时 ok 必须是 False：README 把 ok 定义为"查询是否成功"，
    前端也按 ok 过滤，之前返回 ok=True 会把"未配置"当成成功结果。"""
    adapter = GeoIp2Adapter(tmp_path, None)
    result = adapter.lookup("8.8.8.8")
    assert result.ok is False
    assert result.data is None
    assert "IPGEOSEARCH_GEOIP2_MMDB" in (result.error or "")


def test_missing_mmdb_file_reports_failure(tmp_path: Path):
    adapter = GeoIp2Adapter(tmp_path, tmp_path / "not-there.mmdb")
    result = adapter.lookup("8.8.8.8")
    assert result.ok is False
    assert "not found" in (result.error or "").lower()


def test_close_is_idempotent(tmp_path: Path):
    adapter = GeoIp2Adapter(tmp_path, None)
    adapter.close()
    adapter.close()
    assert adapter._reader is None


def test_to_plain_truncates_by_depth():
    adapter = GeoIp2Adapter(Path("."), None)

    class Node:
        def __init__(self, depth: int) -> None:
            self.depth = depth
            if depth:
                self.child = Node(depth - 1)

    plain = adapter._to_plain(Node(5), max_depth=2)
    assert isinstance(plain, dict)
    assert plain["depth"] == 5
    # 再往下的层级被截断，不应无限展开
    assert isinstance(plain["child"], dict)
    assert "child" not in plain["child"]
