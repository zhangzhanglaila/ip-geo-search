"""Adapter for the sibling ip2region project."""

from __future__ import annotations

import ipaddress
import threading
from pathlib import Path

from ._bootstrap import ensure_import_path
from .models import SourceResult


class Ip2RegionAdapter:
    """ip2region 的薄封装。

    searcher 按 IP 版本懒加载并被多线程共享，因此创建过程用锁保护，
    避免并发下重复构造（content 策略会重复把整个 xdb 读进内存）。
    """

    def __init__(self, root: Path, cache_policy: str = "content") -> None:
        self.root = root
        self.cache_policy = cache_policy
        self._searchers: dict[int, object] = {}
        self._util = None
        self._searcher_module = None
        self._lock = threading.Lock()

    def lookup(self, ip: str) -> SourceResult:
        try:
            version = ipaddress.ip_address(ip).version
            searcher = self._get_searcher(version)
            region = searcher.search(ip)
            return SourceResult(
                source="ip2region",
                ok=True,
                data={"region": region, "ip_version": version},
            )
        except Exception as exc:
            return SourceResult(source="ip2region", ok=False, error=str(exc))

    def close(self) -> None:
        with self._lock:
            searchers = list(self._searchers.values())
            self._searchers.clear()
        for searcher in searchers:
            close = getattr(searcher, "close", None)
            if close:
                close()

    def _load_modules(self) -> None:
        if self._util is not None and self._searcher_module is not None:
            return

        binding_path = self.root / "binding" / "python"
        if not binding_path.exists():
            raise FileNotFoundError(f"ip2region Python binding not found: {binding_path}")
        ensure_import_path(binding_path)

        import ip2region.searcher as searcher_module
        import ip2region.util as util

        self._util = util
        self._searcher_module = searcher_module

    def _get_searcher(self, ip_version: int) -> object:
        with self._lock:
            existing = self._searchers.get(ip_version)
            if existing is not None:
                return existing

            self._load_modules()
            assert self._util is not None
            assert self._searcher_module is not None

            if ip_version == 4:
                version = self._util.IPv4
                db_path = self.root / "data" / "ip2region_v4.xdb"
            else:
                version = self._util.IPv6
                db_path = self.root / "data" / "ip2region_v6.xdb"

            if not db_path.exists():
                raise FileNotFoundError(f"xdb file not found: {db_path}")

            if self.cache_policy == "file":
                searcher = self._searcher_module.new_with_file_only(version, str(db_path))
            elif self.cache_policy == "vector":
                vector = self._util.load_vector_index_from_file(str(db_path))
                searcher = self._searcher_module.new_with_vector_index(version, str(db_path), vector)
            elif self.cache_policy == "content":
                content = self._util.load_content_from_file(str(db_path))
                searcher = self._searcher_module.new_with_buffer(version, content)
            else:
                raise ValueError(f"unsupported ip2region cache policy: {self.cache_policy}")

            self._searchers[ip_version] = searcher
            return searcher
