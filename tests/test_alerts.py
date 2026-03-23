"""Tests for alert rule matching and webhook delivery (mocked HTTP)."""

from __future__ import annotations

import asyncio
import socket
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from backend.alerts import deliver_webhook, evaluate_alerts, fire_alerts, validate_webhook_url
from backend.models import (
    Alert,
    AlertRule,
    AlertSeverity,
    AlertTrigger,
    DeviceChange,
    DeviceDiff,
    LinkKey,
    TopologyDiff,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_diff(
    devices_added: list[str] | None = None,
    devices_removed: list[str] | None = None,
    links_added: list[LinkKey] | None = None,
    links_removed: list[LinkKey] | None = None,
    devices_changed: list[DeviceDiff] | None = None,
) -> TopologyDiff:
    all_changes = list(devices_added or []) + list(devices_removed or [])
    if links_added:
        all_changes += links_added
    if links_removed:
        all_changes += links_removed
    if devices_changed:
        all_changes += devices_changed
    return TopologyDiff(
        diff_id=str(uuid4()),
        current_session_id="cur",
        previous_session_id="prev",
        computed_at=datetime.now(UTC),
        devices_added=devices_added or [],
        devices_removed=devices_removed or [],
        links_added=links_added or [],
        links_removed=links_removed or [],
        devices_changed=devices_changed or [],
        total_changes=len(all_changes),
    )


def _make_rule(
    triggers: list[AlertTrigger],
    webhook_url: str | None = None,
    severity: AlertSeverity = AlertSeverity.WARNING,
) -> AlertRule:
    return AlertRule(
        rule_id=str(uuid4()),
        name="Test Rule",
        triggers=triggers,
        severity=severity,
        webhook_url=webhook_url,
        created_at=datetime.now(UTC),
    )


def _link_key(src: str = "SW-A", tgt: str = "SW-B") -> LinkKey:
    return LinkKey(source=src, target=tgt, source_intf="Gi0/1", target_intf="Gi0/1")


# ---------------------------------------------------------------------------
# evaluate_alerts — matching engine
# ---------------------------------------------------------------------------


class TestEvaluateAlerts:
    def test_no_changes_fires_no_alerts(self) -> None:
        diff = _make_diff()
        diff = diff.model_copy(update={"total_changes": 0})
        rule = _make_rule([AlertTrigger.DEVICE_ADDED])
        assert evaluate_alerts(diff, rules=[]) == []
        assert evaluate_alerts(diff, rules=[rule]) == []

    def test_device_added_fires(self) -> None:
        diff = _make_diff(devices_added=["SW-NEW"])
        rule = _make_rule([AlertTrigger.DEVICE_ADDED])
        alerts = evaluate_alerts(diff, rules=[rule])
        assert len(alerts) == 1
        assert alerts[0].trigger == AlertTrigger.DEVICE_ADDED
        assert "SW-NEW" in alerts[0].detail

    def test_device_removed_fires(self) -> None:
        diff = _make_diff(devices_removed=["SW-GONE"])
        rule = _make_rule([AlertTrigger.DEVICE_REMOVED])
        alerts = evaluate_alerts(diff, rules=[rule])
        assert len(alerts) == 1
        assert alerts[0].trigger == AlertTrigger.DEVICE_REMOVED

    def test_link_added_fires(self) -> None:
        diff = _make_diff(links_added=[_link_key()])
        rule = _make_rule([AlertTrigger.LINK_ADDED])
        alerts = evaluate_alerts(diff, rules=[rule])
        assert len(alerts) == 1
        assert alerts[0].trigger == AlertTrigger.LINK_ADDED

    def test_link_removed_fires(self) -> None:
        diff = _make_diff(links_removed=[_link_key()])
        rule = _make_rule([AlertTrigger.LINK_REMOVED])
        alerts = evaluate_alerts(diff, rules=[rule])
        assert len(alerts) == 1

    def test_device_status_change_fires(self) -> None:
        changed = DeviceDiff(
            device_id="SW-1",
            hostname="SW-1",
            changes=[DeviceChange(field="status", before="ok", after="timeout")],
        )
        diff = _make_diff(devices_changed=[changed])
        rule = _make_rule([AlertTrigger.DEVICE_STATUS_CHANGE])
        alerts = evaluate_alerts(diff, rules=[rule])
        assert len(alerts) == 1
        assert "SW-1" in alerts[0].detail

    def test_non_status_change_does_not_fire_status_trigger(self) -> None:
        changed = DeviceDiff(
            device_id="SW-1",
            hostname="SW-1",
            changes=[DeviceChange(field="os_version", before="17.3", after="17.6")],
        )
        diff = _make_diff(devices_changed=[changed])
        rule = _make_rule([AlertTrigger.DEVICE_STATUS_CHANGE])
        alerts = evaluate_alerts(diff, rules=[rule])
        assert alerts == []

    def test_multiple_triggers_one_rule_fires_per_trigger(self) -> None:
        """A rule with two matching triggers should fire twice."""
        diff = _make_diff(devices_added=["SW-A"], devices_removed=["SW-B"])
        rule = _make_rule([AlertTrigger.DEVICE_ADDED, AlertTrigger.DEVICE_REMOVED])
        alerts = evaluate_alerts(diff, rules=[rule])
        assert len(alerts) == 2
        triggers = {a.trigger for a in alerts}
        assert triggers == {AlertTrigger.DEVICE_ADDED, AlertTrigger.DEVICE_REMOVED}

    def test_rule_name_propagated(self) -> None:
        diff = _make_diff(devices_added=["SW-X"])
        rule = _make_rule([AlertTrigger.DEVICE_ADDED])
        rule = rule.model_copy(update={"name": "My custom rule"})
        alerts = evaluate_alerts(diff, rules=[rule])
        assert alerts[0].rule_name == "My custom rule"

    def test_non_matching_trigger_not_fired(self) -> None:
        diff = _make_diff(devices_added=["SW-NEW"])
        rule = _make_rule([AlertTrigger.DEVICE_REMOVED])  # wrong trigger
        alerts = evaluate_alerts(diff, rules=[rule])
        assert alerts == []

    def test_empty_rules_list(self) -> None:
        diff = _make_diff(devices_added=["SW-NEW"])
        assert evaluate_alerts(diff, rules=[]) == []


# ---------------------------------------------------------------------------
# deliver_webhook
# ---------------------------------------------------------------------------


class TestDeliverWebhook:
    @pytest.mark.asyncio
    async def test_calls_client_post_with_correct_payload(self) -> None:
        client = MagicMock()
        client.post = AsyncMock()
        alert = Alert(
            alert_id="a1",
            rule_id="r1",
            rule_name="Test",
            triggered_at=datetime.now(UTC),
            severity=AlertSeverity.WARNING,
            trigger=AlertTrigger.DEVICE_ADDED,
            detail="SW-NEW added",
            current_session_id="cur",
            previous_session_id="prev",
        )
        await deliver_webhook(alert, "http://example.com/hook", client)
        client.post.assert_called_once()
        _, kwargs = client.post.call_args
        payload = kwargs["json"]
        assert payload["alert_id"] == "a1"
        assert payload["trigger"] == "device_added"
        assert payload["detail"] == "SW-NEW added"

    @pytest.mark.asyncio
    async def test_webhook_failure_does_not_raise(self) -> None:
        client = MagicMock()
        client.post = AsyncMock(side_effect=RuntimeError("connection refused"))
        alert = Alert(
            alert_id="a2",
            rule_id="r1",
            rule_name="Test",
            triggered_at=datetime.now(UTC),
            severity=AlertSeverity.WARNING,
            trigger=AlertTrigger.DEVICE_REMOVED,
            detail="SW-GONE removed",
            current_session_id="cur",
            previous_session_id="prev",
        )
        # Must not raise
        await deliver_webhook(alert, "http://bad.example/hook", client)


# ---------------------------------------------------------------------------
# fire_alerts (integration: evaluate + deliver)
# ---------------------------------------------------------------------------


class TestFireAlerts:
    @pytest.mark.asyncio
    async def test_fires_and_delivers_webhook(self) -> None:
        client = MagicMock()
        client.post = AsyncMock()

        diff = _make_diff(devices_added=["SW-NEW"])
        rule = _make_rule([AlertTrigger.DEVICE_ADDED], webhook_url="http://example.com/wh")

        alerts = await fire_alerts(diff, [rule], client)
        assert len(alerts) == 1
        client.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_webhook_url_skips_delivery(self) -> None:
        client = MagicMock()
        client.post = AsyncMock()

        diff = _make_diff(devices_added=["SW-NEW"])
        rule = _make_rule([AlertTrigger.DEVICE_ADDED], webhook_url=None)

        alerts = await fire_alerts(diff, [rule], client)
        assert len(alerts) == 1
        client.post.assert_not_called()


# ---------------------------------------------------------------------------
# SQLite alert stores
# ---------------------------------------------------------------------------


class TestSQLiteAlertStores:
    def setup_method(self) -> None:
        self._tmpdir = tempfile.mkdtemp()
        self._db_path = Path(self._tmpdir) / "test.db"
        from backend.store_sqlite import SQLiteAlertRuleStore, SQLiteAlertStore

        self.rule_store = SQLiteAlertRuleStore(self._db_path)
        self.alert_store = SQLiteAlertStore(self._db_path)

    def _make_alert(self, alert_id: str = "a1") -> Alert:
        return Alert(
            alert_id=alert_id,
            rule_id="r1",
            rule_name="Test",
            triggered_at=datetime.now(UTC),
            severity=AlertSeverity.WARNING,
            trigger=AlertTrigger.DEVICE_ADDED,
            detail="detail",
            current_session_id="cur",
            previous_session_id="prev",
        )

    def test_save_and_get_rule(self) -> None:
        rule = _make_rule([AlertTrigger.DEVICE_ADDED])
        asyncio.run(self.rule_store.save(rule))
        got = self.rule_store.get(rule.rule_id)
        assert got is not None
        assert got.rule_id == rule.rule_id

    def test_delete_rule(self) -> None:
        rule = _make_rule([AlertTrigger.DEVICE_REMOVED])
        asyncio.run(self.rule_store.save(rule))
        deleted = asyncio.run(self.rule_store.delete(rule.rule_id))
        assert deleted is True
        assert self.rule_store.get(rule.rule_id) is None

    def test_delete_missing_rule(self) -> None:
        assert asyncio.run(self.rule_store.delete("no-such-id")) is False

    def test_save_and_get_alert(self) -> None:
        alert = self._make_alert()
        asyncio.run(self.alert_store.save(alert))
        got = self.alert_store.get("a1")
        assert got is not None
        assert got.alert_id == "a1"

    def test_acknowledge_alert(self) -> None:
        alert = self._make_alert("ack-test")
        asyncio.run(self.alert_store.save(alert))
        updated = asyncio.run(self.alert_store.acknowledge("ack-test", acked=True))
        assert updated is not None
        assert updated.acknowledged_at is not None

    def test_unacknowledge_alert(self) -> None:
        alert = self._make_alert("unack-test")
        asyncio.run(self.alert_store.save(alert))
        asyncio.run(self.alert_store.acknowledge("unack-test", acked=True))
        updated = asyncio.run(self.alert_store.acknowledge("unack-test", acked=False))
        assert updated is not None
        assert updated.acknowledged_at is None

    def test_list_all_alerts(self) -> None:
        for i in range(3):
            asyncio.run(self.alert_store.save(self._make_alert(f"a{i}")))
        assert len(self.alert_store.list_all()) == 3


# ---------------------------------------------------------------------------
# SSRF validation tests
# ---------------------------------------------------------------------------


def test_validate_webhook_url_blocks_private_ip() -> None:
    with pytest.raises(ValueError, match="blocked"):
        validate_webhook_url("http://192.168.1.1:8080/hook")


def test_validate_webhook_url_blocks_loopback() -> None:
    with pytest.raises(ValueError, match="blocked"):
        validate_webhook_url("http://127.0.0.1/hook")


def test_validate_webhook_url_blocks_link_local() -> None:
    with pytest.raises(ValueError, match="blocked"):
        validate_webhook_url("http://169.254.169.254/latest/meta-data/")


def test_validate_webhook_url_blocks_non_http_scheme() -> None:
    with pytest.raises(ValueError, match="scheme"):
        validate_webhook_url("ftp://example.com/hook")


def test_validate_webhook_url_blocks_no_hostname() -> None:
    with pytest.raises(ValueError, match="hostname"):
        validate_webhook_url("http:///path")


@patch("socket.getaddrinfo", return_value=[(socket.AF_INET, 0, 0, "", ("93.184.216.34", 80))])
def test_validate_webhook_url_allows_public_ip(_mock: object) -> None:
    validate_webhook_url("https://example.com/webhook")


@patch("socket.getaddrinfo", return_value=[(socket.AF_INET, 0, 0, "", ("10.0.0.1", 80))])
def test_validate_webhook_url_blocks_dns_resolving_to_private(_mock: object) -> None:
    with pytest.raises(ValueError, match="blocked"):
        validate_webhook_url("https://evil.example.com/webhook")
