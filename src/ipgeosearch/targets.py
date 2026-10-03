"""目标解析与校验：把用户输入的字面量收敛成 IP 或主机名。

纯函数、无 IO，供 http_app（查询参数校验）、probe（探测目标解析）与
dns（主机名合法性）共用，避免各处重复一份正则与 `strip(".")` 细节。
"""

from __future__ import annotations

import ipaddress
import re
from urllib.parse import urlparse

# 标签不以 - 开头结尾、总长不超过 253、字符集限定为字母数字与 . -
HOSTNAME_PATTERN = re.compile(r"^(?=.{1,253}$)(?!-)[A-Za-z0-9.-]+(?<!-)$")


def parse_ip(value: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address:
    """解析 IP 字面量，允许首尾空白；非法时抛 ValueError。"""
    return ipaddress.ip_address(value.strip())


def is_literal_ip(value: str) -> bool:
    try:
        parse_ip(value)
    except ValueError:
        return False
    return True


def normalize_host(value: str) -> str:
    """去掉首尾空白与 FQDN 末尾的点（`example.com.` 是合法写法）。"""
    return value.strip().strip(".")


def is_valid_hostname(host: str) -> bool:
    """判断是否为可安全用于 DNS/连接查询的主机名。"""
    return bool(HOSTNAME_PATTERN.match(host)) and ".." not in host


def host_from_target(target: str) -> str:
    """从 IP / 域名 / URL 字面量中取出主机名，取不到时抛 ValueError。"""
    parsed = urlparse(target if "://" in target else f"//{target}")
    host = normalize_host(parsed.hostname or target)
    if not host:
        raise ValueError("missing target")
    return host


def require_host(target: str) -> str:
    """取出主机名并校验：要么是合法 IP，要么是合法主机名。"""
    host = host_from_target(target)
    if not is_literal_ip(host) and not is_valid_hostname(host):
        raise ValueError("invalid target") from None
    return host
