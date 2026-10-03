"""RDAP 查询：把注册信息的原始 JSON 摘要成前端需要的字段。"""

from __future__ import annotations

import ipaddress
import json
import urllib.error
import urllib.request

RDAP_TIMEOUT_SECONDS = 6.0
RDAP_ENDPOINT = "https://rdap.org/ip/{ip}"
MAX_ENTITIES = 6


def fetch_json(url: str, timeout: float = RDAP_TIMEOUT_SECONDS) -> dict[str, object]:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "ip-geo-search/1.0",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8", errors="replace"))


def vcard_value(entity: dict[str, object], field_name: str) -> str:
    """从 jCard 结构里取一个字段（fn / email 等）。"""
    vcard = entity.get("vcardArray")
    if not isinstance(vcard, list) or len(vcard) < 2 or not isinstance(vcard[1], list):
        return ""
    for item in vcard[1]:
        if isinstance(item, list) and len(item) >= 4 and item[0] == field_name:
            return str(item[3])
    return ""


def summarize(payload: dict[str, object]) -> dict[str, object]:
    events: dict[str, str] = {}
    for event in payload.get("events", []):
        if not isinstance(event, dict):
            continue
        action = str(event.get("eventAction", "")).strip()
        date = str(event.get("eventDate", "")).strip()
        if action and date:
            events[action] = date

    entities: list[dict[str, object]] = []
    for entity in payload.get("entities", []):
        if not isinstance(entity, dict):
            continue
        name = vcard_value(entity, "fn")
        email = vcard_value(entity, "email")
        roles = entity.get("roles") if isinstance(entity.get("roles"), list) else []
        if name or email or roles:
            entities.append({"name": name, "email": email, "roles": roles})
        if len(entities) >= MAX_ENTITIES:
            break

    return {
        "handle": payload.get("handle", ""),
        "name": payload.get("name", ""),
        "type": payload.get("type", ""),
        "country": payload.get("country", ""),
        "startAddress": payload.get("startAddress", ""),
        "endAddress": payload.get("endAddress", ""),
        "events": events,
        "entities": entities,
        "rawStatus": payload.get("status", []),
    }


def lookup(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> dict[str, object]:
    """查询一个 IP 的 RDAP 记录。

    失败不抛错：调用方拿到的是 `available: False` 加原因，
    这样前端可以照常渲染"注册信息不可用"。
    """
    address = str(ip)
    if not ip.is_global:
        return {"ip": address, "available": False, "reason": "non-global address"}

    try:
        payload = fetch_json(RDAP_ENDPOINT.format(ip=address))
        return {"ip": address, "available": True, "rdap": summarize(payload)}
    except urllib.error.HTTPError as exc:
        return {"ip": address, "available": False, "error": f"rdap http {exc.code}"}
    except Exception as exc:
        return {"ip": address, "available": False, "error": str(exc)}
