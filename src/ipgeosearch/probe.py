"""TCP 端口探测：只对目标做 443/80 的连通性与延迟测量。

`/probe` 由服务端代任意目标发起连接，因此目标必须先在 targets 里过一遍
（只允许 IP 或合法主机名），端口也固定为 443/80，避免被当成通用端口扫描器。
注意：该接口仍可探测内网地址，对外暴露时应配合 API Key 使用。
"""

from __future__ import annotations

import socket
import time

from .targets import require_host

PROBE_TIMEOUT_SECONDS = 3.0
PROBE_PORTS = (443, 80)


def probe_target(target: str) -> dict[str, object]:
    host = require_host(target)

    results: list[dict[str, object]] = []
    for port in PROBE_PORTS:
        started = time.perf_counter()
        try:
            with socket.create_connection((host, port), timeout=PROBE_TIMEOUT_SECONDS):
                latency_ms = round((time.perf_counter() - started) * 1000, 2)
                results.append({"port": port, "open": True, "latencyMs": latency_ms})
        except OSError as exc:
            latency_ms = round((time.perf_counter() - started) * 1000, 2)
            results.append({"port": port, "open": False, "latencyMs": latency_ms, "error": str(exc)})
    return {"target": target, "host": host, "results": results}
