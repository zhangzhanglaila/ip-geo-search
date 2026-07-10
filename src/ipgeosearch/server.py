"""Small dependency-free HTTP API."""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from .service import IPGeoSearch


STATIC_ROOT = Path(__file__).resolve().parent / "static"
DEFAULT_OFFLINE_MAP_ROOT = Path("D:/iPhotron-LocalPhotoAlbumManager/src/maps")


def _offline_map_root() -> Path:
    return Path(os.getenv("IPGEOSEARCH_OFFLINE_MAP_ROOT", DEFAULT_OFFLINE_MAP_ROOT)).resolve()


def _offline_map_available() -> bool:
    root = _offline_map_root()
    return (root / "style.json").is_file() and (root / "tiles" / "tiles.json").is_file()


class LookupHandler(BaseHTTPRequestHandler):
    service = IPGeoSearch()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path in ("", "/"):
            self._send_file(STATIC_ROOT / "index.html")
            return

        if parsed.path.startswith("/static/"):
            relative_path = parsed.path.removeprefix("/static/")
            self._send_file(STATIC_ROOT.joinpath(*relative_path.split("/")))
            return

        if parsed.path == "/offline-map/style.json":
            self._send_offline_map_style()
            return

        if parsed.path == "/offline-map/tiles.json":
            self._send_offline_tiles_json()
            return

        if parsed.path.startswith("/offline-map/tiles/"):
            relative_path = parsed.path.removeprefix("/offline-map/tiles/")
            self._send_offline_tile(relative_path)
            return

        if parsed.path.startswith("/offline-map/fonts/"):
            relative_path = parsed.path.removeprefix("/offline-map/fonts/")
            self._send_offline_font(relative_path)
            return

        if parsed.path == "/health":
            self._send_json({"ok": True})
            return

        if parsed.path == "/datasets":
            self._send_json({"datasets": self.service.available_csv_datasets()})
            return

        if parsed.path == "/map-config":
            amap_key = os.getenv("AMAP_WEB_KEY", "")
            default_provider = "offline" if _offline_map_available() else ("amap" if amap_key else "osm")
            provider = os.getenv("MAP_PROVIDER", default_provider).lower()
            self._send_json(
                {
                    "provider": provider,
                    "amapKey": amap_key,
                    "offlineMapAvailable": _offline_map_available(),
                    "offlineMapMaxZoom": 6,
                }
            )
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

    def _send_file(self, path: Path) -> None:
        try:
            resolved = path.resolve()
            if not str(resolved).startswith(str(STATIC_ROOT.resolve())):
                self._send_json({"error": "not found"}, status=404)
                return
            if not resolved.is_file():
                self._send_json({"error": "not found"}, status=404)
                return

            body = resolved.read_bytes()
            content_type = mimetypes.guess_type(str(resolved))[0] or "application/octet-stream"
            if resolved.suffix == ".js":
                content_type = "text/javascript"
            self.send_response(200)
            self.send_header("Content-Type", f"{content_type}; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except Exception as exc:
            self._send_json({"error": str(exc)}, status=500)

    def _send_bytes(self, body: bytes, content_type: str, status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _request_origin(self) -> str:
        host = self.headers.get("Host", f"{self.server.server_address[0]}:{self.server.server_address[1]}")
        return f"http://{host}"

    def _send_offline_map_style(self) -> None:
        root = _offline_map_root()
        style_path = root / "style.json"
        if not style_path.is_file():
            self._send_json({"error": "offline map style not found"}, status=404)
            return

        with style_path.open("r", encoding="utf-8") as handle:
            style = json.load(handle)

        origin = self._request_origin()
        style["glyphs"] = f"{origin}/offline-map/fonts/{{fontstack}}/{{range}}.pbf"
        style["sources"]["maplibre"] = {
            "type": "vector",
            "url": f"{origin}/offline-map/tiles.json",
        }
        body = json.dumps(style, ensure_ascii=False).encode("utf-8")
        self._send_bytes(body, "application/json; charset=utf-8")

    def _send_offline_tiles_json(self) -> None:
        root = _offline_map_root()
        tiles_json = root / "tiles" / "tiles.json"
        if not tiles_json.is_file():
            self._send_json({"error": "offline tilejson not found"}, status=404)
            return

        with tiles_json.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        payload["tiles"] = [f"{self._request_origin()}/offline-map/tiles/{{z}}/{{x}}/{{y}}.pbf"]
        payload["scheme"] = "xyz"
        self._send_bytes(json.dumps(payload, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def _send_offline_tile(self, relative_path: str) -> None:
        root = (_offline_map_root() / "tiles").resolve()
        path = root.joinpath(*relative_path.split("/")).resolve()
        if not str(path).startswith(str(root)):
            self._send_json({"error": "not found"}, status=404)
            return
        if not path.is_file() or path.suffix != ".pbf":
            self._send_json({"error": "tile not found"}, status=404)
            return
        self._send_bytes(path.read_bytes(), "application/x-protobuf")

    def _send_offline_font(self, relative_path: str) -> None:
        root = (_offline_map_root() / "font").resolve()
        parts = [unquote(part) for part in relative_path.split("/")]
        path = root.joinpath(*parts).resolve()
        if not str(path).startswith(str(root)):
            self._send_json({"error": "not found"}, status=404)
            return
        if not path.is_file() or path.suffix != ".pbf":
            self._send_json({"error": "font not found"}, status=404)
            return
        self._send_bytes(path.read_bytes(), "application/x-protobuf")


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
