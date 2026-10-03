"""DNS 报文编解码测试（纯函数，不发真实请求）。"""

from __future__ import annotations

import struct

import pytest

from ipgeosearch.server import (
    DNS_RECORD_TYPES,
    _decode_dns_record,
    _encode_dns_name,
    _parse_dns_response,
    _read_dns_name,
)

QUESTION = b"\x07example\x03com\x00" + struct.pack("!HH", 1, 1)


def build_response(transaction_id: int, rdata_list: list[tuple[int, bytes]], flags: int = 0x8180) -> bytes:
    header = struct.pack("!HHHHHH", transaction_id, flags, 1, len(rdata_list), 0, 0)
    body = QUESTION
    for record_type, rdata in rdata_list:
        body += b"\xc0\x0c" + struct.pack("!HHIH", record_type, 1, 300, len(rdata)) + rdata
    return header + body


def test_encode_dns_name():
    assert _encode_dns_name("example.com") == b"\x07example\x03com\x00"


def test_encode_dns_name_supports_idna():
    encoded = _encode_dns_name("例子.测试")
    assert encoded.endswith(b"\x00")
    assert b"xn--" in encoded


def test_read_dns_name_with_pointer():
    # QUESTION 位于报文起始处，因此指向它的压缩指针是 0x00。
    message = QUESTION + b"\xc0\x00"
    name, offset = _read_dns_name(message, len(QUESTION))
    assert name == "example.com"
    assert offset == len(QUESTION) + 2


def test_read_dns_name_detects_pointer_loop():
    # 指针指向自身，必须抛错而不是死循环。
    message = b"\x00" * 12 + b"\xc0\x0c"
    with pytest.raises(ValueError, match="recursive"):
        _read_dns_name(message, 12)


def test_read_dns_name_detects_truncation():
    with pytest.raises(ValueError):
        _read_dns_name(b"\x07exam", 0)


def test_parse_a_record():
    records = _parse_dns_response(build_response(0x1234, [(1, bytes([93, 184, 216, 34]))]), 0x1234)
    assert records == [{"type": "A", "value": "93.184.216.34", "ttl": 300, "source": "dns"}]


def test_parse_aaaa_record():
    rdata = bytes.fromhex("20010db8" + "00" * 11 + "01")
    records = _parse_dns_response(build_response(7, [(28, rdata)]), 7)
    assert records[0]["type"] == "AAAA"
    assert records[0]["value"] == "2001:db8::1"


def test_parse_cname_record_using_compression():
    records = _parse_dns_response(build_response(9, [(5, b"\xc0\x0c")]), 9)
    assert records == [{"type": "CNAME", "value": "example.com", "ttl": 300, "source": "dns"}]


def test_parse_mx_record():
    rdata = struct.pack("!H", 10) + b"\x04mail\xc0\x0c"
    records = _parse_dns_response(build_response(11, [(15, rdata)]), 11)
    assert records[0]["type"] == "MX"
    assert records[0]["value"].startswith("10 mail.")


def test_parse_ns_record():
    records = _parse_dns_response(build_response(3, [(2, b"\xc0\x0c")]), 3)
    assert records[0]["type"] == "NS"


def test_parse_skips_non_internet_class():
    header = struct.pack("!HHHHHH", 5, 0x8180, 1, 1, 0, 0)
    body = QUESTION + b"\xc0\x0c" + struct.pack("!HHIH", 1, 3, 300, 4) + bytes([1, 2, 3, 4])
    assert _parse_dns_response(header + body, 5) == []


def test_parse_rejects_short_response():
    with pytest.raises(ValueError, match="too short"):
        _parse_dns_response(b"\x00" * 8, 1)


def test_parse_rejects_transaction_mismatch():
    with pytest.raises(ValueError, match="transaction mismatch"):
        _parse_dns_response(build_response(1, [(1, bytes([1, 2, 3, 4]))]), 2)


def test_parse_rejects_error_rcode():
    with pytest.raises(ValueError, match="returned code 3"):
        _parse_dns_response(build_response(1, [], flags=0x8183), 1)


def test_parse_detects_pointer_loop_in_answers():
    header = struct.pack("!HHHHHH", 1, 0x8180, 0, 1, 0, 0)
    with pytest.raises(ValueError, match="recursive"):
        _parse_dns_response(header + b"\xc0\x0c", 1)


def test_parse_detects_truncated_answer():
    # 根名字（\x00）可以解析，但后面不足 10 字节的答案头。
    header = struct.pack("!HHHHHH", 1, 0x8180, 0, 1, 0, 0)
    with pytest.raises(ValueError, match="truncated"):
        _parse_dns_response(header + b"\x00\x00\x01", 1)


def test_decode_returns_empty_for_unknown_type():
    assert _decode_dns_record(b"\x00" * 32, 99, 0, 4) == ""


def test_record_type_table_is_consistent():
    assert DNS_RECORD_TYPES["A"] == 1
    assert set(DNS_RECORD_TYPES) == {"A", "AAAA", "CNAME", "MX", "NS"}
