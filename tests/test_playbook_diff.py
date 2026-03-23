"""Tests for the playbook execution diff endpoint (NET-65 P3.5)."""

from __future__ import annotations

import pytest


class TestPlaybookDiffAPI:
    @pytest.fixture
    def client(self):  # type: ignore[no-untyped-def]
        from httpx import ASGITransport, AsyncClient

        from backend.main import app

        transport = ASGITransport(app=app)
        return AsyncClient(transport=transport, base_url="http://test/api/v1")

    async def test_diff_run_not_found(self, client) -> None:  # type: ignore[no-untyped-def]
        resp = await client.get("/playbook-runs/nonexistent/diff")
        assert resp.status_code == 404

    async def test_diff_compare_run_not_found(self, client) -> None:  # type: ignore[no-untyped-def]
        """Create a run, then request diff with a nonexistent compare run."""
        from datetime import UTC, datetime

        from backend.main import _playbook_store
        from backend.playbooks import (
            DeviceExecutionResult,
            ExecutionStatus,
            PlaybookExecution,
        )

        execution = PlaybookExecution(
            id="diff-test-1",
            playbook_id="pb-1",
            playbook_title="Test",
            timestamp=datetime.now(UTC),
            overall_status=ExecutionStatus.SUCCESS,
            device_results=[
                DeviceExecutionResult(
                    device_id="sw1",
                    device_ip="10.0.0.1",
                    status=ExecutionStatus.SUCCESS,
                    pre_check_outputs={"show vlan brief": "VLAN 1"},
                    post_check_outputs={"show vlan brief": "VLAN 1\nVLAN 100"},
                )
            ],
        )
        await _playbook_store.save_execution(execution)

        resp = await client.get("/playbook-runs/diff-test-1/diff?compare_run_id=nonexistent")
        assert resp.status_code == 404

    async def test_diff_pre_vs_post(self, client) -> None:  # type: ignore[no-untyped-def]
        """Diff within a single run (pre-check vs post-check)."""
        from datetime import UTC, datetime

        from backend.main import _playbook_store
        from backend.playbooks import (
            DeviceExecutionResult,
            ExecutionStatus,
            PlaybookExecution,
        )

        execution = PlaybookExecution(
            id="diff-test-2",
            playbook_id="pb-1",
            playbook_title="Test",
            timestamp=datetime.now(UTC),
            overall_status=ExecutionStatus.SUCCESS,
            device_results=[
                DeviceExecutionResult(
                    device_id="sw1",
                    device_ip="10.0.0.1",
                    status=ExecutionStatus.SUCCESS,
                    pre_check_outputs={"show vlan brief": "VLAN 1"},
                    post_check_outputs={"show vlan brief": "VLAN 1\nVLAN 100"},
                )
            ],
        )
        await _playbook_store.save_execution(execution)

        resp = await client.get("/playbook-runs/diff-test-2/diff")
        assert resp.status_code == 200
        data = resp.json()
        assert data["run_id"] == "diff-test-2"
        assert data["compare_run_id"] is None
        assert len(data["device_diffs"]) == 1

        dd = data["device_diffs"][0]
        assert dd["device_id"] == "sw1"
        assert "show vlan brief" in dd["commands"]
        assert "+VLAN 100" in dd["commands"]["show vlan brief"]

    async def test_diff_no_changes(self, client) -> None:  # type: ignore[no-untyped-def]
        """When pre and post are identical, no diff output."""
        from datetime import UTC, datetime

        from backend.main import _playbook_store
        from backend.playbooks import (
            DeviceExecutionResult,
            ExecutionStatus,
            PlaybookExecution,
        )

        execution = PlaybookExecution(
            id="diff-test-3",
            playbook_id="pb-1",
            playbook_title="Test",
            timestamp=datetime.now(UTC),
            overall_status=ExecutionStatus.SUCCESS,
            device_results=[
                DeviceExecutionResult(
                    device_id="sw1",
                    device_ip="10.0.0.1",
                    status=ExecutionStatus.SUCCESS,
                    pre_check_outputs={"show vlan brief": "VLAN 1"},
                    post_check_outputs={"show vlan brief": "VLAN 1"},
                )
            ],
        )
        await _playbook_store.save_execution(execution)

        resp = await client.get("/playbook-runs/diff-test-3/diff")
        assert resp.status_code == 200
        data = resp.json()
        dd = data["device_diffs"][0]
        assert len(dd["commands"]) == 0

    async def test_diff_cross_run(self, client) -> None:  # type: ignore[no-untyped-def]
        """Diff post-check outputs between two runs."""
        from datetime import UTC, datetime

        from backend.main import _playbook_store
        from backend.playbooks import (
            DeviceExecutionResult,
            ExecutionStatus,
            PlaybookExecution,
        )

        exec_a = PlaybookExecution(
            id="diff-test-4a",
            playbook_id="pb-1",
            playbook_title="Test",
            timestamp=datetime.now(UTC),
            overall_status=ExecutionStatus.SUCCESS,
            device_results=[
                DeviceExecutionResult(
                    device_id="sw1",
                    device_ip="10.0.0.1",
                    status=ExecutionStatus.SUCCESS,
                    post_check_outputs={"show vlan brief": "VLAN 1\nVLAN 100"},
                )
            ],
        )
        exec_b = PlaybookExecution(
            id="diff-test-4b",
            playbook_id="pb-1",
            playbook_title="Test",
            timestamp=datetime.now(UTC),
            overall_status=ExecutionStatus.SUCCESS,
            device_results=[
                DeviceExecutionResult(
                    device_id="sw1",
                    device_ip="10.0.0.1",
                    status=ExecutionStatus.SUCCESS,
                    post_check_outputs={"show vlan brief": "VLAN 1\nVLAN 200"},
                )
            ],
        )
        await _playbook_store.save_execution(exec_a)
        await _playbook_store.save_execution(exec_b)

        resp = await client.get("/playbook-runs/diff-test-4a/diff?compare_run_id=diff-test-4b")
        assert resp.status_code == 200
        data = resp.json()
        assert data["compare_run_id"] == "diff-test-4b"
        dd = data["device_diffs"][0]
        diff_text = dd["commands"]["show vlan brief"]
        assert "-VLAN 100" in diff_text
        assert "+VLAN 200" in diff_text
