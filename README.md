# IPGeoSearch / IP 地理搜索

Offline IP geolocation search with multi-source lookup, ASN detection, and map-ready output.

IPGeoSearch is a local IP geolocation toolkit that combines `ip2region`, `ip-location-db`, and optional MaxMind GeoIP2 MMDB data. It is built for fast offline IP lookup, data comparison across sources, and future map visualization.

IPGeoSearch 是一个离线 IP 地理搜索工具，整合 `ip2region`、`ip-location-db` 和可选的 MaxMind GeoIP2 MMDB 数据，支持快速查询 IP 归属地、ASN 信息，并为地图可视化展示预留接口。

## Features / 功能

- Fast offline IP lookup with `ip2region` `.xdb` files.
- Country and ASN lookup from `ip-location-db` CSV datasets.
- Optional MaxMind GeoIP2 `.mmdb` reader support.
- IPv4 and IPv6 support.
- CLI query tool.
- Lightweight HTTP API.
- Web page with offline map display for IP search and location markers.

## Data Sources / 数据源

IPGeoSearch reads existing sibling project directories by default:

```text
../ip2region
../ip-location-db
../GeoIP2-python
```

It does not copy large database files into this project.

默认情况下，IPGeoSearch 会读取当前目录旁边已有的三个项目，不会复制大型数据库文件。

## Quick Start / 快速开始

```powershell
cd D:\ip\ip-geo-search
python lookup.py 8.8.8.8
python lookup.py 8.8.8.8 --json
python lookup.py 2404:6800:4005:80a::200e --json
```

Query selected sources:

```powershell
python lookup.py 8.8.8.8 --source ip2region --source csv --json
```

List available `ip-location-db` CSV datasets:

```powershell
python lookup.py --list-csv
```

## HTTP API / HTTP 接口

Start the API server:

```powershell
python api.py --host 127.0.0.1 --port 8787
```

Open the web page:

```text
http://127.0.0.1:8787/
```

By default, the web page uses a local SVG world map generated from the iPhotron offline PBF vector tiles. The source map data is read from:

```text
D:\iPhotron-LocalPhotoAlbumManager\src\maps
```

You can point IPGeoSearch to another compatible offline map directory:

```powershell
$env:IPGEOSEARCH_OFFLINE_MAP_ROOT="D:\path\to\maps"
python api.py --host 127.0.0.1 --port 8787
```

If the offline map directory is unavailable, the web page falls back to OpenStreetMap. To use Amap instead, set an Amap Web JS API key before starting the server:

```powershell
$env:MAP_PROVIDER="amap"
$env:AMAP_WEB_KEY="your-amap-web-js-api-key"
python api.py --host 127.0.0.1 --port 8787
```

Lookup:

```text
http://127.0.0.1:8787/lookup?ip=8.8.8.8
```

List datasets:

```text
http://127.0.0.1:8787/datasets
```

Health check:

```text
http://127.0.0.1:8787/health
```

## Example Output / 示例输出

```json
{
  "ip": "8.8.8.8",
  "ip_version": 4,
  "results": [
    {
      "source": "ip2region",
      "ok": true,
      "data": {
        "region": "United States|California|0|Google LLC|US",
        "ip_version": 4
      }
    },
    {
      "source": "ip-location-db",
      "ok": true,
      "data": {
        "user-country": {
          "country_code": "US"
        },
        "origin-asn": {
          "autonomous_system_number": "15169",
          "autonomous_system_organization": "Google LLC"
        }
      }
    }
  ]
}
```

## Optional GeoIP2 MMDB / 可选 GeoIP2 数据库

`GeoIP2-python` is a reader library. It does not include MaxMind database files.

To enable GeoIP2 lookup, set `GEOIP2_MMDB`:

```powershell
$env:GEOIP2_MMDB="D:\data\GeoLite2-City.mmdb"
python lookup.py 8.8.8.8 --source geoip2 --json
```

## Environment Variables / 环境变量

```powershell
$env:IP2REGION_ROOT="D:\ip\ip2region"
$env:IP_LOCATION_DB_ROOT="D:\ip\ip-location-db"
$env:GEOIP2_PYTHON_ROOT="D:\ip\GeoIP2-python"
$env:GEOIP2_MMDB="D:\data\GeoLite2-City.mmdb"
$env:IPGEOSEARCH_OFFLINE_MAP_ROOT="D:\iPhotron-LocalPhotoAlbumManager\src\maps"
```

## Roadmap / 规划

- More precise map markers when city-level latitude and longitude are available.
- Batch IP lookup.
- Export results to CSV and JSON.
- More source comparison views.
- Docker packaging.

## License / 许可证

This integration project is not yet licensed. Please check the licenses of the upstream data sources before using their datasets.

本项目目前尚未添加许可证。使用上游数据时，请分别确认 `ip2region`、`ip-location-db`、GeoIP2/GeoLite2 等数据源的许可证要求。
