"""Reader for ip-location-db CSV datasets."""

from __future__ import annotations

import csv
import ipaddress
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .models import SourceResult


COUNTRY_FIELDS = ("ip_range_start", "ip_range_end", "country_code")
ASN_FIELDS = (
    "ip_range_start",
    "ip_range_end",
    "autonomous_system_number",
    "autonomous_system_organization",
)
CITY_FIELDS = (
    "ip_range_start",
    "ip_range_end",
    "country_code",
    "state1",
    "state2",
    "city",
    "postcode",
    "latitude",
    "longitude",
    "timezone",
)


@dataclass(frozen=True)
class CsvRange:
    start: int
    end: int
    row: dict[str, str]


class IpLocationDb:
    def __init__(self, root: Path) -> None:
        self.root = root
        self._cache: dict[tuple[str, int], list[CsvRange]] = {}

    def lookup_many(self, ip: str, datasets: list[str]) -> SourceResult:
        try:
            parsed = ipaddress.ip_address(ip)
            rows = {}
            for dataset in datasets:
                rows[dataset] = self.lookup_dataset(parsed, dataset)
            return SourceResult(source="ip-location-db", ok=True, data=rows)
        except Exception as exc:
            return SourceResult(source="ip-location-db", ok=False, error=str(exc))

    def lookup_dataset(self, ip: ipaddress._BaseAddress, dataset: str) -> dict[str, Any] | None:
        ranges = self._load_dataset(dataset, ip.version)
        value = int(ip)
        low = 0
        high = len(ranges) - 1
        while low <= high:
            mid = (low + high) // 2
            item = ranges[mid]
            if value < item.start:
                high = mid - 1
            elif value > item.end:
                low = mid + 1
            else:
                return item.row
        return None

    def available_datasets(self) -> list[str]:
        datasets = []
        if not self.root.exists():
            return datasets
        for child in self.root.iterdir():
            if not child.is_dir():
                continue
            if (child / f"{child.name}-ipv4.csv").exists() or (
                child / f"{child.name}-ipv6.csv"
            ).exists():
                datasets.append(child.name)
        return sorted(datasets)

    def _load_dataset(self, dataset: str, ip_version: int) -> list[CsvRange]:
        key = (dataset, ip_version)
        if key in self._cache:
            return self._cache[key]

        suffix = "ipv4" if ip_version == 4 else "ipv6"
        path = self.root / dataset / f"{dataset}-{suffix}.csv"
        if not path.exists():
            raise FileNotFoundError(f"CSV dataset not found: {path}")

        fields = self._fields_for_dataset(dataset)
        ranges: list[CsvRange] = []
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.reader(handle)
            for values in reader:
                if not values:
                    continue
                if len(values) < 3:
                    continue
                row = {name: values[index] if index < len(values) else "" for index, name in enumerate(fields)}
                ranges.append(
                    CsvRange(
                        start=int(ipaddress.ip_address(values[0])),
                        end=int(ipaddress.ip_address(values[1])),
                        row=row,
                    )
                )

        ranges.sort(key=lambda item: item.start)
        self._cache[key] = ranges
        return ranges

    @staticmethod
    def _fields_for_dataset(dataset: str) -> tuple[str, ...]:
        if dataset.endswith("-asn"):
            return ASN_FIELDS
        if dataset.endswith("-city"):
            return CITY_FIELDS
        return COUNTRY_FIELDS
