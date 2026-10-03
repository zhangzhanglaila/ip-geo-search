"""IPGeoSearch lookup service."""

from __future__ import annotations

import ipaddress
import threading
import time
from collections import OrderedDict
from copy import deepcopy
from typing import Any

from . import scoring
from .config import Paths
from .geoip2_adapter import GeoIp2Adapter
from .ip2region_adapter import Ip2RegionAdapter
from .ip_location_db import IpLocationDb


DEFAULT_CSV_DATASETS = ["user-country", "origin-asn"]
DEFAULT_SOURCES = ["ip2region", "ip-location-db", "geoip2"]
CACHE_TTL_SECONDS = 60.0
CACHE_MAX_ENTRIES = 512

CacheKey = tuple[str, tuple[str, ...], tuple[str, ...]]


class IPGeoSearch:
    """聚合各数据源的查询服务。

    该实例会被多个请求线程共享，因此只保存不可变配置：
    每次查询的数据源与数据集都通过参数传入，不再由请求临时改写实例状态。
    """

    def __init__(
        self,
        paths: Paths | None = None,
        csv_datasets: list[str] | None = None,
        ip2region_cache: str = "content",
        cache_ttl: float = CACHE_TTL_SECONDS,
        cache_max_entries: int = CACHE_MAX_ENTRIES,
    ) -> None:
        self.paths = paths or Paths.from_env()
        self.csv_datasets = tuple(csv_datasets or DEFAULT_CSV_DATASETS)
        self.ip2region = Ip2RegionAdapter(self.paths.ip2region_root, ip2region_cache)
        self.ip_location_db = IpLocationDb(self.paths.ip_location_db_root)
        self.geoip2 = GeoIp2Adapter(self.paths.geoip2_python_root, self.paths.geoip2_mmdb)
        self._cache_ttl = cache_ttl
        self._cache_max_entries = cache_max_entries
        self._cache: OrderedDict[CacheKey, tuple[float, dict[str, Any]]] = OrderedDict()
        self._cache_lock = threading.Lock()

    def lookup(
        self,
        ip: str,
        sources: list[str] | None = None,
        csv_datasets: list[str] | None = None,
    ) -> dict[str, Any]:
        parsed = ipaddress.ip_address(ip)
        requested = list(sources) if sources else list(DEFAULT_SOURCES)
        datasets = list(csv_datasets) if csv_datasets else list(self.csv_datasets)

        cache_key: CacheKey = (str(parsed), tuple(requested), tuple(datasets))
        cached = self._cache_get(cache_key)
        if cached is not None:
            return deepcopy(cached)

        results = []
        if "ip2region" in requested:
            results.append(self.ip2region.lookup(ip).to_dict())
        if "ip-location-db" in requested or "csv" in requested:
            results.append(self.ip_location_db.lookup_many(ip, datasets).to_dict())
        if "geoip2" in requested:
            results.append(self.geoip2.lookup(ip).to_dict())

        payload = {
            "ip": ip,
            "ip_version": parsed.version,
            "results": results,
        }
        # 类型与风险评分统一在这里产出，前端与 /intel 都直接复用，避免两套规则漂移。
        payload["risk"] = scoring.classify(parsed, payload)
        self._cache_put(cache_key, payload)
        return deepcopy(payload)

    def available_csv_datasets(self) -> list[str]:
        return self.ip_location_db.available_datasets()

    def clear_cache(self) -> None:
        with self._cache_lock:
            self._cache.clear()

    def close(self) -> None:
        self.ip2region.close()
        self.geoip2.close()

    def _cache_get(self, key: CacheKey) -> dict[str, Any] | None:
        if self._cache_ttl <= 0:
            return None
        now = time.monotonic()
        with self._cache_lock:
            entry = self._cache.get(key)
            if entry is None:
                return None
            stored_at, payload = entry
            if now - stored_at > self._cache_ttl:
                del self._cache[key]
                return None
            self._cache.move_to_end(key)
            return payload

    def _cache_put(self, key: CacheKey, payload: dict[str, Any]) -> None:
        if self._cache_ttl <= 0 or self._cache_max_entries <= 0:
            return
        with self._cache_lock:
            self._cache[key] = (time.monotonic(), payload)
            self._cache.move_to_end(key)
            while len(self._cache) > self._cache_max_entries:
                self._cache.popitem(last=False)
