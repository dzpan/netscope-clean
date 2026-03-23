"""Integration tests for Advanced Mode API endpoints (/advanced/*).

Tests all endpoints with a mock Scrapli backend and validates the full
flow: status check → VLAN change → audit list → audit detail → export → undo.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from backend.audit_store import AuditStore
from backend.models import AdvancedStatus, AuditRecord, PortChange

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_record(
    audit_id: str = "audit-001",
    device_id: str = "SW-01",
    status: AdvancedStatus = AdvancedStatus.SUCCESS,
    operation: str = "vlan_change",
    undo_of: str | None = None,
) -> AuditRecord:
    return AuditRecord(
        id=audit_id,
        timestamp=datetime.now(UTC),
        device_id=device_id,
        device_ip="10.0.0.1",
        platform="iosxe",
        operation=operation,
        status=status,
        changes=[
            PortChange(
                interface="GigabitEthernet1/0/1",
                field="access_vlan",
                old_value="10",
                new_value="20",
                verified=True,
            )
        ],
        commands_sent=["interface GigabitEthernet1/0/1", "switchport access vlan 20"],
        pre_state={"GigabitEthernet1/0/1": "switchport access vlan 10"},
        post_state={"GigabitEthernet1/0/1": "switchport access vlan 20"},
        rollback_commands=["interface GigabitEthernet1/0/1", "switchport access vlan 10"],
        undo_of=undo_of,
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def _enable_advanced(monkeypatch: pytest.MonkeyPatch) -> AuditStore:
    """Inject a fresh in-memory audit store for test isolation."""
    import backend.main as main_mod

    store = AuditStore()
    monkeypatch.setattr(main_mod, "_audit_store", store)
    # Also patch app.state so router modules see the test store
    main_mod.app.state.audit_store = store
    return store


@pytest.fixture
async def client() -> Any:
    from backend.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test/api/v1") as c:
        yield c


# ---------------------------------------------------------------------------
# GET /advanced/status
# ---------------------------------------------------------------------------


class TestAdvancedStatus:
    async def test_status_always_allowed(self, client: AsyncClient) -> None:
        resp = await client.get("/advanced/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["allowed"] is True
        assert "password_required" in data
        assert "max_ports_per_change" in data
        assert "audit_retention_days" in data
        assert "require_write_mem" in data

    async def test_status_password_required_when_set(
        self, client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import backend.main as main_mod

        monkeypatch.setattr(main_mod.settings, "advanced_password", "secret123")
        resp = await client.get("/advanced/status")
        data = resp.json()
        assert data["password_required"] is True

    async def test_status_password_not_required_when_empty(
        self, client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import backend.main as main_mod

        monkeypatch.setattr(main_mod.settings, "advanced_password", "")
        resp = await client.get("/advanced/status")
        data = resp.json()
        assert data["password_required"] is False


# ---------------------------------------------------------------------------
# POST /advanced/authenticate
# ---------------------------------------------------------------------------


class TestAdvancedAuthenticate:
    async def test_authenticate_no_password_configured(
        self, client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import backend.main as main_mod

        monkeypatch.setattr(main_mod.settings, "advanced_password", "")
        resp = await client.post("/advanced/authenticate", json={"password": ""})
        assert resp.status_code == 200
        assert resp.json()["authenticated"] is True

    async def test_authenticate_correct_password(
        self, client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import backend.main as main_mod

        monkeypatch.setattr(main_mod.settings, "advanced_password", "secret123")
        resp = await client.post("/advanced/authenticate", json={"password": "secret123"})
        assert resp.status_code == 200
        assert resp.json()["authenticated"] is True

    async def test_authenticate_wrong_password(
        self, client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import backend.main as main_mod

        monkeypatch.setattr(main_mod.settings, "advanced_password", "secret123")
        resp = await client.post("/advanced/authenticate", json={"password": "wrong"})
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# POST /advanced/vlan-change
# ---------------------------------------------------------------------------


class TestVlanChange:
    @patch("backend.advanced.execute_vlan_change", new_callable=AsyncMock)
    async def test_vlan_change_success(
        self,
        mock_exec: AsyncMock,
        client: AsyncClient,
        _enable_advanced: AuditStore,
    ) -> None:
        expected = _make_record()
        mock_exec.return_value = expected

        resp = await client.post(
            "/advanced/vlan-change",
            json={
                "device_id": "SW-01",
                "device_ip": "10.0.0.1",
                "interfaces": ["GigabitEthernet1/0/1"],
                "target_vlan": 20,
                "username": "admin",
                "password": "pass",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["id"] == "audit-001"
        assert data["status"] == "success"
        assert data["operation"] == "vlan_change"
        assert len(data["changes"]) == 1
        assert data["changes"][0]["interface"] == "GigabitEthernet1/0/1"

        # Verify the record was stored in the audit store
        stored = _enable_advanced.get("audit-001")
        assert stored is not None

    @patch("backend.advanced.execute_vlan_change", new_callable=AsyncMock)
    async def test_vlan_change_failure(
        self,
        mock_exec: AsyncMock,
        client: AsyncClient,
        _enable_advanced: AuditStore,
    ) -> None:
        failed = _make_record(status=AdvancedStatus.FAILED)
        failed = failed.model_copy(update={"error": "VLAN 99 does not exist on device"})
        mock_exec.return_value = failed

        resp = await client.post(
            "/advanced/vlan-change",
            json={
                "device_id": "SW-01",
                "device_ip": "10.0.0.1",
                "interfaces": ["GigabitEthernet1/0/1"],
                "target_vlan": 99,
                "username": "admin",
                "password": "pass",
            },
        )
        assert resp.status_code == 201  # still 201, failure is in the record
        data = resp.json()
        assert data["status"] == "failed"
        assert "VLAN 99" in data["error"]

    async def test_vlan_change_validation_bad_vlan(
        self,
        client: AsyncClient,
        _enable_advanced: AuditStore,
    ) -> None:
        resp = await client.post(
            "/advanced/vlan-change",
            json={
                "device_id": "SW-01",
                "device_ip": "10.0.0.1",
                "interfaces": ["GigabitEthernet1/0/1"],
                "target_vlan": 9999,  # above 4094
                "username": "admin",
                "password": "pass",
            },
        )
        assert resp.status_code == 422  # Pydantic validation

    async def test_vlan_change_validation_no_interfaces(
        self,
        client: AsyncClient,
        _enable_advanced: AuditStore,
    ) -> None:
        resp = await client.post(
            "/advanced/vlan-change",
            json={
                "device_id": "SW-01",
                "device_ip": "10.0.0.1",
                "interfaces": [],  # empty
                "target_vlan": 20,
                "username": "admin",
                "password": "pass",
            },
        )
        assert resp.status_code == 422  # Pydantic min_length=1


# ---------------------------------------------------------------------------
# GET /advanced/audit
# ---------------------------------------------------------------------------


class TestListAudit:
    async def test_list_audit_empty(
        self, client: AsyncClient, _enable_advanced: AuditStore
    ) -> None:
        resp = await client.get("/advanced/audit")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_list_audit_with_records(
        self, client: AsyncClient, _enable_advanced: AuditStore
    ) -> None:
        store = _enable_advanced
        await store.create(_make_record("r1"))
        await store.create(_make_record("r2"))

        resp = await client.get("/advanced/audit")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2

    async def test_list_audit_filter_device(
        self, client: AsyncClient, _enable_advanced: AuditStore
    ) -> None:
        store = _enable_advanced
        await store.create(_make_record("r1", device_id="SW-01"))
        await store.create(_make_record("r2", device_id="SW-02"))

        resp = await client.get("/advanced/audit", params={"device_id": "SW-01"})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["device_id"] == "SW-01"

    async def test_list_audit_pagination(
        self, client: AsyncClient, _enable_advanced: AuditStore
    ) -> None:
        store = _enable_advanced
        for i in range(5):
            await store.create(_make_record(f"r{i}"))

        resp = await client.get("/advanced/audit", params={"limit": 2, "offset": 0})
        assert resp.status_code == 200
        assert len(resp.json()) == 2

        resp2 = await client.get("/advanced/audit", params={"limit": 2, "offset": 2})
        assert resp2.status_code == 200
        assert len(resp2.json()) == 2


# ---------------------------------------------------------------------------
# GET /advanced/audit/{audit_id}
# ---------------------------------------------------------------------------


class TestGetAudit:
    async def test_get_audit_not_found(
        self, client: AsyncClient, _enable_advanced: AuditStore
    ) -> None:
        resp = await client.get("/advanced/audit/nonexistent")
        assert resp.status_code == 404

    async def test_get_audit_found(self, client: AsyncClient, _enable_advanced: AuditStore) -> None:
        store = _enable_advanced
        await store.create(_make_record("audit-xyz"))

        resp = await client.get("/advanced/audit/audit-xyz")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == "audit-xyz"
        assert data["device_id"] == "SW-01"
        assert data["changes"][0]["interface"] == "GigabitEthernet1/0/1"


# ---------------------------------------------------------------------------
# GET /advanced/audit/export
# ---------------------------------------------------------------------------


class TestExportAudit:
    async def test_export_json(self, client: AsyncClient, _enable_advanced: AuditStore) -> None:
        store = _enable_advanced
        await store.create(_make_record("r1"))

        resp = await client.get("/advanced/audit/export", params={"format": "json"})
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/json"
        assert "r1" in resp.text

    async def test_export_csv(self, client: AsyncClient, _enable_advanced: AuditStore) -> None:
        store = _enable_advanced
        await store.create(_make_record("r1"))

        resp = await client.get("/advanced/audit/export", params={"format": "csv"})
        assert resp.status_code == 200
        assert "text/csv" in resp.headers["content-type"]
        assert "r1" in resp.text

    async def test_export_default_is_json(
        self, client: AsyncClient, _enable_advanced: AuditStore
    ) -> None:
        store = _enable_advanced
        await store.create(_make_record("r1"))

        resp = await client.get("/advanced/audit/export")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/json"


# ---------------------------------------------------------------------------
# POST /advanced/audit/{audit_id}/undo
# ---------------------------------------------------------------------------


class TestUndoAudit:
    async def test_undo_not_found(self, client: AsyncClient, _enable_advanced: AuditStore) -> None:
        resp = await client.post(
            "/advanced/audit/nonexistent/undo",
            json={"username": "admin", "password": "pass"},
        )
        assert resp.status_code == 404

    @patch("backend.advanced.undo_change", new_callable=AsyncMock)
    async def test_undo_success(
        self,
        mock_undo: AsyncMock,
        client: AsyncClient,
        _enable_advanced: AuditStore,
    ) -> None:
        store = _enable_advanced
        original = _make_record("orig-001")
        await store.create(original)

        undo_record = _make_record(
            "undo-001",
            status=AdvancedStatus.SUCCESS,
            operation="undo",
            undo_of="orig-001",
        )
        mock_undo.return_value = undo_record

        resp = await client.post(
            "/advanced/audit/orig-001/undo",
            json={"username": "admin", "password": "pass"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["operation"] == "undo"
        assert data["undo_of"] == "orig-001"
        assert data["status"] == "success"

        # Verify original was marked as rolled back
        updated_original = store.get("orig-001")
        assert updated_original is not None
        assert updated_original.undone_by == "undo-001"


# ---------------------------------------------------------------------------
# Full integration flow (end-to-end)
# ---------------------------------------------------------------------------


class TestFullFlow:
    """End-to-end flow: status → change → list → detail → export → undo."""

    @patch("backend.advanced.undo_change", new_callable=AsyncMock)
    @patch("backend.advanced.execute_vlan_change", new_callable=AsyncMock)
    async def test_full_advanced_mode_flow(
        self,
        mock_exec: AsyncMock,
        mock_undo: AsyncMock,
        client: AsyncClient,
        _enable_advanced: AuditStore,
    ) -> None:
        # 1. Check status — Advanced Mode is always available
        resp = await client.get("/advanced/status")
        assert resp.status_code == 200
        assert resp.json()["allowed"] is True

        # 2. Execute VLAN change
        change_record = _make_record("flow-001")
        mock_exec.return_value = change_record

        resp = await client.post(
            "/advanced/vlan-change",
            json={
                "device_id": "SW-01",
                "device_ip": "10.0.0.1",
                "interfaces": ["GigabitEthernet1/0/1"],
                "target_vlan": 20,
                "username": "admin",
                "password": "pass",
            },
        )
        assert resp.status_code == 201
        change_data = resp.json()
        change_id = change_data["id"]
        assert change_id == "flow-001"

        # 3. List audit records — should contain the change
        resp = await client.get("/advanced/audit")
        assert resp.status_code == 200
        records = resp.json()
        assert len(records) == 1
        assert records[0]["id"] == change_id

        # 4. Get specific audit record
        resp = await client.get(f"/advanced/audit/{change_id}")
        assert resp.status_code == 200
        detail = resp.json()
        assert detail["id"] == change_id
        assert detail["pre_state"]["GigabitEthernet1/0/1"] == "switchport access vlan 10"

        # 5. Export as JSON
        resp = await client.get("/advanced/audit/export", params={"format": "json"})
        assert resp.status_code == 200
        assert change_id in resp.text

        # 6. Export as CSV
        resp = await client.get("/advanced/audit/export", params={"format": "csv"})
        assert resp.status_code == 200
        assert change_id in resp.text

        # 7. Undo the change
        undo_record = _make_record(
            "undo-flow-001",
            status=AdvancedStatus.SUCCESS,
            operation="undo",
            undo_of=change_id,
        )
        mock_undo.return_value = undo_record

        resp = await client.post(
            f"/advanced/audit/{change_id}/undo",
            json={"username": "admin", "password": "pass"},
        )
        assert resp.status_code == 201
        undo_data = resp.json()
        assert undo_data["operation"] == "undo"
        assert undo_data["undo_of"] == change_id

        # 8. Verify original record shows as undone
        resp = await client.get(f"/advanced/audit/{change_id}")
        assert resp.status_code == 200
        updated = resp.json()
        assert updated["undone_by"] == "undo-flow-001"

        # 9. Audit log now has both records
        resp = await client.get("/advanced/audit")
        assert resp.status_code == 200
        assert len(resp.json()) == 2


# ---------------------------------------------------------------------------
# Frontend-backend contract validation
# ---------------------------------------------------------------------------


class TestFrontendContract:
    """Verify that the API endpoints match what the frontend api.js expects."""

    async def test_status_response_shape(
        self, client: AsyncClient, _enable_advanced: AuditStore
    ) -> None:
        """Frontend getAdvancedStatus() expects: allowed, password_required,
        require_write_mem, max_ports_per_change, audit_retention_days."""
        resp = await client.get("/advanced/status")
        data = resp.json()
        required_keys = {
            "allowed",
            "password_required",
            "require_write_mem",
            "max_ports_per_change",
            "audit_retention_days",
        }
        assert required_keys.issubset(data.keys()), f"Missing: {required_keys - data.keys()}"

    async def test_vlan_change_accepts_frontend_payload(
        self, client: AsyncClient, _enable_advanced: AuditStore
    ) -> None:
        """Frontend executeVlanChange() sends: device_id, device_ip, interfaces,
        target_vlan, description, write_memory + credentials."""
        # Test that validation passes (even though execute will fail without Scrapli)
        payload = {
            "device_id": "SW-01",
            "device_ip": "10.0.0.1",
            "platform": "iosxe",
            "interfaces": ["GigabitEthernet1/0/1"],
            "target_vlan": 20,
            "description": "User workstation",
            "write_memory": True,
            "username": "admin",
            "password": "pass",
            "enable_password": "secret",
            "timeout": 60,
        }
        with patch("backend.advanced.execute_vlan_change", new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = _make_record()
            resp = await client.post("/advanced/vlan-change", json=payload)
            assert resp.status_code == 201

    async def test_audit_record_has_expected_fields(
        self, client: AsyncClient, _enable_advanced: AuditStore
    ) -> None:
        """Frontend expects AuditRecord with: id, timestamp, device_id, device_ip,
        platform, operation, status, changes, commands_sent, pre_state, post_state,
        rollback_commands, undo_of, undone_by, error."""
        store = _enable_advanced
        await store.create(_make_record("contract-001"))

        resp = await client.get("/advanced/audit/contract-001")
        data = resp.json()
        expected_fields = {
            "id",
            "timestamp",
            "device_id",
            "device_ip",
            "platform",
            "operation",
            "status",
            "changes",
            "commands_sent",
            "pre_state",
            "post_state",
            "rollback_commands",
            "undo_of",
            "undone_by",
            "error",
        }
        assert expected_fields.issubset(data.keys()), f"Missing: {expected_fields - data.keys()}"

    async def test_port_change_has_expected_fields(
        self, client: AsyncClient, _enable_advanced: AuditStore
    ) -> None:
        """Frontend expects PortChange with: interface, field, old_value,
        new_value, verified."""
        store = _enable_advanced
        await store.create(_make_record("contract-002"))

        resp = await client.get("/advanced/audit/contract-002")
        change = resp.json()["changes"][0]
        expected_fields = {"interface", "field", "old_value", "new_value", "verified"}
        assert expected_fields.issubset(change.keys())

    async def test_list_audit_accepts_device_id_filter(
        self, client: AsyncClient, _enable_advanced: AuditStore
    ) -> None:
        """Frontend listAuditRecords() sends device_id as query param."""
        resp = await client.get("/advanced/audit", params={"device_id": "SW-01"})
        assert resp.status_code == 200

    async def test_list_audit_accepts_pagination(
        self, client: AsyncClient, _enable_advanced: AuditStore
    ) -> None:
        """Frontend listAuditRecords() sends limit and offset as query params."""
        resp = await client.get("/advanced/audit", params={"limit": "10", "offset": "0"})
        assert resp.status_code == 200

    async def test_export_format_param_name(
        self, client: AsyncClient, _enable_advanced: AuditStore
    ) -> None:
        """Frontend exportAuditLog() sends 'format' query param.
        Backend accepts it via Query alias."""
        store = _enable_advanced
        await store.create(_make_record("export-001"))

        # Frontend sends 'format' — backend accepts via alias
        resp = await client.get("/advanced/audit/export", params={"format": "csv"})
        assert resp.status_code == 200
        assert "text/csv" in resp.headers["content-type"]

    async def test_undo_accepts_credentials_in_body(
        self, client: AsyncClient, _enable_advanced: AuditStore
    ) -> None:
        """Frontend undoAuditRecord() sends credentials in request body."""
        store = _enable_advanced
        await store.create(_make_record("undo-contract"))

        with patch("backend.advanced.undo_change", new_callable=AsyncMock) as mock_undo:
            mock_undo.return_value = _make_record(
                "undo-result", operation="undo", undo_of="undo-contract"
            )
            resp = await client.post(
                "/advanced/audit/undo-contract/undo",
                json={"username": "admin", "password": "pass"},
            )
            assert resp.status_code == 201
