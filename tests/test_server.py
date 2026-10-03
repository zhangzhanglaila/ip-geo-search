"""HTTP 接口集成测试：真实启动服务并走完整请求链路。"""

from __future__ import annotations

import http.client
import json
import threading
import urllib.error
import urllib.request
from collections.abc import Iterator
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from ipgeosearch import http_app
from ipgeosearch import server as server_module
from ipgeosearch.config import Paths
from ipgeosearch.models import SourceResult
from ipgeosearch.service import IPGeoSearch


class StubAdapter:
    def __init__(self, source: str, data: dict | None = None) -> None:
        self.source = source
        self.data = data if data is not None else {}

    def lookup(self, ip: str) -> SourceResult:
        return SourceResult(source=self.source, ok=True, data=dict(self.data))

    def lookup_many(self, ip: str, datasets: list[str]) -> SourceResult:
        data = {name: {"country_code": "US"} for name in datasets}
        return SourceResult(source="ip-location-db", ok=True, data=data)

    def available_datasets(self) -> list[str]:
        return ["user-country", "origin-asn"]

    def close(self) -> None:
        return None


@pytest.fixture()
def base_url(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    paths = Paths(
        workspace=tmp_path,
        ip2region_root=tmp_path / "ip2region",
        ip_location_db_root=tmp_path / "ip-location-db",
        geoip2_python_root=tmp_path / "GeoIP2-python",
        geoip2_mmdb=None,
    )
    service = IPGeoSearch(paths=paths, csv_datasets=["user-country"], cache_ttl=0)
    service.ip2region = StubAdapter("ip2region", {"region": "United States|California|0|Cloudflare, Inc.|US"})
    service.ip_location_db = StubAdapter("ip-location-db")
    service.geoip2 = StubAdapter("geoip2")

    # 反向 DNS 与 DNSBL 会走外网，测试里替换成固定结果
    # （补丁打在 http_app 上，即实际调用点）
    monkeypatch.setattr(
        http_app,
        "reverse_lookup",
        lambda ip: {"ip": ip, "hostname": "dns.example", "aliases": [], "addresses": []},
    )
    monkeypatch.setattr(
        http_app,
        "dnsbl_lookup",
        lambda ip: {"checked": True, "server": "test", "matches": [], "errors": {}},
    )
    monkeypatch.delenv("IPGEOSEARCH_API_KEY", raising=False)
    monkeypatch.delenv("IPGEOSEARCH_TMAP_KEY", raising=False)

    previous = server_module.LookupHandler.service
    server_module.LookupHandler.service = service
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server_module.LookupHandler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{httpd.server_address[1]}"
    finally:
        httpd.shutdown()
        httpd.server_close()
        server_module.LookupHandler.service = previous


def get_json(url: str, api_key: str | None = None) -> tuple[int, dict]:
    request = urllib.request.Request(url)
    if api_key:
        request.add_header("X-API-Key", api_key)
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read().decode("utf-8"))


def get_status(base_url: str, path: str) -> int:
    """只看状态码，不解析响应体（静态资源可能返回 HTML）。"""
    try:
        with urllib.request.urlopen(f"{base_url}{path}", timeout=10) as response:
            return response.status
    except urllib.error.HTTPError as error:
        return error.code


def test_health(base_url: str):
    status, payload = get_json(f"{base_url}/health")
    assert status == 200
    assert payload == {"ok": True}


def test_lookup_returns_results_and_risk(base_url: str):
    status, payload = get_json(f"{base_url}/lookup?ip=8.8.8.8")
    assert status == 200
    assert payload["ip_version"] == 4
    assert [item["source"] for item in payload["results"]] == ["ip2region", "ip-location-db", "geoip2"]
    assert payload["risk"]["ipType"] == "CDN / 边缘网络"
    assert payload["risk"]["level"] in {"low", "medium", "high"}


def test_lookup_requires_ip(base_url: str):
    status, payload = get_json(f"{base_url}/lookup")
    assert status == 400
    assert "missing ip" in payload["error"]


def test_lookup_rejects_bad_ip(base_url: str):
    status, payload = get_json(f"{base_url}/lookup?ip=999.999.999.999")
    assert status == 400
    assert payload["error"]


def test_lookup_honours_source_parameter(base_url: str):
    _, payload = get_json(f"{base_url}/lookup?ip=8.8.8.8&source=geoip2")
    assert [item["source"] for item in payload["results"]] == ["geoip2"]


def test_intel_embeds_lookup_result(base_url: str):
    status, payload = get_json(f"{base_url}/intel?ip=8.8.8.8")
    assert status == 200
    assert [item["source"] for item in payload["lookup"]["results"]] == ["ip2region", "ip-location-db", "geoip2"]
    assert payload["reverseDns"]["hostname"] == "dns.example"
    assert payload["dnsbl"]["checked"] is True
    assert set(payload["privacy"]) == {
        "flags",
        "score",
        "level",
        "summary",
        "tags",
        "ipType",
        "proxyLike",
        "serverLike",
        "abuseLike",
    }


def test_intel_requires_valid_ip(base_url: str):
    assert get_status(base_url, "/intel") == 400
    assert get_status(base_url, "/intel?ip=nope") == 400


def test_datasets_endpoint(base_url: str):
    status, payload = get_json(f"{base_url}/datasets")
    assert status == 200
    assert payload == {"datasets": ["user-country", "origin-asn"]}


def test_map_config_without_key(base_url: str):
    status, payload = get_json(f"{base_url}/map-config")
    assert status == 200
    assert payload == {"provider": "tencent", "key": "", "configured": False}


def test_map_config_with_key(base_url: str, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("IPGEOSEARCH_TMAP_KEY", "demo-key")
    _, payload = get_json(f"{base_url}/map-config")
    assert payload["configured"] is True
    assert payload["key"] == "demo-key"


def test_unknown_path_returns_404(base_url: str):
    assert get_status(base_url, "/nope") == 404


def test_security_headers_are_present(base_url: str):
    with urllib.request.urlopen(f"{base_url}/health", timeout=10) as response:
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert response.headers["Referrer-Policy"] == "no-referrer"
        assert response.headers["X-Frame-Options"] == "DENY"


def test_static_assets_support_etag_revalidation(base_url: str):
    request = urllib.request.Request(f"{base_url}/static/app.js")
    with urllib.request.urlopen(request, timeout=10) as response:
        etag = response.headers["ETag"]
        assert etag
    assert response.headers["Cache-Control"] == "no-cache"

    conditional = urllib.request.Request(f"{base_url}/static/app.js", headers={"If-None-Match": etag})
    try:
        with urllib.request.urlopen(conditional, timeout=10) as response:
            raise AssertionError("应返回 304")
    except urllib.error.HTTPError as error:
        assert error.code == 304


def test_access_log_can_be_disabled(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]):
    """访问日志默认打开，可用 IPGEOSEARCH_ACCESS_LOG=0 关掉。"""
    handler = object.__new__(server_module.LookupHandler)
    handler.client_address = ("127.0.0.1", 1234)

    monkeypatch.delenv("IPGEOSEARCH_ACCESS_LOG", raising=False)
    handler.log_message("GET %s", "/health")
    assert "GET /health" in capsys.readouterr().err

    monkeypatch.setenv("IPGEOSEARCH_ACCESS_LOG", "0")
    handler.log_message("GET %s", "/health")
    assert "GET /health" not in capsys.readouterr().err


def test_index_and_static_assets(base_url: str):
    assert get_status(base_url, "/") == 200
    assert get_status(base_url, "/static/app.js") == 200
    assert get_status(base_url, "/static/styles.css") == 200
    assert get_status(base_url, "/static/assets/china-coordinates.json") == 200
    assert get_status(base_url, "/static/missing.js") == 404


def test_raw_traversal_paths_are_rejected(base_url: str):
    """用 http.client 发送未规范化的原始路径，绕开 urllib 的客户端归一化。"""
    host, port = base_url.removeprefix("http://").split(":")
    for raw_path in ("/static/../README.md", "/static/..%2f..%2fREADME.md", "/static/%2e%2e/README.md"):
        connection = http.client.HTTPConnection(host, int(port), timeout=10)
        try:
            connection.putrequest("GET", raw_path, skip_accept_encoding=True)
            connection.endheaders()
            response = connection.getresponse()
            assert response.status == 404, raw_path
        finally:
            connection.close()


def test_api_key_protection(base_url: str, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("IPGEOSEARCH_API_KEY", "secret")

    assert get_status(base_url, "/health") == 200
    assert get_status(base_url, "/auth-config") == 200
    assert get_status(base_url, "/lookup?ip=8.8.8.8") == 401

    status, _ = get_json(f"{base_url}/lookup?ip=8.8.8.8", api_key="secret")
    assert status == 200

    status, _ = get_json(f"{base_url}/lookup?ip=8.8.8.8&api_key=secret")
    assert status == 200


def test_auth_config_reports_requirement(base_url: str, monkeypatch: pytest.MonkeyPatch):
    _, payload = get_json(f"{base_url}/auth-config")
    assert payload == {"apiKeyRequired": False}
    monkeypatch.setenv("IPGEOSEARCH_API_KEY", "secret")
    _, payload = get_json(f"{base_url}/auth-config")
    assert payload == {"apiKeyRequired": True}


IP_ENDPOINTS = ("/lookup", "/rdap", "/reverse-dns", "/intel")


@pytest.mark.parametrize("path", IP_ENDPOINTS)
def test_ip_endpoints_share_missing_ip_message(base_url: str, path: str):
    """P2-1：`?ip=` 型接口共用同一套入参校验，文案也一致。"""
    status, payload = get_json(f"{base_url}{path}")
    assert status == 400
    assert payload["error"] == "missing ip query parameter"


@pytest.mark.parametrize("path", IP_ENDPOINTS)
def test_ip_endpoints_share_invalid_ip_message(base_url: str, path: str):
    status, payload = get_json(f"{base_url}{path}?ip=nope")
    assert status == 400
    assert payload["error"] == "invalid ip"


def test_dns_rejects_literal_ip_but_resolve_accepts_it(base_url: str):
    """`/dns` 只接受域名，`/resolve` 两者都接受 —— 由 host_endpoint 的开关决定。"""
    status, payload = get_json(f"{base_url}/dns?host=1.2.3.4")
    assert status == 400
    assert payload["error"] == "dns query expects a hostname"

    status, payload = get_json(f"{base_url}/resolve?host=1.2.3.4")
    assert status == 200
    assert payload == {"host": "1.2.3.4", "addresses": ["1.2.3.4"]}


@pytest.mark.parametrize("path", ("/dns", "/resolve"))
def test_host_endpoints_share_validation(base_url: str, path: str):
    status, payload = get_json(f"{base_url}{path}")
    assert status == 400
    assert payload["error"] == "missing host query parameter"

    status, payload = get_json(f"{base_url}{path}?host=bad..host")
    assert status == 400
    assert payload["error"] == "invalid hostname"


def test_route_table_covers_every_documented_endpoint():
    """路由表是唯一入口，避免新增接口只加了方法却忘了注册。"""
    assert set(server_module.LookupHandler.ROUTES) == {
        "/health",
        "/map-config",
        "/datasets",
        "/lookup",
        "/resolve",
        "/dns",
        "/rdap",
        "/reverse-dns",
        "/intel",
        "/probe",
    }
    for handler_name in server_module.LookupHandler.ROUTES.values():
        assert callable(getattr(server_module.LookupHandler, handler_name))
