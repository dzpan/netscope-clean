"""Background scheduler for periodic re-discovery.

Activated when NETSCOPE_REDISCOVERY_INTERVAL > 0 AND NETSCOPE_DB_PATH is set
(so original DiscoverRequests can be retrieved and diffs can be stored).

Each scheduled run:
  1. Lists all sessions that have a stored DiscoverRequest.
  2. Re-runs discovery with the original parameters.
  3. Computes a diff against the previous snapshot.
  4. Saves the new session and diff to SQLite.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


async def _rediscovery_loop(interval: int, db_path: Path, retention_days: int = 0) -> None:
    """Run re-discovery for all persisted sessions on *interval*-second cadence."""
    from backend.alerts import HttpxAlertClient, fire_alerts
    from backend.diff import compute_diff
    from backend.discovery import run_discovery
    from backend.store_sqlite import (
        SQLiteAlertRuleStore,
        SQLiteAlertStore,
        SQLiteDiffStore,
        SQLiteDiscoverRequestStore,
        SQLiteSessionStore,
        _open_db,
        cleanup_old_snapshots,
    )

    req_store = SQLiteDiscoverRequestStore(db_path)
    session_store = SQLiteSessionStore(db_path)
    diff_store = SQLiteDiffStore(db_path)
    alert_rule_store = SQLiteAlertRuleStore(db_path)
    alert_store = SQLiteAlertStore(db_path)
    http_client = HttpxAlertClient()
    # Shared connection for retention cleanup (avoids opening extra connections)
    _cleanup_conn = _open_db(db_path)

    logger.info("Scheduler started: re-discovery every %ds", interval)

    while True:
        await asyncio.sleep(interval)
        logger.info("Scheduler: starting periodic re-discovery pass")

        sessions = session_store.list_all()
        if not sessions:
            logger.debug("Scheduler: no sessions to re-discover")
        else:
            for previous in sessions:
                req = req_store.get(previous.session_id)
                if req is None:
                    logger.debug(
                        "Scheduler: no stored request for session %s — skipping",
                        previous.session_id,
                    )
                    continue

                try:
                    logger.info(
                        "Scheduler: re-discovering session %s (seeds=%s)",
                        previous.session_id,
                        req.seeds,
                    )
                    current = await run_discovery(req)
                    await session_store.save(current)

                    diff = compute_diff(current, previous)
                    await diff_store.save(diff)

                    # Fire alerts
                    rules = alert_rule_store.list_all()
                    if rules:
                        alerts = await fire_alerts(diff, rules, http_client)
                        for alert in alerts:
                            await alert_store.save(alert)
                        if alerts:
                            logger.info(
                                "Scheduler: %d alert(s) fired for diff %s",
                                len(alerts),
                                diff.diff_id,
                            )

                    logger.info(
                        "Scheduler: session %s re-discovered → new=%s changes=%d",
                        previous.session_id,
                        current.session_id,
                        diff.total_changes,
                    )
                except Exception:
                    logger.exception(
                        "Scheduler: re-discovery failed for session %s", previous.session_id
                    )

        # Run retention cleanup after each pass
        if retention_days > 0:
            deleted = cleanup_old_snapshots(_cleanup_conn, retention_days)
            if deleted:
                logger.info("Scheduler: retention cleanup deleted %d old snapshot(s)", deleted)


def start_scheduler(interval: int, db_path: Path, retention_days: int = 0) -> asyncio.Task[None]:
    """Spawn the background re-discovery loop and return the asyncio Task."""
    return asyncio.create_task(
        _rediscovery_loop(interval, db_path, retention_days),
        name="netscope-scheduler",
    )
