# IPGeoSearch / IP 地理搜索

IPGeoSearch is a local IP and domain geolocation search tool with a playful web interface, online map display, batch lookup, history, and export support.

IPGeoSearch 是一个本地 IP 与域名地理位置查询工具，提供动漫风前端页面、在线地图定位、批量查询、查询历史和结果导出能力。

## Features / 功能

- Single IP or domain lookup by default.
- Switchable batch lookup mode for multiple IPs and domains.
- Domain-to-IP resolution before geolocation lookup.
- Online map display with single-point and multi-point markers.
- Click a batch result to focus the map on that location.
- Copy IP, location, ASN, ISP, and coordinates.
- Query history with one-click re-query.
- Export batch results to CSV or JSON.
- Lightweight HTTP API for local integration.

## Quick Start / 快速开始

Start the web service:

```powershell
cd D:\ip\ip-geo-search
python api.py --host 127.0.0.1 --port 8787
```

Open:

```text
http://127.0.0.1:8787/
```

CLI lookup:

```powershell
python lookup.py 8.8.8.8
python lookup.py 8.8.8.8 --json
```

## Web Usage / 页面用法

1. Open the page and use the default **单个查询** mode.
2. Enter an IP or domain, such as `8.8.8.8` or `github.com`.
3. Click **立即查询** to view location, ASN, ISP, risk score, and map marker.
4. Click **多个查询** to batch query multiple IPs or domains.
5. Use **导出 CSV** or **导出 JSON** to save batch results.

## HTTP API / HTTP 接口

Lookup an IP:

```text
http://127.0.0.1:8787/lookup?ip=8.8.8.8
```

Resolve a domain:

```text
http://127.0.0.1:8787/resolve?host=github.com
```

Health check:

```text
http://127.0.0.1:8787/health
```

## Example Lookup Response / 查询示例

```json
{
  "ip": "8.8.8.8",
  "ip_version": 4,
  "results": [
    {
      "source": "local",
      "ok": true,
      "data": {
        "country": "United States",
        "region": "California",
        "network": "Google LLC"
      }
    }
  ]
}
```

## Environment / 环境

The project runs as a local Python service and serves the frontend from `src/ipgeosearch/static`.

```powershell
python api.py --host 127.0.0.1 --port 8787
```

## Roadmap / 规划

- Better IP type detection.
- More detailed risk labels.
- Dark anime theme.
- API documentation page.
- Docker packaging.

## License / 许可证

This project has not added a license yet.

本项目目前尚未添加许可证。
