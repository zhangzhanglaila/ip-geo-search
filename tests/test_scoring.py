"""风险评估规则测试。"""

from __future__ import annotations

import ipaddress

from ipgeosearch import scoring


def payload(country: str = "", asn: str = "", org: str = "") -> dict:
    rows: dict[str, dict[str, str]] = {}
    if country:
        rows["user-country"] = {"country_code": country}
    if asn or org:
        rows["origin-asn"] = {
            "autonomous_system_number": asn,
            "autonomous_system_organization": org,
        }
    return {"ip": "1.1.1.1", "results": [{"source": "ip-location-db", "ok": True, "data": rows}]}


def classify(ip: str, lookup_payload: dict | None = None, **kwargs) -> dict:
    return scoring.classify(ipaddress.ip_address(ip), lookup_payload, **kwargs)


def test_private_address_is_flagged_without_score():
    result = classify("10.0.0.1")
    assert result["ipType"] == scoring.IP_TYPE_PRIVATE
    assert result["tags"] == [scoring.TAG_PRIVATE]
    assert result["score"] == 0
    assert result["level"] == scoring.LEVEL_LOW


def test_cdn_organization_is_detected():
    result = classify("1.1.1.1", payload(country="US", asn="13335", org="Cloudflare, Inc."))
    assert result["ipType"] == scoring.IP_TYPE_CDN
    assert result["score"] == scoring.CDN_SCORE
    assert result["serverLike"] is True
    assert result["ipType"] != scoring.IP_TYPE_HOSTING


def test_cdn_and_hosting_keywords_do_not_double_count():
    # Cloudflare 同时命中 cdn 与 hosting 两张词表，按优先级链只应计一次分。
    result = classify("1.1.1.1", payload(asn="13335", org="Cloudflare, Inc."))
    assert result["score"] == scoring.CDN_SCORE
    assert result["score"] < scoring.CDN_SCORE + scoring.HOSTING_SCORE


def test_hosting_organization_scores_between_low_and_high():
    result = classify("8.8.8.8", payload(asn="15169", org="Google LLC"))
    assert result["ipType"] == scoring.IP_TYPE_HOSTING
    assert result["score"] == scoring.HOSTING_SCORE
    assert result["level"] == scoring.LEVEL_MEDIUM


def test_mobile_and_broadband_types():
    mobile = classify("117.151.83.202", payload(asn="9808", org="China Mobile Communications"))
    assert mobile["ipType"] == scoring.IP_TYPE_MOBILE
    assert mobile["score"] == scoring.MOBILE_SCORE

    broadband = classify("114.114.114.114", payload(asn="4134", org="Chinanet broadband"))
    assert broadband["ipType"] == scoring.IP_TYPE_BROADBAND
    assert broadband["score"] == scoring.BROADBAND_SCORE


def test_plain_network_falls_back_to_default_tag():
    result = classify("9.9.9.9", payload(country="US", asn="19281", org="Quad9"))
    assert result["tags"] == [scoring.TAG_DEFAULT]
    assert result["ipType"] == scoring.IP_TYPE_COMMERCIAL


def test_unknown_without_asn():
    result = classify("9.9.9.9")
    assert result["ipType"] == scoring.IP_TYPE_UNKNOWN
    assert result["score"] == 0


def test_proxy_and_abuse_stack_and_reach_high_level():
    proxy = classify("1.2.3.4", payload(org="anonymous proxy service"))
    assert proxy["proxyLike"] is True
    assert proxy["score"] == scoring.PROXY_SCORE
    assert proxy["level"] == scoring.LEVEL_MEDIUM

    both = classify("1.2.3.4", payload(org="proxy spam abuse"))
    assert both["score"] == scoring.PROXY_SCORE + scoring.ABUSE_SCORE
    assert both["level"] == scoring.LEVEL_HIGH
    assert both["abuseLike"] is True


def test_dnsbl_listing_adds_score_and_tag():
    result = classify("1.2.3.4", payload(org="Quad9"), dnsbl_listed=True)
    assert result["score"] == scoring.DNSBL_SCORE
    assert result["flags"]["dnsblListed"] is True
    assert scoring.TAG_DNSBL in result["tags"]
    assert result["abuseLike"] is True


def test_score_is_capped():
    result = classify(
        "1.2.3.4",
        payload(org="cloudflare proxy spam abuse blacklist"),
        dnsbl_listed=True,
    )
    assert result["score"] == scoring.MAX_SCORE


def test_extra_text_participates_in_matching():
    plain = classify("5.5.5.5", payload(org="Quad9"))
    hinted = classify("5.5.5.5", payload(org="Quad9"), extra_text="ptr.cloudflare.net")
    assert plain["ipType"] != scoring.IP_TYPE_CDN
    assert hinted["ipType"] == scoring.IP_TYPE_CDN


def test_tags_are_unique():
    result = classify("1.2.3.4", payload(org="cloudflare cdn edgecast"))
    assert len(result["tags"]) == len(set(result["tags"]))


def test_network_text_handles_missing_results():
    assert scoring.network_text(None) == ""
    assert scoring.network_text({"results": [{"data": None}]}).strip() in ("null", '"null"')


def test_has_network_identity():
    assert scoring.has_network_identity(payload(asn="13335", org="Cloudflare")) is True
    assert scoring.has_network_identity({"results": [{"data": {"user-country": {"country_code": "US"}}}]}) is False
    assert scoring.has_network_identity(None) is False
