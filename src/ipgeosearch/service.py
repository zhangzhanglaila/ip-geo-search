"""IPGeoSearch lookup service."""

from __future__ import annotations

import ipaddress
from typing import Any

from .config import Paths
from .geoip2_adapter import GeoIp2Adapter
from .ip2region_adapter import Ip2RegionAdapter
from .ip_location_db import IpLocationDb


DEFAULT_CSV_DATASETS = ["user-country", "origin-asn"]


class IPGeoSearch:
    def __init__(
        self,
        paths: Paths | None = None,
        csv_datasets: list[str] | None = None,
        ip2region_cache: str = "content",
    ) -> None:
        self.paths = paths or Paths.from_env()
        self.csv_datasets = csv_datasets or DEFAULT_CSV_DATASETS
        self.ip2region = Ip2RegionAdapter(self.paths.ip2region_root, ip2region_cache)
        self.ip_location_db = IpLocationDb(self.paths.ip_location_db_root)
        self.geoip2 = GeoIp2Adapter(self.paths.geoip2_python_root, self.paths.geoip2_mmdb)

    def lookup(self, ip: str, sources: list[str] | None = None) -> dict[str, Any]:
        parsed = ipaddress.ip_address(ip)
        requested = sources or ["ip2region", "ip-location-db", "geoip2"]
        results = []

        if "ip2region" in requested:
            results.append(self.ip2region.lookup(ip).to_dict())
        if "ip-location-db" in requested or "csv" in requested:
            results.append(self.ip_location_db.lookup_many(ip, self.csv_datasets).to_dict())
        if "geoip2" in requested:
            results.append(self.geoip2.lookup(ip).to_dict())

        return {
            "ip": ip,
            "ip_version": parsed.version,
            "results": results,
        }

    def available_csv_datasets(self) -> list[str]:
        return self.ip_location_db.available_datasets()

    def close(self) -> None:
        self.ip2region.close()
        self.geoip2.close()
