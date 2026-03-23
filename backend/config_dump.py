"""Device config dump — runs a full set of show commands and stores the output."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from uuid import uuid4

from backend.models import CommandResult, ConfigDump, ConfigDumpRequest, CredentialSet

logger = logging.getLogger(__name__)

try:
    from scrapli.driver.core import AsyncIOSXEDriver

    SCRAPLI_AVAILABLE = True
except ImportError:
    SCRAPLI_AVAILABLE = False

# Ordered list of commands to collect.
# Each entry: (command, label)  — label is used for display only.
DUMP_COMMANDS: list[tuple[str, str]] = [
    ("show version", "Version"),
    ("show running-config", "Running Config"),
    ("show ip interface brief", "IP Interfaces"),
    ("show interfaces", "Interfaces (detail)"),
    ("show interfaces status", "Interfaces Status"),
    ("show vlan brief", "VLANs"),
    ("show ip route", "IP Routing Table"),
    ("show ip arp", "ARP Table"),
    ("show mac address-table", "MAC Address Table"),
    ("show cdp neighbors detail", "CDP Neighbors"),
    ("show lldp neighbors detail", "LLDP Neighbors"),
    ("show spanning-tree", "Spanning Tree"),
    ("show etherchannel summary", "EtherChannel"),
    ("show nve peers", "NVE Peers (VXLAN)"),
    ("show nve vni", "NVE VNI Mappings (VXLAN)"),
    ("show bgp l2vpn evpn summary", "BGP EVPN Summary (VXLAN)"),
    ("show ip ospf neighbor", "OSPF Neighbors"),
    ("show ip bgp summary", "BGP Summary"),
    ("show standby brief", "HSRP"),
    ("show ntp status", "NTP Status"),
    ("show logging", "Syslog"),
    ("show environment all", "Environment"),
    ("show inventory", "Inventory"),
    ("show license summary", "Licenses"),
]


def _build_cred_list(req: ConfigDumpRequest) -> list[CredentialSet]:
    """Return ordered list of credentials to try. Explicit sets first, primary as fallback."""
    creds: list[CredentialSet] = list(req.credential_sets)
    if req.username:
        primary = CredentialSet(
            username=req.username,
            password=req.password,
            enable_password=req.enable_password,
        )
        already = any(
            c.username == primary.username and c.password == primary.password for c in creds
        )
        if not already:
            creds.append(primary)
    return creds


async def run_config_dump(req: ConfigDumpRequest) -> ConfigDump:
    """SSH into device and run all DUMP_COMMANDS, trying each credential set in order.

    Uses explicit open/close instead of ``async with`` to prevent scrapli's
    ``__aexit__`` from swallowing authentication exceptions.
    """
    if not SCRAPLI_AVAILABLE:
        raise RuntimeError("Scrapli not installed")

    from backend.discovery import _base_opts, _classify_error
    from backend.utils import safe_close

    cred_list = _build_cred_list(req)
    if not cred_list:
        raise RuntimeError("No credentials provided")

    device_id = req.device_id or req.device_ip
    last_exc: Exception | None = None

    for i, creds in enumerate(cred_list, 1):
        opts = _base_opts(req.device_ip, creds, req.timeout)
        conn = AsyncIOSXEDriver(**opts)

        # --- Phase 1: open connection ---
        try:
            await conn.open()
        except Exception as exc:
            await safe_close(conn)
            last_exc = exc
            reason = _classify_error(exc)
            if reason != "auth_failed":
                logger.info(
                    "Config dump %s → %s (%s), not retrying credentials",
                    req.device_ip,
                    reason,
                    exc,
                )
                break
            logger.info(
                "Config dump %s → auth failed with creds %d/%d ('%s')",
                req.device_ip,
                i,
                len(cred_list),
                creds.username,
            )
            continue

        # --- Phase 2: run commands (connection is open) ---
        try:
            results: list[CommandResult] = []
            for command, _label in DUMP_COMMANDS:
                try:
                    resp = await conn.send_command(command)
                    output = resp.result.strip()
                    # Some IOS devices return error text instead of raising
                    if output.startswith("% ") or "Invalid input" in output:
                        results.append(CommandResult(command=command, output="", error=output))
                    else:
                        results.append(CommandResult(command=command, output=output))
                    logger.debug(
                        "Dumped '%s' from %s (%d chars)", command, req.device_ip, len(output)
                    )
                except Exception as exc:
                    logger.warning("Command '%s' failed on %s: %s", command, req.device_ip, exc)
                    results.append(CommandResult(command=command, output="", error=str(exc)))

            return ConfigDump(
                dump_id=str(uuid4()),
                device_id=device_id,
                device_ip=req.device_ip,
                dumped_at=datetime.now(UTC),
                commands=results,
            )
        finally:
            await safe_close(conn)

    # All credential sets exhausted or non-auth error
    raise (last_exc or RuntimeError("Config dump failed — no credentials succeeded"))
