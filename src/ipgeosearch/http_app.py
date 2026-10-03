"""HTTP 层：路由分发、入参校验、静态资源与鉴权。

只负责"把请求翻译成函数调用、把结果写成响应"，具体能力（查询数据源、DNS、
RDAP、端口探测）分别由 service / dns / rdap / probe 提供。

入参校验统一由 `ip_endpoint` 与 `host_endpoint` 两个装饰器承担，
原先每个 `_send_*` 方法自带一份"取参 → 判空 → 判格式 → 400"的样板。
"""

from __future__ import annotations

import functools
import hmac
import json
import mimetypes
import os
import socket
import sys
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from . import scoring
from .dns import dnsbl_lookup, resolve_records, reverse_lookup
from .probe import probe_target
from .rdap import lookup as rdap_lookup
from .service import IPGeoSearch
from .targets import is_literal_ip, is_valid_hostname, normalize_host, parse_ip

STATIC_ROOT = Path(__file__).resolve().parent / "static"
REQUEST_TIMEOUT_SECONDS = 15.0
ACCESS_LOG_ENV = "IPGEOSEARCH_ACCESS_LOG"

# 未启用 API Key 时这些路径无需鉴权；/auth-config 需要保持可访问，
# 前端要先问"要不要密钥"才能决定是否提示输入。
PUBLIC_PATHS = {"", "/", "/health", "/auth-config"}
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "X-Frame-Options": "DENY",
}

Query = dict[str, list[str]]
Endpoint = Callable[..., None]


def access_log_enabled() -> bool:
    return os.getenv(ACCESS_LOG_ENV, "1").strip().lower() not in {"0", "false", "no", "off"}


def resolve_static_path(url_path: str) -> Path | None:
    """把 /static/... 映射到 STATIC_ROOT 下的真实文件；非法路径返回 None。

    字符串前缀比较无法区分目录与同前缀的兄弟目录，所以这里同时做路径段级
    校验（拒绝 . / .. / 反斜杠）与目录归属判断。
    """
    if not url_path.startswith("/static/"):
        return None
    relative = unquote(url_path).removeprefix("/static/")
    parts = [part for part in relative.split("/") if part not in ("", ".")]
    if not parts or ".." in parts or "\\" in relative:
        return None

    try:
        resolved = STATIC_ROOT.joinpath(*parts).resolve()
    except OSError:
        return None
    return resolved if resolved.is_relative_to(STATIC_ROOT.resolve()) else None


def ip_endpoint(method: Endpoint) -> Endpoint:
    """`?ip=` 型接口的统一入口校验，把解析好的 ipaddress 对象交给实现。"""

    @functools.wraps(method)
    def wrapper(self: LookupHandler, query: Query) -> None:
        raw = query.get("ip", [""])[0]
        if not raw:
            self._send_json({"error": "missing ip query parameter"}, status=400)
            return
        try:
            parsed = parse_ip(raw)
        except ValueError:
            self._send_json({"error": "invalid ip"}, status=400)
            return
        method(self, parsed, query)

    return wrapper


def host_endpoint(allow_ip: bool) -> Callable[[Endpoint], Endpoint]:
    """`?host=` 型接口的统一入口校验；`allow_ip=False` 时拒绝 IP 字面量。"""

    def decorator(method: Endpoint) -> Endpoint:
        @functools.wraps(method)
        def wrapper(self: LookupHandler, query: Query) -> None:
            host = normalize_host(query.get("host", [""])[0])
            if not host:
                self._send_json({"error": "missing host query parameter"}, status=400)
                return
            if is_literal_ip(host):
                if not allow_ip:
                    self._send_json({"error": "dns query expects a hostname"}, status=400)
                    return
            elif not is_valid_hostname(host):
                self._send_json({"error": "invalid hostname"}, status=400)
                return
            method(self, host, query)

        return wrapper

    return decorator


class LookupHandler(BaseHTTPRequestHandler):
    service = IPGeoSearch()
    # 读取请求的超时时间，避免慢速连接长期占用线程。
    timeout = REQUEST_TIMEOUT_SECONDS

    # 路径到处理方法的映射，新增接口只需加一行。
    ROUTES: dict[str, str] = {
        "/health": "_send_health",
        "/map-config": "_send_map_config",
        "/datasets": "_send_datasets",
        "/lookup": "_send_lookup",
        "/resolve": "_send_resolve",
        "/dns": "_send_dns",
        "/rdap": "_send_rdap",
        "/reverse-dns": "_send_reverse_dns",
        "/intel": "_send_intel",
        "/probe": "_send_probe",
    }

    # --- 路由 ---------------------------------------------------------------

    def do_GET(self) -> None:
        parsed = urlparse(self.path)

        if parsed.path in ("", "/"):
            self._send_file(STATIC_ROOT / "index.html")
            return

        if parsed.path.startswith("/static/"):
            static_file = resolve_static_path(parsed.path)
            if static_file is None:
                self._send_json({"error": "not found"}, status=404)
                return
            self._send_file(static_file)
            return

        if parsed.path == "/auth-config":
            self._send_json({"apiKeyRequired": bool(os.getenv("IPGEOSEARCH_API_KEY", ""))})
            return

        query = parse_qs(parsed.query)
        if self._requires_auth(parsed.path) and not self._is_authorized(query):
            self._send_json({"error": "unauthorized"}, status=401)
            return

        handler_name = self.ROUTES.get(parsed.path)
        if handler_name is None:
            self._send_json({"error": "not found"}, status=404)
            return
        getattr(self, handler_name)(query)

    def log_message(self, format: str, *args: object) -> None:
        if access_log_enabled():
            sys.stderr.write(f"{self.address_string()} - {format % args}\n")

    # --- 入参辅助 -----------------------------------------------------------

    def _lookup_options(self, query: Query) -> dict[str, list[str] | None]:
        """把请求里的数据源/数据集参数整理成 service.lookup 的关键字参数。"""
        return {
            "sources": query.get("source") or None,
            "csv_datasets": query.get("csv_db") or None,
        }

    def _requires_auth(self, path: str) -> bool:
        if not os.getenv("IPGEOSEARCH_API_KEY", ""):
            return False
        return path not in PUBLIC_PATHS and not path.startswith("/static/")

    def _is_authorized(self, query: Query) -> bool:
        expected = os.getenv("IPGEOSEARCH_API_KEY", "")
        if not expected:
            return True
        supplied = self.headers.get("X-API-Key", "") or query.get("api_key", [""])[0]
        return hmac.compare_digest(supplied, expected)

    # --- 响应 ---------------------------------------------------------------

    def _send_common_headers(self, etag: str | None = None) -> None:
        for name, value in SECURITY_HEADERS.items():
            self.send_header(name, value)
        if etag:
            self.send_header("ETag", etag)
            # 静态资源必须每次校验，避免改完前端还拿到旧文件。
            self.send_header("Cache-Control", "no-cache")

    def _send_json(self, payload: object, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self._send_common_headers()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path: Path) -> None:
        try:
            resolved = path.resolve()
            if not resolved.is_relative_to(STATIC_ROOT.resolve()) or not resolved.is_file():
                self._send_json({"error": "not found"}, status=404)
                return

            stat = resolved.stat()
            etag = f'"{int(stat.st_mtime)}-{stat.st_size}"'
            if self.headers.get("If-None-Match") == etag:
                self.send_response(304)
                self._send_common_headers(etag)
                self.end_headers()
                return

            body = resolved.read_bytes()
            content_type = mimetypes.guess_type(str(resolved))[0] or "application/octet-stream"
            if resolved.suffix == ".js":
                content_type = "text/javascript"
            self.send_response(200)
            self._send_common_headers(etag)
            self.send_header("Content-Type", f"{content_type}; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except Exception as exc:
            self.log_error("static file failed: %s", exc)
            self._send_json({"error": "internal error"}, status=500)

    # --- 各接口实现 ---------------------------------------------------------

    def _send_health(self, query: Query) -> None:
        self._send_json({"ok": True})

    def _send_map_config(self, query: Query) -> None:
        key = os.getenv("IPGEOSEARCH_TMAP_KEY", "")
        self._send_json({"provider": "tencent", "key": key, "configured": bool(key)})

    def _send_datasets(self, query: Query) -> None:
        self._send_json({"datasets": self.service.available_csv_datasets()})

    @ip_endpoint
    def _send_lookup(self, ip: Any, query: Query) -> None:
        try:
            self._send_json(self.service.lookup(str(ip), **self._lookup_options(query)))
        except ValueError as exc:
            # 入参不合法（例如 IP 格式错误）
            self._send_json({"error": str(exc)}, status=400)
        except Exception as exc:
            # 服务端自身的问题（数据源不可用等）不应伪装成客户端错误
            self.log_error("lookup failed for %s: %s", ip, exc)
            self._send_json({"error": "lookup failed"}, status=500)

    @host_endpoint(allow_ip=True)
    def _send_resolve(self, host: str, query: Query) -> None:
        if is_literal_ip(host):
            self._send_json({"host": host, "addresses": [str(parse_ip(host))]})
            return

        try:
            rows = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
        except socket.gaierror as exc:
            self._send_json({"error": f"resolve failed: {exc.strerror or exc}"}, status=400)
            return

        addresses = sorted({row[4][0] for row in rows}, key=lambda value: (":" in value, value))
        if not addresses:
            self._send_json({"error": "no addresses found"}, status=404)
            return
        self._send_json({"host": host, "addresses": addresses})

    @host_endpoint(allow_ip=False)
    def _send_dns(self, host: str, query: Query) -> None:
        self._send_json(resolve_records(host))

    @ip_endpoint
    def _send_rdap(self, ip: Any, query: Query) -> None:
        self._send_json(rdap_lookup(ip))

    @ip_endpoint
    def _send_reverse_dns(self, ip: Any, query: Query) -> None:
        self._send_json(reverse_lookup(str(ip)))

    @ip_endpoint
    def _send_intel(self, ip: Any, query: Query) -> None:
        address = str(ip)
        reverse_payload = reverse_lookup(address)
        dnsbl_payload = dnsbl_lookup(ip)
        try:
            lookup_payload = self.service.lookup(address, **self._lookup_options(query))
        except Exception as exc:
            lookup_payload = {"ip": address, "results": [], "error": str(exc)}

        privacy = scoring.classify(
            ip,
            lookup_payload,
            extra_text=str(reverse_payload.get("hostname", "")),
            dnsbl_listed=bool(dnsbl_payload.get("matches")),
        )
        self._send_json(
            {
                "ip": address,
                "lookup": lookup_payload,
                "reverseDns": reverse_payload,
                "dnsbl": dnsbl_payload,
                "privacy": privacy,
            }
        )

    def _send_probe(self, query: Query) -> None:
        target = query.get("target", [""])[0].strip()
        if not target:
            self._send_json({"error": "missing target query parameter"}, status=400)
            return
        try:
            self._send_json(probe_target(target))
        except ValueError as exc:
            self._send_json({"error": str(exc)}, status=400)
        except Exception as exc:
            self.log_error("probe failed for %s: %s", target, exc)
            self._send_json({"error": "probe failed"}, status=500)


class LookupServer(ThreadingHTTPServer):
    """请求线程设为守护线程，进程退出时不会被残留连接卡住。"""

    daemon_threads = True
    request_queue_size = 64
    allow_reuse_address = True
