"""Tests for SNMP fallback collector.

These tests verify the module structure and helper functions without requiring
a live SNMP agent or pysnmp installation.
"""

from __future__ import annotations

from backend.vendors.snmp import (
    OID_CDP_CACHE_DEVICE_ID,
    OID_IF_DESCR,
    OID_LLDP_REM_SYS_NAME,
    OID_SYS_DESCR,
    OID_SYS_NAME,
    _extract_platform,
)


class TestExtractPlatform:
    def test_cisco_sysdescr(self) -> None:
        descr = "Cisco IOS Software, C3750E Software (C3750E-UNIVERSALK9-M), Version 15.2(4)E10"
        result = _extract_platform(descr)
        assert result is not None
        assert "Cisco" in result

    def test_arista_sysdescr(self) -> None:
        descr = "Arista Networks EOS version 4.28.3M running on an Arista Networks vEOS-lab"
        result = _extract_platform(descr)
        assert result is not None
        assert "Arista" in result

    def test_juniper_sysdescr(self) -> None:
        descr = "Juniper Networks, Inc. ex4200-48t Ethernet Switch"
        result = _extract_platform(descr)
        assert result is not None
        assert "Juniper" in result

    def test_empty(self) -> None:
        assert _extract_platform("") is None

    def test_multiline(self) -> None:
        descr = "Cisco IOS Software\nSome other line\nThird line"
        result = _extract_platform(descr)
        assert result == "Cisco IOS Software"

    def test_truncation(self) -> None:
        descr = "A" * 200
        result = _extract_platform(descr)
        assert result is not None
        assert len(result) == 100


class TestOidConstants:
    """Verify OID constants are well-formed."""

    def test_oid_format(self) -> None:
        for oid in [
            OID_SYS_DESCR,
            OID_SYS_NAME,
            OID_IF_DESCR,
            OID_LLDP_REM_SYS_NAME,
            OID_CDP_CACHE_DEVICE_ID,
        ]:
            assert oid.startswith("1.")
            parts = oid.split(".")
            assert all(p.isdigit() for p in parts), f"Invalid OID: {oid}"


class TestSnmpCollectorImport:
    """Verify SnmpCollector can be imported even without pysnmp."""

    def test_import(self) -> None:
        from backend.vendors.snmp import SnmpCollector

        collector = SnmpCollector(host="10.0.0.1", community="public")
        assert collector.host == "10.0.0.1"
        assert collector.community == "public"
        assert collector.port == 161
