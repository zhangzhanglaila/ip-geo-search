"""Small dependency-free HTTP API."""

from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .service import IPGeoSearch


class LookupHandler(BaseHTTPRequestHandler):
    service = IPGeoSearch()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            self._send_json({"ok": True})
            return

        if parsed.path == "/datasets":
            self._send_json({"datasets": self.service.available_csv_datasets()})
            return

        if parsed.path != "/lookup":
            self._send_json({"error": "not found"}, status=404)
            return

        query = parse_qs(parsed.query)
        ip = query.get("ip", [""])[0]
        if not ip:
            self._send_json({"error": "missing ip query parameter"}, status=400)
            return

        sources = query.get("source") or None
        csv_datasets = query.get("csv_db")
        old_datasets = None
        if csv_datasets:
            old_datasets = self.service.csv_datasets
            self.service.csv_datasets = csv_datasets

        try:
            self._send_json(self.service.lookup(ip, sources=sources))
        except Exception as exc:
            self._send_json({"error": str(exc)}, status=400)
        finally:
            if old_datasets is not None:
                self.service.csv_datasets = old_datasets

    def log_message(self, format: str, *args: object) -> None:
        return

    def _send_json(self, payload: object, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    parser = argparse.ArgumentParser(description="IPGeoSearch HTTP API")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), LookupHandler)
    print(f"listening on http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        LookupHandler.service.close()
        server.server_close()


if __name__ == "__main__":
    main()
