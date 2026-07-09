"""Command line interface."""

from __future__ import annotations

import argparse
import json
from pprint import pprint

from .service import DEFAULT_CSV_DATASETS, IPGeoSearch


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="IPGeoSearch offline IP geolocation lookup")
    parser.add_argument("ip", nargs="?", help="IP address to query")
    parser.add_argument(
        "--source",
        action="append",
        choices=["ip2region", "ip-location-db", "csv", "geoip2"],
        help="Source to query. Can be repeated. Defaults to all sources.",
    )
    parser.add_argument(
        "--csv-db",
        action="append",
        default=None,
        help=f"ip-location-db dataset. Defaults to {', '.join(DEFAULT_CSV_DATASETS)}.",
    )
    parser.add_argument(
        "--ip2region-cache",
        choices=["content", "vector", "file"],
        default="content",
        help="ip2region cache policy.",
    )
    parser.add_argument("--list-csv", action="store_true", help="List available CSV datasets.")
    parser.add_argument("--json", action="store_true", help="Print JSON output.")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    service = IPGeoSearch(
        csv_datasets=args.csv_db,
        ip2region_cache=args.ip2region_cache,
    )
    try:
        if args.list_csv:
            datasets = service.available_csv_datasets()
            print(json.dumps(datasets, ensure_ascii=False, indent=2) if args.json else "\n".join(datasets))
            return

        if not args.ip:
            parser.error("ip is required unless --list-csv is used")

        result = service.lookup(args.ip, sources=args.source)
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            pprint(result, sort_dicts=False)
    finally:
        service.close()


if __name__ == "__main__":
    main()
