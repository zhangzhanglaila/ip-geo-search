# ip-geo-search / IP 地理搜索

ip-geo-search is a local IP and domain geolocation search tool with a playful web interface, online map display, batch lookup, network intelligence, history, and export support.

ip-geo-search 是一个本地 IP 与域名地理位置查询工具，提供动漫风前端页面、在线地图定位、批量查询、网络情报分析、查询历史和结果导出能力。

## Table of Contents / 目录

- [Features / 功能](#features--功能)
- [Quick Start / 快速开始](#quick-start--快速开始)
- [Web Usage / 页面用法](#web-usage--页面用法)
- [CLI Options / 命令行选项](#cli-options--命令行选项)
- [HTTP API / HTTP 接口](#http-api--http-接口)
- [Docker / Docker 部署](#docker--docker-部署)
- [Lookup Response / 查询返回](#lookup-response--查询返回)
- [Environment / 环境](#environment--环境)
- [Roadmap / 规划](#roadmap--规划)
- [License / 许可证](#license--许可证)

## Features / 功能

| Area / 分类 | Capability / 能力 |
| --- | --- |
| Lookup / 查询 | Single IP or domain lookup by default; switchable batch mode for multiple IPs and domains. / 默认单个 IP 或域名查询，可切换为批量模式查询多个目标。 |
| Resolution / 解析 | Domain-to-IP resolution before geolocation; batch domains expand resolved addresses into result rows. / 查询前先做域名到 IP 解析，批量域名会展开为多条结果。 |
| DNS | A / AAAA / CNAME / MX / NS record lookup and reverse DNS lookup. / 支持 A、AAAA、CNAME、MX、NS 记录查询与反向 DNS 查询。 |
| Ownership / 归属 | RDAP / WHOIS summary for public IP ownership and allocation data. / 通过 RDAP / WHOIS 汇总公网 IP 归属与分配信息。 |
| Intelligence / 情报 | DNSBL blacklist checks; heuristic proxy, VPN, Tor, CDN, hosting, mobile, and private detection; TCP probe on ports 80 and 443. / DNSBL 黑名单检查，启发式识别代理、VPN、Tor、CDN、托管、移动网络与私有地址，并对 80/443 端口做 TCP 连通探测。 |
| Map / 地图 | Online single- and multi-point markers, same-coordinate grouping, batch filters, optional heatmap and order lines, rich popups, and click-to-focus. / 在线单点与多点标注、同坐标聚合、批量筛选、可选热力图与顺序连线、丰富弹窗，以及点击结果定位。 |
| History / 历史 | Query history with one-click re-query, favorites, item deletion, and clear-all. / 查询历史支持一键重查、收藏、单条删除与全部清空。 |
| Batch / 批量 | TXT/CSV import, duplicate removal, failure retry, and result summary. / 支持 TXT/CSV 导入、去重、失败重试与结果统计。 |
| Export / 导出 | Export batch results to CSV or JSON with IP type, risk, ASN, and ISP fields. / 批量结果可导出为 CSV 或 JSON，包含 IP 类型、风险、ASN 与 ISP 字段。 |
| Deployment / 部署 | Optional API key protection, [Docker](https://www.docker.com/) support, a lightweight HTTP API, and a built-in API docs panel. / 可选 API Key 保护、Docker 部署、轻量 HTTP 接口，以及内置 API 文档面板。 |
| Theme / 主题 | Light / dark anime-style theme switch. / 明暗动漫风主题切换。 |

[Back to top / 返回顶部](#ip-geo-search--ip-地理搜索)

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

[Back to top / 返回顶部](#ip-geo-search--ip-地理搜索)

## Web Usage / 页面用法

1. Open the page and use the default **单个查询** mode.
2. Enter an IP or domain, such as `8.8.8.8` or `github.com`.
3. Click **立即查询** to view location, ASN, ISP, risk score, and map marker.
4. Click **多个查询** to batch query multiple IPs or domains.
5. Import TXT/CSV files or paste multiple targets into the batch box.
6. Use result filters, heatmap, and line display to inspect batch map results.
7. Use **重试失败** to re-run failed batch targets.
8. Use **导出 CSV** or **导出 JSON** to save batch results.
9. If API key protection is enabled, click **API Key** in the top bar and enter the key once.

[Back to top / 返回顶部](#ip-geo-search--ip-地理搜索)

## CLI Options / 命令行选项

`python lookup.py` accepts the following options:

| Option / 选项 | Description / 说明 |
| --- | --- |
| `ip` | IP address to query. / 要查询的 IP 地址。 |
| `--source` | Source to query (`ip2region`, `ip-location-db`, `csv`, `geoip2`). Can be repeated. Defaults to all sources. / 指定查询数据源，可重复；默认查询全部数据源。 |
| `--csv-db` | ip-location-db dataset. Can be repeated. / 指定 ip-location-db 数据集，可重复。 |
| `--ip2region-cache` | ip2region cache policy (`content`, `vector`, `file`). Defaults to `content`. / ip2region 缓存策略，默认 `content`。 |
| `--list-csv` | List available CSV datasets. / 列出可用的 CSV 数据集。 |
| `--json` | Print JSON output. / 以 JSON 格式输出。 |

Example:

```powershell
python lookup.py 8.8.8.8 --source geoip2 --json
```

[Back to top / 返回顶部](#ip-geo-search--ip-地理搜索)

## HTTP API / HTTP 接口

All endpoints are served by `python api.py`. Base URL: `http://127.0.0.1:8787`.

| Endpoint / 接口 | Description / 说明 |
| --- | --- |
| [`/lookup?ip=8.8.8.8`](http://127.0.0.1:8787/lookup?ip=8.8.8.8) | Look up an IP address. / 查询 IP 地址。 |
| [`/resolve?host=github.com`](http://127.0.0.1:8787/resolve?host=github.com) | Resolve a domain to addresses. / 将域名解析为地址。 |
| [`/dns?host=github.com`](http://127.0.0.1:8787/dns?host=github.com) | Look up DNS records. / 查询 DNS 记录。 |
| [`/reverse-dns?ip=8.8.8.8`](http://127.0.0.1:8787/reverse-dns?ip=8.8.8.8) | Reverse DNS lookup. / 反向 DNS 查询。 |
| [`/intel?ip=8.8.8.8`](http://127.0.0.1:8787/intel?ip=8.8.8.8) | Network intelligence summary. / 网络情报汇总。 |
| [`/rdap?ip=8.8.8.8`](http://127.0.0.1:8787/rdap?ip=8.8.8.8) | RDAP / WHOIS summary. / RDAP / WHOIS 汇总。 |
| [`/probe?target=github.com`](http://127.0.0.1:8787/probe?target=github.com) | TCP connectivity probe. / TCP 连通探测。 |
| [`/datasets`](http://127.0.0.1:8787/datasets) | List available datasets. / 列出可用数据集。 |
| [`/health`](http://127.0.0.1:8787/health) | Health check. / 健康检查。 |

Optional API key:

```powershell
$env:IPGEOSEARCH_API_KEY="change-me"
python api.py --host 127.0.0.1 --port 8787
```

When enabled, API requests must include `X-API-Key: change-me` or `?api_key=change-me`. The web page can store the key from the **API Key** button.

启用后，接口请求需携带 `X-API-Key: change-me` 或 `?api_key=change-me`。页面可通过 **API Key** 按钮保存该密钥。

[Back to top / 返回顶部](#ip-geo-search--ip-地理搜索)

## Docker / Docker 部署

Build and run:

```powershell
docker build -t ip-geo-search .
docker run --rm -p 8787:8787 ip-geo-search
```

Run with API key protection:

```powershell
docker run --rm -p 8787:8787 -e IPGEOSEARCH_API_KEY=change-me ip-geo-search
```

[Back to top / 返回顶部](#ip-geo-search--ip-地理搜索)

## Lookup Response / 查询返回

The lookup API returns the queried IP, IP version, and a `results` array. Each item contains:

| Field / 字段 | Description / 说明 |
| --- | --- |
| `source` | Local lookup module name. / 本地查询模块名称。 |
| `ok` | Whether the lookup succeeded. / 查询是否成功。 |
| `data` | Matched location, network, ASN, or coordinate data. / 匹配到的位置、网络、ASN 或坐标数据。 |
| `error` | Error message when a lookup module cannot return data. / 查询模块无法返回数据时的错误信息。 |

查询接口会返回 IP、IP 版本和 `results` 数组，每个结果项包含以上字段。

[Back to top / 返回顶部](#ip-geo-search--ip-地理搜索)

## Environment / 环境

The project runs as a local Python service (requires Python 3.10+) and serves the frontend from `src/ipgeosearch/static`.

本项目以本地 Python 服务运行（需要 Python 3.10 及以上），前端资源由 `src/ipgeosearch/static` 提供。

```powershell
python api.py --host 127.0.0.1 --port 8787
```

[Back to top / 返回顶部](#ip-geo-search--ip-地理搜索)

## Roadmap / 规划

- Optional packaged desktop build. / 可选的桌面端打包构建。
- Larger offline-free intelligence source integrations. / 集成更多在线情报数据源。

[Back to top / 返回顶部](#ip-geo-search--ip-地理搜索)

## License / 许可证

This project has not added a license yet.

本项目目前尚未添加许可证。

[Back to top / 返回顶部](#ip-geo-search--ip-地理搜索)
