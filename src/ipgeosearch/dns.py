"""手写 DNS 报文编解码与查询（纯标准库）。

包含三部分：
- 报文层：`encode_name` / `read_name` / `decode_record` / `parse_response`，
  全部是纯函数，可直接用手工构造的报文做测试；
- 查询层：`query_server` / `resolve_records`（正向）、`reverse_lookup`（反向）；
- DNSBL：`dnsbl_lookup`。

压缩指针的循环检测与事务 ID 校验是这个模块最容易出错的细节，改动时请保留。
"""

from __future__ import annotations

import ipaddress
import os
import random
import socket
import struct

DNS_RECORD_TYPES = {
    "A": 1,
    "AAAA": 28,
    "CNAME": 5,
    "MX": 15,
    "NS": 2,
}
DNS_TYPE_NAMES = {value: key for key, value in DNS_RECORD_TYPES.items()}
DNS_TIMEOUT_SECONDS = 3.0
DEFAULT_DNS_SERVER = "223.5.5.5"
DNSBL_ZONES = (
    "zen.spamhaus.org",
    "bl.spamcop.net",
    "dnsbl.sorbs.net",
)


def dns_server() -> str:
    return os.getenv("DNS_SERVER", DEFAULT_DNS_SERVER)


def encode_name(host: str) -> bytes:
    """把域名编码成 DNS 报文里的标签序列（IDNA，末尾以 0 长度字节结束）。"""
    return b"".join(bytes([len(part.encode("idna"))]) + part.encode("idna") for part in host.split(".")) + b"\x00"


def read_name(message: bytes, offset: int) -> tuple[str, int]:
    """读取域名，支持压缩指针；返回 (域名, 指针之后的偏移)。

    指针会跳回报文前部，必须记录已访问偏移并在重访时抛错，
    否则畸形报文会让服务端陷入死循环。
    """
    labels: list[str] = []
    jumped = False
    next_offset = offset
    seen_offsets: set[int] = set()

    while True:
        if offset >= len(message):
            raise ValueError("invalid dns name offset")
        length = message[offset]
        if length & 0xC0 == 0xC0:
            if offset + 1 >= len(message):
                raise ValueError("invalid dns name pointer")
            pointer = ((length & 0x3F) << 8) | message[offset + 1]
            if pointer in seen_offsets:
                raise ValueError("recursive dns name pointer")
            seen_offsets.add(pointer)
            if not jumped:
                next_offset = offset + 2
            offset = pointer
            jumped = True
            continue
        if length == 0:
            offset += 1
            if not jumped:
                next_offset = offset
            break

        offset += 1
        label = message[offset : offset + length]
        if len(label) != length:
            raise ValueError("truncated dns name")
        try:
            labels.append(label.decode("idna"))
        except UnicodeError:
            labels.append(label.decode("ascii", errors="replace"))
        offset += length

    return ".".join(labels), next_offset


def decode_record(message: bytes, record_type: int, rdata_offset: int, rdlength: int) -> str:
    """把单条记录的 rdata 解成可读字符串；不认识的类型返回空串。"""
    data = message[rdata_offset : rdata_offset + rdlength]
    if record_type == DNS_RECORD_TYPES["A"] and rdlength == 4:
        return str(ipaddress.IPv4Address(data))
    if record_type == DNS_RECORD_TYPES["AAAA"] and rdlength == 16:
        return str(ipaddress.IPv6Address(data))
    if record_type in (DNS_RECORD_TYPES["CNAME"], DNS_RECORD_TYPES["NS"]):
        value, _ = read_name(message, rdata_offset)
        return value
    if record_type == DNS_RECORD_TYPES["MX"] and rdlength >= 3:
        preference = struct.unpack("!H", data[:2])[0]
        exchange, _ = read_name(message, rdata_offset + 2)
        return f"{preference} {exchange}"
    return ""


def parse_response(response: bytes, transaction_id: int) -> list[dict[str, object]]:
    """解析 DNS 响应报文，返回 A/AAAA/CNAME/MX/NS 记录。

    独立成函数便于直接用手工构造的报文做测试，不必真的发 UDP 请求。
    """
    if len(response) < 12:
        raise ValueError("dns response too short")

    response_id, flags, question_count, answer_count, _, _ = struct.unpack("!HHHHHH", response[:12])
    if response_id != transaction_id:
        raise ValueError("dns transaction mismatch")
    if flags & 0x000F:
        raise ValueError(f"dns server returned code {flags & 0x000F}")

    offset = 12
    for _ in range(question_count):
        _, offset = read_name(response, offset)
        offset += 4

    records: list[dict[str, object]] = []
    for _ in range(answer_count):
        _, offset = read_name(response, offset)
        if offset + 10 > len(response):
            raise ValueError("truncated dns answer")
        answer_type, answer_class, ttl, rdlength = struct.unpack("!HHIH", response[offset : offset + 10])
        offset += 10
        rdata_offset = offset
        offset += rdlength
        record_name = DNS_TYPE_NAMES.get(answer_type)
        if answer_class != 1 or not record_name:
            continue
        value = decode_record(response, answer_type, rdata_offset, rdlength)
        if value:
            records.append({"type": record_name, "value": value, "ttl": ttl, "source": "dns"})
    return records


def query_server(host: str, record_type: int, server: str) -> list[dict[str, object]]:
    """向指定 DNS 服务器发一次 UDP 查询并解析响应。"""
    transaction_id = random.randrange(0, 65536)
    header = struct.pack("!HHHHHH", transaction_id, 0x0100, 1, 0, 0, 0)
    question = encode_name(host) + struct.pack("!HH", record_type, 1)
    packet = header + question

    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as client:
        client.settimeout(DNS_TIMEOUT_SECONDS)
        client.sendto(packet, (server, 53))
        response, _ = client.recvfrom(4096)

    return parse_response(response, transaction_id)


def _append_record(records: dict[str, list[dict[str, object]]], record: dict[str, object]) -> None:
    record_type = str(record.get("type", ""))
    value = str(record.get("value", ""))
    if record_type not in records or not value:
        return
    if any(row.get("value") == value for row in records[record_type]):
        return
    records[record_type].append(record)


def resolve_records(host: str) -> dict[str, object]:
    """逐类型查询并把系统解析器结果合并进来，作为 DNS 查询失败的兜底。"""
    server = dns_server()
    records: dict[str, list[dict[str, object]]] = {name: [] for name in DNS_RECORD_TYPES}
    errors: dict[str, str] = {}

    for record_name, record_type in DNS_RECORD_TYPES.items():
        try:
            for record in query_server(host, record_type, server):
                _append_record(records, record)
        except Exception as exc:
            errors[record_name] = str(exc)

    try:
        rows = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
        for row in rows:
            address = row[4][0]
            record_type = "AAAA" if ":" in address else "A"
            _append_record(records, {"type": record_type, "value": address, "ttl": None, "source": "system"})
    except socket.gaierror as exc:
        if not records["A"] and not records["AAAA"]:
            errors["system"] = exc.strerror or str(exc)

    return {
        "host": host,
        "server": server,
        "records": records,
        "errors": errors,
        "addresses": sorted({row["value"] for record_type in ("A", "AAAA") for row in records[record_type]}),
    }


def reverse_lookup(ip: str) -> dict[str, object]:
    """反向解析（走系统解析器），失败时把原因放进 error 字段而不是抛错。"""
    try:
        hostname, aliases, addresses = socket.gethostbyaddr(ip)
        return {
            "ip": ip,
            "hostname": hostname,
            "aliases": aliases,
            "addresses": addresses,
        }
    except (socket.herror, socket.gaierror, TimeoutError) as exc:
        return {"ip": ip, "hostname": "", "aliases": [], "addresses": [], "error": str(exc)}


def dnsbl_lookup(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> dict[str, object]:
    """查询若干 DNSBL 黑名单；本应用只支持 IPv4、且只查公网地址。"""
    if ip.version != 4:
        return {"checked": False, "reason": "DNSBL only supports IPv4 in this app", "matches": [], "errors": {}}
    if not ip.is_global:
        return {"checked": False, "reason": "non-global address", "matches": [], "errors": {}}

    server = dns_server()
    reversed_ip = ".".join(reversed(str(ip).split(".")))
    matches: list[dict[str, object]] = []
    errors: dict[str, str] = {}
    for zone in DNSBL_ZONES:
        query = f"{reversed_ip}.{zone}"
        try:
            records = query_server(query, DNS_RECORD_TYPES["A"], server)
            if records:
                matches.append({"zone": zone, "records": records})
        except Exception as exc:
            errors[zone] = str(exc)
    return {"checked": True, "server": server, "matches": matches, "errors": errors}
