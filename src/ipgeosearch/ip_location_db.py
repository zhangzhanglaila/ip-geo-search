"""Reader for ip-location-db CSV datasets."""

from __future__ import annotations

import csv
import ipaddress
import threading
from array import array
from bisect import bisect_right
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from .models import SourceResult


RANGE_FIELD_START = "ip_range_start"
RANGE_FIELD_END = "ip_range_end"

COUNTRY_FIELDS = ("country_code",)
ASN_FIELDS = (
    "autonomous_system_number",
    "autonomous_system_organization",
)
CITY_FIELDS = (
    "country_code",
    "state1",
    "state2",
    "city",
    "postcode",
    "latitude",
    "longitude",
    "timezone",
)

# 默认只用到 user-country 与 origin-asn 两个数据集，缓存上限给小一些，
# 避免通过 csv_db 参数不断切换数据集导致常驻内存单调增长。
MAX_CACHED_DATASETS = 4


def ip_to_int(text: str) -> int:
    """把 IPv4/IPv6 字面量转成整数。

    IPv4 走手工移位，比逐行构造 ipaddress 对象再转 int 快很多
    （默认两个数据集合计约 71 万行，加载耗时主要在这里）。
    """
    if ":" in text:
        return int(ipaddress.IPv6Address(text))
    value = 0
    for part in text.split("."):
        value = (value << 8) | int(part)
    return value


def int_to_ip(value: int) -> str:
    return str(ipaddress.ip_address(value))


def _is_sorted(values: Sequence[int]) -> bool:
    return all(left <= right for left, right in zip(values, values[1:]))


def _to_column(values: list[int], use_array: bool) -> list[int] | array:
    # array("Q") 只占 8 字节/项，省掉每个 int 对象；IPv6 是 128 位，
    # 放不进 unsigned long long，退回普通列表。
    return array("Q", values) if use_array else values


@dataclass(frozen=True)
class CsvIndex:
    """列式存储的区间索引。

    行数据只保留 IP 区间之外的有效字段（元组），区间起点/终点另用并列数组存放：
    原实现每行一个 dataclass + 一个 dict，会把 26MB 的 CSV 放大到数百 MB 常驻内存。
    """

    fields: tuple[str, ...]
    starts: list[int] | array
    ends: list[int] | array
    rows: list[tuple[str, ...]]

    def find(self, value: int) -> dict[str, Any] | None:
        index = bisect_right(self.starts, value) - 1
        if index < 0 or value > self.ends[index]:
            return None
        result = {
            RANGE_FIELD_START: int_to_ip(self.starts[index]),
            RANGE_FIELD_END: int_to_ip(self.ends[index]),
        }
        result.update(zip(self.fields, self.rows[index]))
        return result


class IpLocationDb:
    def __init__(self, root: Path, max_cached_datasets: int = MAX_CACHED_DATASETS) -> None:
        self.root = root
        self.max_cached_datasets = max_cached_datasets
        self._cache: OrderedDict[tuple[str, int], tuple[float, Path, CsvIndex]] = OrderedDict()
        self._lock = threading.Lock()

    def lookup_many(self, ip: str, datasets: list[str]) -> SourceResult:
        try:
            parsed = ipaddress.ip_address(ip)
            value = int(parsed)
            rows: dict[str, dict[str, Any] | None] = {}
            for dataset in datasets:
                rows[dataset] = self._find(dataset, parsed.version, value)
            return SourceResult(source="ip-location-db", ok=True, data=rows)
        except Exception as exc:
            return SourceResult(source="ip-location-db", ok=False, error=str(exc))

    def lookup_dataset(
        self, ip: ipaddress.IPv4Address | ipaddress.IPv6Address, dataset: str
    ) -> dict[str, Any] | None:
        return self._find(dataset, ip.version, int(ip))

    def available_datasets(self) -> list[str]:
        datasets = []
        if not self.root.exists():
            return datasets
        for child in sorted(self.root.iterdir()):
            if not child.is_dir():
                continue
            if (child / f"{child.name}-ipv4.csv").exists() or (
                child / f"{child.name}-ipv6.csv"
            ).exists():
                datasets.append(child.name)
        return datasets

    def cached_datasets(self) -> list[str]:
        with self._lock:
            return [f"{dataset}#v{version}" for dataset, version in self._cache]

    def _find(self, dataset: str, ip_version: int, value: int) -> dict[str, Any] | None:
        return self._get_index(dataset, ip_version).find(value)

    def _get_index(self, dataset: str, ip_version: int) -> CsvIndex:
        path = self._dataset_path(dataset, ip_version)
        if not path.exists():
            raise FileNotFoundError(f"CSV dataset not found: {path}")
        mtime = path.stat().st_mtime
        key = (dataset, ip_version)

        with self._lock:
            entry = self._cache.get(key)
            if entry is not None:
                cached_mtime, cached_path, index = entry
                if cached_path == path and cached_mtime == mtime:
                    self._cache.move_to_end(key)
                    return index
                del self._cache[key]

        index = self._load_index(path, dataset, ip_version)

        with self._lock:
            self._cache[key] = (mtime, path, index)
            self._cache.move_to_end(key)
            while len(self._cache) > self.max_cached_datasets:
                self._cache.popitem(last=False)
        return index

    def _dataset_path(self, dataset: str, ip_version: int) -> Path:
        suffix = "ipv4" if ip_version == 4 else "ipv6"
        return self.root / dataset / f"{dataset}-{suffix}.csv"

    def _load_index(self, path: Path, dataset: str, ip_version: int) -> CsvIndex:
        fields = self._fields_for_dataset(dataset)
        width = len(fields)
        starts: list[int] = []
        ends: list[int] = []
        rows: list[tuple[str, ...]] = []

        with path.open("r", encoding="utf-8", newline="") as handle:
            for values in csv.reader(handle):
                if len(values) < 2:
                    continue
                starts.append(ip_to_int(values[0]))
                ends.append(ip_to_int(values[1]))
                rows.append(tuple(values[2 : 2 + width]))

        if not _is_sorted(starts):
            order = sorted(range(len(starts)), key=starts.__getitem__)
            starts = [starts[index] for index in order]
            ends = [ends[index] for index in order]
            rows = [rows[index] for index in order]

        use_array = ip_version == 4
        return CsvIndex(
            fields=fields,
            starts=_to_column(starts, use_array),
            ends=_to_column(ends, use_array),
            rows=rows,
        )

    @staticmethod
    def _fields_for_dataset(dataset: str) -> tuple[str, ...]:
        if dataset.endswith("-asn"):
            return ASN_FIELDS
        if dataset.endswith("-city"):
            return CITY_FIELDS
        return COUNTRY_FIELDS
