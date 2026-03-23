"""Alert engine — evaluates topology diffs against configured rules and delivers webhooks.

Each AlertRule can fire on one or more AlertTrigger types. When a diff is
computed (via manual rediscover or the scheduled background pass), call
``evaluate_alerts`` to produce Alert objects for any matching rules, then
``deliver_webhook`` to POST the JSON payload to the configured URL.
"""

from __future__ import annotations

import ipaddress
import logging
import socket
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Protocol
from urllib.parse import urlparse
from uuid import uuid4

from backend.models import Alert, AlertRule, AlertSeverity, AlertTrigger, TopologyDiff

logger = logging.getLogger(__name__)


def validate_webhook_url(url: str) -> None:
    """Raise ValueError if *url* targets a private/internal network."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"Blocked webhook: unsupported scheme '{parsed.scheme}'")
    hostname = parsed.hostname
    if not hostname:
        raise ValueError("Blocked webhook: no hostname in URL")

    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        addr_infos = socket.getaddrinfo(hostname, port, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise ValueError(f"Blocked webhook: DNS resolution failed for '{hostname}'") from exc

    for family, _type, _proto, _canonname, sockaddr in addr_infos:
        ip = ipaddress.ip_address(sockaddr[0])
        if ip.is_private or ip.is_reserved:
            raise ValueError(f"Blocked webhook: resolved to blocked address {ip}")


# ---------------------------------------------------------------------------
# Matching engine
# ---------------------------------------------------------------------------


def _device_status_changed(diff: TopologyDiff) -> bool:
    for dev in diff.devices_changed:
        for chg in dev.changes:
            if chg.field == "status":
                return True
    return False


_TRIGGER_CHECKS: dict[AlertTrigger, Callable[[TopologyDiff], bool]] = {
    AlertTrigger.DEVICE_ADDED: lambda d: bool(d.devices_added),
    AlertTrigger.DEVICE_REMOVED: lambda d: bool(d.devices_removed),
    AlertTrigger.LINK_ADDED: lambda d: bool(d.links_added),
    AlertTrigger.LINK_REMOVED: lambda d: bool(d.links_removed),
    AlertTrigger.DEVICE_STATUS_CHANGE: _device_status_changed,
    AlertTrigger.STP_CHANGE: lambda _: False,  # reserved — not yet detected
}


def _describe_trigger(trigger: AlertTrigger, diff: TopologyDiff) -> str:
    """Return a human-readable description for a fired trigger."""
    if trigger == AlertTrigger.DEVICE_ADDED:
        return f"{len(diff.devices_added)} device(s) added: {', '.join(diff.devices_added)}"
    if trigger == AlertTrigger.DEVICE_REMOVED:
        return f"{len(diff.devices_removed)} device(s) removed: {', '.join(diff.devices_removed)}"
    if trigger == AlertTrigger.LINK_ADDED:
        desc = ", ".join(f"{lk.source}:{lk.source_intf}↔{lk.target}" for lk in diff.links_added[:5])
        suffix = f" (+{len(diff.links_added) - 5} more)" if len(diff.links_added) > 5 else ""
        return f"{len(diff.links_added)} link(s) added: {desc}{suffix}"
    if trigger == AlertTrigger.LINK_REMOVED:
        desc = ", ".join(
            f"{lk.source}:{lk.source_intf}↔{lk.target}" for lk in diff.links_removed[:5]
        )
        suffix = f" (+{len(diff.links_removed) - 5} more)" if len(diff.links_removed) > 5 else ""
        return f"{len(diff.links_removed)} link(s) removed: {desc}{suffix}"
    if trigger == AlertTrigger.DEVICE_STATUS_CHANGE:
        changed = [
            f"{d.hostname or d.device_id}({c.before}→{c.after})"
            for d in diff.devices_changed
            for c in d.changes
            if c.field == "status"
        ]
        return f"Device status changed: {', '.join(changed)}"
    return str(trigger)


def evaluate_alerts(diff: TopologyDiff, rules: list[AlertRule]) -> list[Alert]:
    """Evaluate *diff* against all *rules* and return fired alerts.

    One Alert is created per (rule, matching trigger). If a rule has multiple
    matching triggers, it fires once per trigger so each gets its own detail.
    """
    if diff.total_changes == 0:
        return []

    alerts: list[Alert] = []
    now = datetime.now(UTC)

    for rule in rules:
        for trigger in rule.triggers:
            check = _TRIGGER_CHECKS.get(trigger)
            if check is None:
                continue
            if not check(diff):
                continue
            alerts.append(
                Alert(
                    alert_id=str(uuid4()),
                    rule_id=rule.rule_id,
                    rule_name=rule.name,
                    triggered_at=now,
                    severity=rule.severity,
                    trigger=trigger,
                    detail=_describe_trigger(trigger, diff),
                    current_session_id=diff.current_session_id,
                    previous_session_id=diff.previous_session_id,
                )
            )

    return alerts


# ---------------------------------------------------------------------------
# Webhook delivery
# ---------------------------------------------------------------------------


class HttpClientProtocol(Protocol):
    """Minimal interface for the HTTP client used in webhook delivery.

    Using a Protocol makes it easy to inject a mock in tests without depending
    on httpx's concrete classes.
    """

    async def post(self, url: str, *, json: object) -> None: ...


async def deliver_webhook(alert: Alert, url: str, client: HttpClientProtocol) -> None:
    """POST *alert* as JSON to *url* using *client*.

    Logs a warning on failure but never raises — webhook delivery is best-effort.
    """
    try:
        validate_webhook_url(url)
    except ValueError:
        logger.warning("Webhook blocked (SSRF): url=%s", url)
        return
    payload = {
        "alert_id": alert.alert_id,
        "rule_id": alert.rule_id,
        "rule_name": alert.rule_name,
        "triggered_at": alert.triggered_at.isoformat(),
        "severity": alert.severity,
        "trigger": alert.trigger,
        "detail": alert.detail,
        "current_session_id": alert.current_session_id,
        "previous_session_id": alert.previous_session_id,
    }
    try:
        await client.post(url, json=payload)
        logger.info("Webhook delivered: alert=%s url=%s", alert.alert_id, url)
    except Exception:
        logger.warning(
            "Webhook delivery failed: alert=%s url=%s", alert.alert_id, url, exc_info=True
        )


async def fire_alerts(
    diff: TopologyDiff,
    rules: list[AlertRule],
    http_client: HttpClientProtocol,
) -> list[Alert]:
    """Evaluate diff, deliver webhooks, return fired alerts (caller must persist them)."""
    alerts = evaluate_alerts(diff, rules)
    for alert in alerts:
        rule = next((r for r in rules if r.rule_id == alert.rule_id), None)
        if rule and rule.webhook_url:
            await deliver_webhook(alert, rule.webhook_url, http_client)
    return alerts


# ---------------------------------------------------------------------------
# Default HTTP client (httpx)
# ---------------------------------------------------------------------------


class HttpxAlertClient:
    """Production HTTP client using httpx with a short timeout."""

    def __init__(self) -> None:
        import httpx

        self._client = httpx.AsyncClient(timeout=10.0)

    async def post(self, url: str, *, json: object) -> None:
        import httpx

        try:
            resp = await self._client.post(url, json=json)
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(f"Webhook HTTP {exc.response.status_code}: {url}") from exc

    async def aclose(self) -> None:
        await self._client.aclose()


def make_severity_for_diff(diff: TopologyDiff) -> AlertSeverity:
    """Heuristic default severity: critical for removals, warning otherwise."""
    if diff.devices_removed or diff.links_removed:
        return AlertSeverity.CRITICAL
    return AlertSeverity.WARNING
