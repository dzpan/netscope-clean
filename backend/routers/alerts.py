"""Alerts router endpoints."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request

from backend.models import (
    Alert,
    AlertAckRequest,
    AlertRule,
    AlertRuleRequest,
    TestWebhookRequest,
)

router = APIRouter()


def _require_alert_stores(request: Request) -> None:
    if request.app.state.alert_rule_store is None or request.app.state.alert_store is None:
        raise HTTPException(
            status_code=422,
            detail="Alerts require NETSCOPE_DB_PATH to be configured",
        )


@router.post("/alerts/rules", response_model=AlertRule, status_code=201, tags=["Alerts"])
async def create_alert_rule(request: Request, req: AlertRuleRequest) -> AlertRule:
    """Create a new alert rule."""
    _require_alert_stores(request)

    rule = AlertRule(
        rule_id=str(uuid4()),
        name=req.name,
        triggers=req.triggers,
        severity=req.severity,
        webhook_url=req.webhook_url,
        created_at=datetime.now(UTC),
    )
    _alert_rule_store = request.app.state.alert_rule_store
    if _alert_rule_store is None:
        raise HTTPException(status_code=500, detail="Alert rule store not initialized")
    await _alert_rule_store.save(rule)
    return rule


@router.get("/alerts/rules", response_model=list[AlertRule], tags=["Alerts"])
async def list_alert_rules(request: Request) -> list[AlertRule]:
    """List all configured alert rules."""
    _require_alert_stores(request)
    _alert_rule_store = request.app.state.alert_rule_store
    if _alert_rule_store is None:
        raise HTTPException(status_code=500, detail="Alert rule store not initialized")
    return _alert_rule_store.list_all()  # type: ignore[no-any-return]


@router.put("/alerts/rules/{rule_id}", response_model=AlertRule, tags=["Alerts"])
async def update_alert_rule(request: Request, rule_id: str, req: AlertRuleRequest) -> AlertRule:
    """Update an existing alert rule."""
    _require_alert_stores(request)
    _alert_rule_store = request.app.state.alert_rule_store
    if _alert_rule_store is None:
        raise HTTPException(status_code=500, detail="Alert rule store not initialized")
    existing = _alert_rule_store.get(rule_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Alert rule not found")
    updated = existing.model_copy(
        update={
            "name": req.name,
            "triggers": req.triggers,
            "severity": req.severity,
            "webhook_url": req.webhook_url,
        }
    )
    await _alert_rule_store.save(updated)
    return updated  # type: ignore[no-any-return]


@router.delete("/alerts/rules/{rule_id}", status_code=204, tags=["Alerts"])
async def delete_alert_rule(request: Request, rule_id: str) -> None:
    """Delete an alert rule by ID."""
    _require_alert_stores(request)
    _alert_rule_store = request.app.state.alert_rule_store
    if _alert_rule_store is None:
        raise HTTPException(status_code=500, detail="Alert rule store not initialized")
    deleted = await _alert_rule_store.delete(rule_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Alert rule not found")


@router.get("/alerts", response_model=list[Alert], tags=["Alerts"])
async def list_alerts(request: Request, limit: int = 200) -> list[Alert]:
    """List recent fired alerts, most recent first."""
    _require_alert_stores(request)
    limit = max(1, min(limit, 1000))
    _alert_store = request.app.state.alert_store
    if _alert_store is None:
        raise HTTPException(status_code=500, detail="Alert store not initialized")
    return _alert_store.list_all(limit=limit)  # type: ignore[no-any-return]


@router.patch("/alerts/{alert_id}/ack", response_model=Alert, tags=["Alerts"])
async def ack_alert(request: Request, alert_id: str, body: AlertAckRequest) -> Alert:
    """Acknowledge (or un-acknowledge) a fired alert."""
    _require_alert_stores(request)
    _alert_store = request.app.state.alert_store
    if _alert_store is None:
        raise HTTPException(status_code=500, detail="Alert store not initialized")
    updated = await _alert_store.acknowledge(alert_id, body.acknowledged)
    if updated is None:
        raise HTTPException(status_code=404, detail="Alert not found")
    return updated  # type: ignore[no-any-return]


@router.post("/alerts/test-webhook", tags=["Alerts"])
async def test_webhook(req: TestWebhookRequest) -> dict[str, object]:
    """Send a test payload to the given webhook URL."""
    from backend.alerts import validate_webhook_url

    try:
        validate_webhook_url(req.url)
    except ValueError as exc:
        return {"success": False, "error": f"Blocked: {exc}"}

    import httpx

    payload = {
        "alert_id": "test-00000000",
        "rule_id": "test-rule",
        "rule_name": "Test Alert",
        "triggered_at": datetime.now(UTC).isoformat(),
        "severity": "info",
        "trigger": "device_added",
        "detail": "This is a test webhook from NetScope.",
        "current_session_id": "test-session",
        "previous_session_id": "test-session-prev",
        "test": True,
    }
    headers: dict[str, str] = {}
    if req.secret:
        import hashlib
        import hmac

        sig = hmac.new(
            req.secret.encode(), msg=str(payload).encode(), digestmod=hashlib.sha256
        ).hexdigest()
        headers["X-NetScope-Signature"] = sig
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(req.url, json=payload, headers=headers)
            return {"success": True, "status_code": resp.status_code, "body": resp.text[:500]}
    except Exception as exc:
        return {"success": False, "error": str(exc)}
