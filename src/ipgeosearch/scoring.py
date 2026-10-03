"""IP 类型判定与风险评分的唯一实现。

前端曾经维护了第二套等价逻辑（`classifyIp`），两边的正则词表、加分项与阈值都不一致，
同一个 IP 在"欺诈风险评估"卡片（前端计算）和 `/intel`（后端计算）里会得到不同结论。
这里把规则收敛成纯函数，`/lookup`、`/intel`、批量查询与 CLI 共用同一份结果，
前端只负责渲染。
"""

from __future__ import annotations

import ipaddress
import json
import re
from typing import Any

IP_TYPE_CDN = "CDN / 边缘网络"
IP_TYPE_HOSTING = "云服务 / 机房 IP"
IP_TYPE_MOBILE = "移动网络"
IP_TYPE_BROADBAND = "宽带网络"
IP_TYPE_COMMERCIAL = "商业 IP"
IP_TYPE_UNKNOWN = "未知"
IP_TYPE_PRIVATE = "非公网地址"

LEVEL_LOW = "low"
LEVEL_MEDIUM = "medium"
LEVEL_HIGH = "high"

SUMMARY_HIGH = "较高风险 - 重点关注"
SUMMARY_MEDIUM = "中低风险 - 建议复核"
SUMMARY_LOW = "极低风险 - 安全可信"

CDN_PATTERN = re.compile(r"cloudflare|akamai|fastly|cdn|edgecast|cachefly")
HOSTING_PATTERN = re.compile(
    r"cloud|hosting|host|server|data\s*center|datacenter|colo|aws|amazon|google|"
    r"azure|microsoft|oracle|digitalocean|linode|ovh|aliyun|alibaba|tencent|huawei"
)
MOBILE_PATTERN = re.compile(r"mobile|cellular|wireless|cmcc|chinamobile|移动")
BROADBAND_PATTERN = re.compile(r"telecom|unicom|broadband|宽带|电信|联通|cable|fiber|dsl")
PROXY_PATTERN = re.compile(r"proxy|vpn|tor|anonymous|privacy|crawler|scraper")
ABUSE_PATTERN = re.compile(r"abuse|spam|blacklist|malware|botnet")

TAG_CDN = "CDN/边缘网络"
TAG_HOSTING = "云服务/机房"
TAG_MOBILE = "移动网络"
TAG_BROADBAND = "宽带网络"
TAG_PROXY = "疑似代理/VPN/Tor"
TAG_ABUSE = "疑似滥用风险"
TAG_DNSBL = "命中 DNSBL"
TAG_PRIVATE = "非公网地址"
TAG_DEFAULT = "常规网络"

CDN_SCORE = 18
HOSTING_SCORE = 24
MOBILE_SCORE = 4
BROADBAND_SCORE = 2
PROXY_SCORE = 34
ABUSE_SCORE = 30
DNSBL_SCORE = 42

MAX_SCORE = 98
HIGH_RISK_SCORE = 45
LOW_RISK_SCORE = 20

# 类型按优先级取第一个命中的分类：Cloudflare 这类词会同时命中 CDN 与机房词表，
# 用优先级链避免重复加分，也让"IP 类型"字段只有一个确定取值。
TYPE_RULES: tuple[tuple[str, re.Pattern[str], str, str, int], ...] = (
    ("cdn", CDN_PATTERN, IP_TYPE_CDN, TAG_CDN, CDN_SCORE),
    ("hosting", HOSTING_PATTERN, IP_TYPE_HOSTING, TAG_HOSTING, HOSTING_SCORE),
    ("mobile", MOBILE_PATTERN, IP_TYPE_MOBILE, TAG_MOBILE, MOBILE_SCORE),
    ("broadband", BROADBAND_PATTERN, IP_TYPE_BROADBAND, TAG_BROADBAND, BROADBAND_SCORE),
)


def network_text(lookup_payload: dict[str, Any] | None, extra_text: str = "") -> str:
    """把各数据源返回的内容拼成一段用于关键词匹配的小写文本。"""
    parts: list[str] = []
    for result in (lookup_payload or {}).get("results") or []:
        if isinstance(result, dict):
            parts.append(json.dumps(result.get("data", {}), ensure_ascii=False))
    if extra_text:
        parts.append(extra_text)
    return " ".join(parts).lower()


def has_network_identity(lookup_payload: dict[str, Any] | None) -> bool:
    """数据源是否给出了 ASN 信息，用于区分"商业 IP"与"未知"。"""
    for result in (lookup_payload or {}).get("results") or []:
        data = result.get("data") if isinstance(result, dict) else None
        if not isinstance(data, dict):
            continue
        for row in data.values():
            if isinstance(row, dict) and row.get("autonomous_system_number"):
                return True
    return False


def detect_flags(
    ip: ipaddress.IPv4Address | ipaddress.IPv6Address,
    text: str,
    dnsbl_listed: bool = False,
) -> dict[str, bool]:
    return {
        "private": ip.is_private,
        "loopback": ip.is_loopback,
        "reserved": ip.is_reserved,
        "multicast": ip.is_multicast,
        "global": ip.is_global,
        "hosting": bool(HOSTING_PATTERN.search(text)),
        "cdn": bool(CDN_PATTERN.search(text)),
        "mobile": bool(MOBILE_PATTERN.search(text)),
        "broadband": bool(BROADBAND_PATTERN.search(text)),
        "proxy": bool(PROXY_PATTERN.search(text)),
        "abuse": bool(ABUSE_PATTERN.search(text)),
        "dnsblListed": bool(dnsbl_listed),
    }


def classify(
    ip: ipaddress.IPv4Address | ipaddress.IPv6Address,
    lookup_payload: dict[str, Any] | None = None,
    extra_text: str = "",
    dnsbl_listed: bool = False,
) -> dict[str, Any]:
    """返回统一的评估结果，供 /lookup、/intel 与 CLI 共用。"""
    text = network_text(lookup_payload, extra_text)
    flags = detect_flags(ip, text, dnsbl_listed)
    has_asn = has_network_identity(lookup_payload)

    score = 0
    tags: list[str] = []
    ip_type = IP_TYPE_COMMERCIAL if has_asn else IP_TYPE_UNKNOWN

    if flags["private"] or flags["loopback"] or flags["reserved"]:
        ip_type = IP_TYPE_PRIVATE
        tags.append(TAG_PRIVATE)
    else:
        for key, _, type_name, tag, points in TYPE_RULES:
            if flags[key]:
                ip_type = type_name
                tags.append(tag)
                score += points
                break
        if not tags:
            tags.append(TAG_DEFAULT)

    if flags["proxy"]:
        score += PROXY_SCORE
        tags.append(TAG_PROXY)
    if flags["abuse"]:
        score += ABUSE_SCORE
        tags.append(TAG_ABUSE)
    if flags["dnsblListed"]:
        score += DNSBL_SCORE
        tags.append(TAG_DNSBL)

    score = min(MAX_SCORE, score)
    if score >= HIGH_RISK_SCORE:
        level, summary = LEVEL_HIGH, SUMMARY_HIGH
    elif score > LOW_RISK_SCORE:
        level, summary = LEVEL_MEDIUM, SUMMARY_MEDIUM
    else:
        level, summary = LEVEL_LOW, SUMMARY_LOW

    return {
        "flags": flags,
        "score": score,
        "level": level,
        "summary": summary,
        "tags": list(dict.fromkeys(tags)),
        "ipType": ip_type,
        "proxyLike": flags["proxy"],
        "serverLike": flags["cdn"] or flags["hosting"],
        "abuseLike": flags["abuse"] or flags["dnsblListed"],
    }
