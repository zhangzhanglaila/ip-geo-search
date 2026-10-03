"""CLI 入口：启动 HTTP 服务并打印数据源可用状态。

HTTP 相关的实现都在 `http_app`，这里只负责命令行参数与生命周期；
`LookupHandler` / `LookupServer` 在此再导出，保持 `ipgeosearch.server:main`
这个 console script 入口与既有调用方的兼容。
"""

from __future__ import annotations

import argparse

from .http_app import LookupHandler, LookupServer
from .service import IPGeoSearch

__all__ = ["LookupHandler", "LookupServer", "main"]


def _print_data_sources(service: IPGeoSearch) -> None:
    paths = service.paths
    print(f"data root: {paths.workspace}", flush=True)
    for name, path, ok in paths.availability():
        print(f"  [{'ok' if ok else 'missing'}] {name}: {path}", flush=True)
    missing = paths.missing_sources()
    if missing:
        print(f"warning: 数据源不可用，相关查询会失败: {', '.join(missing)}", flush=True)
        print(
            "        可设置 IPGEOSEARCH_DATA_ROOT 指向数据仓库的父目录，"
            "或用 IPGEOSEARCH_IP2REGION_ROOT / IPGEOSEARCH_IP_LOCATION_DB_ROOT / "
            "IPGEOSEARCH_GEOIP2_PYTHON_ROOT 分别指定。",
            flush=True,
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="IPGeoSearch HTTP API")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    args = parser.parse_args()

    _print_data_sources(LookupHandler.service)
    server = LookupServer((args.host, args.port), LookupHandler)
    print(f"listening on http://{args.host}:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        LookupHandler.service.close()
        server.server_close()


if __name__ == "__main__":
    main()
