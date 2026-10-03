"""ip-location-db CSV 索引测试。"""

from __future__ import annotations

import csv
import ipaddress
import os
from pathlib import Path

import pytest

from ipgeosearch.ip_location_db import IpLocationDb, int_to_ip, ip_to_int

COUNTRY_ROWS = [
    ("1.0.0.0", "1.0.0.255", "AU"),
    ("1.0.4.0", "1.0.7.255", "CN"),
    ("9.9.9.0", "9.9.9.255", "US"),
]
ASN_ROWS = [
    ("1.0.0.0", "1.0.0.255", "13335", "Cloudflare, Inc."),
    ("1.0.4.0", "1.0.7.255", "38803", "Gtelecom Pty Ltd"),
]


def write_dataset(root: Path, name: str, rows: list[tuple[str, ...]], suffix: str = "ipv4") -> Path:
    directory = root / name
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{name}-{suffix}.csv"
    # 用 csv.writer 保证含逗号的字段（如 "Cloudflare, Inc."）被正确加引号，
    # 与真实的 ip-location-db 数据集格式一致。
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerows(rows)
    return path


@pytest.fixture()
def db(tmp_path: Path) -> IpLocationDb:
    write_dataset(tmp_path, "user-country", COUNTRY_ROWS)
    write_dataset(tmp_path, "origin-asn", ASN_ROWS)
    return IpLocationDb(tmp_path)


def test_ip_to_int_roundtrip():
    assert ip_to_int("1.0.0.0") == 16777216
    assert int_to_ip(16777216) == "1.0.0.0"
    assert ip_to_int("2001:db8::1") == int(ipaddress.IPv6Address("2001:db8::1"))
    assert int_to_ip(int(ipaddress.IPv6Address("2001:db8::1"))) == "2001:db8::1"


def test_lookup_hit_and_miss(db: IpLocationDb):
    inside = db.lookup_dataset(ipaddress.ip_address("1.0.5.9"), "user-country")
    assert inside is not None
    assert inside["country_code"] == "CN"
    assert inside["ip_range_start"] == "1.0.4.0"
    assert inside["ip_range_end"] == "1.0.7.255"

    assert db.lookup_dataset(ipaddress.ip_address("1.0.2.1"), "user-country") is None


def test_asn_dataset_fields(db: IpLocationDb):
    row = db.lookup_dataset(ipaddress.ip_address("1.0.0.10"), "origin-asn")
    assert row is not None
    assert set(row) == {
        "ip_range_start",
        "ip_range_end",
        "autonomous_system_number",
        "autonomous_system_organization",
    }
    assert row["autonomous_system_organization"] == "Cloudflare, Inc."


def test_boundary_addresses(db: IpLocationDb):
    for address in ("1.0.0.0", "1.0.0.255", "1.0.4.0", "1.0.7.255"):
        assert db.lookup_dataset(ipaddress.ip_address(address), "user-country") is not None
    assert db.lookup_dataset(ipaddress.ip_address("1.0.3.255"), "user-country") is None


def test_unsorted_dataset_is_sorted_before_search(tmp_path: Path):
    write_dataset(tmp_path, "user-country", list(reversed(COUNTRY_ROWS)))
    db = IpLocationDb(tmp_path)
    row = db.lookup_dataset(ipaddress.ip_address("1.0.5.9"), "user-country")
    assert row is not None and row["country_code"] == "CN"


def test_lookup_many_reports_missing_dataset(tmp_path: Path):
    result = IpLocationDb(tmp_path).lookup_many("1.0.0.1", ["user-country"])
    assert result.ok is False
    assert "CSV dataset not found" in (result.error or "")


def test_cache_is_reused(db: IpLocationDb):
    first = db.lookup_dataset(ipaddress.ip_address("1.0.0.1"), "user-country")
    assert db.cached_datasets() == ["user-country#v4"]
    second = db.lookup_dataset(ipaddress.ip_address("1.0.0.2"), "user-country")
    assert first is not second or first == second
    assert db.cached_datasets() == ["user-country#v4"]


def test_cache_evicts_least_recently_used(tmp_path: Path):
    write_dataset(tmp_path, "user-country", COUNTRY_ROWS)
    write_dataset(tmp_path, "origin-asn", ASN_ROWS)
    write_dataset(tmp_path, "server-country", COUNTRY_ROWS)
    db = IpLocationDb(tmp_path, max_cached_datasets=2)

    db.lookup_dataset(ipaddress.ip_address("1.0.0.1"), "user-country")
    db.lookup_dataset(ipaddress.ip_address("1.0.0.1"), "origin-asn")
    db.lookup_dataset(ipaddress.ip_address("1.0.0.1"), "server-country")

    assert db.cached_datasets() == ["origin-asn#v4", "server-country#v4"]


def test_cache_invalidates_when_file_changes(tmp_path: Path):
    path = write_dataset(tmp_path, "user-country", COUNTRY_ROWS)
    db = IpLocationDb(tmp_path)
    assert db.lookup_dataset(ipaddress.ip_address("1.0.5.9"), "user-country")["country_code"] == "CN"

    write_dataset(tmp_path, "user-country", [("1.0.0.0", "1.0.7.255", "SG")])
    stale = os.stat(path).st_mtime + 10
    os.utime(path, (stale, stale))

    assert db.lookup_dataset(ipaddress.ip_address("1.0.5.9"), "user-country")["country_code"] == "SG"


def test_ipv6_dataset_keeps_full_precision(tmp_path: Path):
    write_dataset(
        tmp_path,
        "user-country",
        [("2001:db8::", "2001:db8::ffff", "JP")],
        suffix="ipv6",
    )
    db = IpLocationDb(tmp_path)
    row = db.lookup_dataset(ipaddress.ip_address("2001:db8::1"), "user-country")
    assert row is not None
    assert row["country_code"] == "JP"
    assert row["ip_range_start"] == "2001:db8::"
    assert row["ip_range_end"] == "2001:db8::ffff"


def test_rows_shorter_than_fields_do_not_break(tmp_path: Path):
    write_dataset(tmp_path, "user-country", [("1.0.0.0", "1.0.0.255")])
    db = IpLocationDb(tmp_path)
    row = db.lookup_dataset(ipaddress.ip_address("1.0.0.1"), "user-country")
    assert row is not None
    assert row["country_code"] == ""


def test_available_datasets_lists_only_real_ones(tmp_path: Path):
    write_dataset(tmp_path, "user-country", COUNTRY_ROWS)
    (tmp_path / "not-a-dataset").mkdir()
    assert IpLocationDb(tmp_path).available_datasets() == ["user-country"]
