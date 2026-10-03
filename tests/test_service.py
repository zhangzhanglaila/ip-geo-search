"""服务层测试：参数传递、结果结构、缓存行为。

重点是验证"查询参数不再通过改写实例状态传递"——同一实例并发/连续使用不同数据集时
结果不会互相污染。
"""

from __future__ import annotations

from pathlib import Path

from ipgeosearch.config import Paths
from ipgeosearch.models import SourceResult
from ipgeosearch.service import IPGeoSearch


class FakeAdapter:
    def __init__(self, source: str, data: dict | None = None) -> None:
        self.source = source
        self.data = data if data is not None else {"ip": "stub"}
        self.calls: list[tuple] = []
        self.closed = False

    def lookup(self, ip: str) -> SourceResult:
        self.calls.append((ip,))
        return SourceResult(source=self.source, ok=True, data=dict(self.data))

    def lookup_many(self, ip: str, datasets: list[str]) -> SourceResult:
        self.calls.append((ip, tuple(datasets)))
        data = {name: {"country_code": "US"} for name in datasets}
        return SourceResult(source="ip-location-db", ok=True, data=data)

    def available_datasets(self) -> list[str]:
        return ["user-country", "origin-asn"]

    def close(self) -> None:
        self.closed = True


def build_service(tmp_path: Path, **kwargs) -> IPGeoSearch:
    paths = Paths(
        workspace=tmp_path,
        ip2region_root=tmp_path / "ip2region",
        ip_location_db_root=tmp_path / "ip-location-db",
        geoip2_python_root=tmp_path / "GeoIP2-python",
        geoip2_mmdb=None,
    )
    service = IPGeoSearch(paths=paths, csv_datasets=["user-country"], **kwargs)
    service.ip2region = FakeAdapter("ip2region", {"region": "United States|California|0|Cloudflare, Inc.|US"})
    service.ip_location_db = FakeAdapter("ip-location-db")
    service.geoip2 = FakeAdapter("geoip2")
    return service


def test_lookup_returns_all_sources_in_order(tmp_path: Path):
    payload = build_service(tmp_path).lookup("8.8.8.8")
    assert payload["ip"] == "8.8.8.8"
    assert payload["ip_version"] == 4
    assert [item["source"] for item in payload["results"]] == ["ip2region", "ip-location-db", "geoip2"]
    assert payload["risk"]["ipType"] == "CDN / 边缘网络"


def test_lookup_respects_source_filter(tmp_path: Path):
    service = build_service(tmp_path)
    payload = service.lookup("8.8.8.8", sources=["geoip2"])
    assert [item["source"] for item in payload["results"]] == ["geoip2"]
    assert service.ip2region.calls == []


def test_csv_alias_selects_location_db(tmp_path: Path):
    service = build_service(tmp_path)
    payload = service.lookup("8.8.8.8", sources=["csv"])
    assert [item["source"] for item in payload["results"]] == ["ip-location-db"]


def test_datasets_are_passed_per_call(tmp_path: Path):
    service = build_service(tmp_path)
    service.lookup("8.8.8.8", csv_datasets=["origin-asn"])
    assert service.ip_location_db.calls[-1] == ("8.8.8.8", ("origin-asn",))

    service.lookup("8.8.8.8", csv_datasets=["geolite2-city"])
    assert service.ip_location_db.calls[-1] == ("8.8.8.8", ("geolite2-city",))

    # 调用后实例自身的默认数据集不应被改写
    assert service.csv_datasets == ("user-country",)
    service.lookup("9.9.9.9")
    assert service.ip_location_db.calls[-1] == ("9.9.9.9", ("user-country",))


def test_cache_avoids_repeated_adapter_calls(tmp_path: Path):
    service = build_service(tmp_path)
    first = service.lookup("8.8.8.8")
    second = service.lookup("8.8.8.8")
    assert len(service.ip2region.calls) == 1
    assert first == second
    assert first is not second


def test_cache_key_includes_datasets(tmp_path: Path):
    service = build_service(tmp_path)
    service.lookup("8.8.8.8", csv_datasets=["user-country"])
    service.lookup("8.8.8.8", csv_datasets=["origin-asn"])
    assert len(service.ip_location_db.calls) == 2


def test_cache_can_be_disabled(tmp_path: Path):
    service = build_service(tmp_path, cache_ttl=0)
    service.lookup("8.8.8.8")
    service.lookup("8.8.8.8")
    assert len(service.ip2region.calls) == 2


def test_cache_is_bounded(tmp_path: Path):
    service = build_service(tmp_path, cache_max_entries=1, cache_ttl=60)
    service.lookup("8.8.8.8")
    service.lookup("1.1.1.1")
    service.lookup("8.8.8.8")
    assert len(service.ip2region.calls) == 3


def test_clear_cache(tmp_path: Path):
    service = build_service(tmp_path)
    service.lookup("8.8.8.8")
    service.clear_cache()
    service.lookup("8.8.8.8")
    assert len(service.ip2region.calls) == 2


def test_available_datasets_delegates(tmp_path: Path):
    assert build_service(tmp_path).available_csv_datasets() == ["user-country", "origin-asn"]


def test_close_closes_adapters(tmp_path: Path):
    service = build_service(tmp_path)
    service.close()
    assert service.ip2region.closed is True
    assert service.geoip2.closed is True


def test_lookup_rejects_invalid_ip(tmp_path: Path):
    import pytest

    with pytest.raises(ValueError):
        build_service(tmp_path).lookup("not-an-ip")
