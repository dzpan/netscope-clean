"""SNMP fallback collector for legacy devices without SSH.

Uses standard MIBs to discover device identity, interfaces, and neighbors
(via LLDP-MIB or CISCO-CDP-MIB) for devices that cannot be reached over SSH.

Requires ``pysnmp-lextudio`` for async SNMP operations::

    pip install pysnmp-lextudio

The collector produces the same ``Device`` and ``NeighborRecord`` models as
the SSH-based discovery engine, allowing seamless integration.
"""

from __future__ import annotations

import logging
from typing import Any

from backend.models import (
    Device,
    DeviceStatus,
    InterfaceInfo,
    NeighborRecord,
)

logger = logging.getLogger(__name__)

# Standard OIDs
OID_SYS_DESCR = "1.3.6.1.2.1.1.1.0"
OID_SYS_NAME = "1.3.6.1.2.1.1.5.0"
OID_SYS_OBJECT_ID = "1.3.6.1.2.1.1.2.0"

# IF-MIB: interface table
OID_IF_DESCR = "1.3.6.1.2.1.2.2.1.2"  # ifDescr
OID_IF_OPER_STATUS = "1.3.6.1.2.1.2.2.1.8"  # ifOperStatus
OID_IF_SPEED = "1.3.6.1.2.1.2.2.1.5"  # ifSpeed

# IP-MIB: IP address table
OID_IP_ADDR_ENTRY = "1.3.6.1.2.1.4.20.1.1"  # ipAdEntAddr
OID_IP_ADDR_IF_INDEX = "1.3.6.1.2.1.4.20.1.2"  # ipAdEntIfIndex

# LLDP-MIB: LLDP remote table
OID_LLDP_REM_SYS_NAME = "1.0.8802.1.1.2.1.4.1.1.9"
OID_LLDP_REM_PORT_ID = "1.0.8802.1.1.2.1.4.1.1.7"
OID_LLDP_REM_PORT_DESC = "1.0.8802.1.1.2.1.4.1.1.8"
OID_LLDP_REM_MAN_ADDR = "1.0.8802.1.1.2.1.4.2.1.4"
OID_LLDP_LOC_PORT_ID = "1.0.8802.1.1.2.1.3.7.1.3"

# CISCO-CDP-MIB: CDP cache table
OID_CDP_CACHE_DEVICE_ID = "1.3.6.1.4.1.9.9.23.1.2.1.1.6"
OID_CDP_CACHE_PLATFORM = "1.3.6.1.4.1.9.9.23.1.2.1.1.8"
OID_CDP_CACHE_ADDRESS = "1.3.6.1.4.1.9.9.23.1.2.1.1.4"
OID_CDP_CACHE_DEVICE_PORT = "1.3.6.1.4.1.9.9.23.1.2.1.1.7"

# Interface operational status values
_IF_STATUS_MAP = {1: "up", 2: "down", 3: "testing", 4: "unknown", 5: "dormant"}

try:
    from pysnmp.hlapi.v3arch.asyncio import (
        CommunityData,
        ContextData,
        ObjectIdentity,
        ObjectType,
        SnmpEngine,
        UdpTransportTarget,
        bulkWalkCmd,
        getCmd,
    )

    PYSNMP_AVAILABLE = True
except ImportError:
    PYSNMP_AVAILABLE = False
    logger.info("pysnmp not available — SNMP fallback disabled")


class SnmpCollector:
    """Async SNMP collector for a single device."""

    def __init__(
        self,
        host: str,
        community: str = "public",
        port: int = 161,
        timeout: float = 5.0,
        retries: int = 1,
    ) -> None:
        self.host = host
        self.community = community
        self.port = port
        self.timeout = timeout
        self.retries = retries

    async def collect(self) -> tuple[Device | None, list[NeighborRecord]]:
        """Collect device info and neighbors via SNMP.

        Returns (Device, neighbors) or (None, []) on failure.
        """
        if not PYSNMP_AVAILABLE:
            logger.warning("pysnmp not installed — cannot collect via SNMP")
            return None, []

        engine = SnmpEngine()
        auth = CommunityData(self.community)
        transport = await UdpTransportTarget.create(
            (self.host, self.port),
            timeout=self.timeout,
            retries=self.retries,
        )
        context = ContextData()

        try:
            # Get system identity
            sys_descr, sys_name = await self._get_system_info(engine, auth, transport, context)
            if not sys_name:
                sys_name = self.host

            hostname = sys_name.split(".")[0]  # strip FQDN

            # Get interfaces
            interfaces = await self._get_interfaces(engine, auth, transport, context)

            # Get neighbors (try LLDP first, then CDP)
            neighbors = await self._get_lldp_neighbors(engine, auth, transport, context)
            if not neighbors:
                neighbors = await self._get_cdp_neighbors(engine, auth, transport, context)

            device = Device(
                id=hostname,
                hostname=hostname,
                mgmt_ip=self.host,
                platform=_extract_platform(sys_descr),
                status=DeviceStatus.OK,
                interfaces=interfaces,
            )

            return device, neighbors

        except Exception as exc:
            logger.error("SNMP collection failed for %s: %s", self.host, exc)
            return None, []

    async def _get_system_info(
        self,
        engine: Any,
        auth: Any,
        transport: Any,
        context: Any,
    ) -> tuple[str, str]:
        """Get sysDescr and sysName."""
        err_indication, err_status, _, var_binds = await getCmd(
            engine,
            auth,
            transport,
            context,
            ObjectType(ObjectIdentity(OID_SYS_DESCR)),
            ObjectType(ObjectIdentity(OID_SYS_NAME)),
        )
        if err_indication or err_status:
            return "", ""

        sys_descr = str(var_binds[0][1]) if len(var_binds) > 0 else ""
        sys_name = str(var_binds[1][1]) if len(var_binds) > 1 else ""
        return sys_descr, sys_name

    async def _get_interfaces(
        self,
        engine: Any,
        auth: Any,
        transport: Any,
        context: Any,
    ) -> list[InterfaceInfo]:
        """Walk IF-MIB ifTable for interface info."""
        interfaces: dict[str, InterfaceInfo] = {}

        # Walk ifDescr
        async for err_ind, err_status, _, var_binds in bulkWalkCmd(
            engine,
            auth,
            transport,
            context,
            0,
            25,
            ObjectType(ObjectIdentity(OID_IF_DESCR)),
        ):
            if err_ind or err_status:
                break
            for oid, val in var_binds:
                if_index = str(oid).split(".")[-1]
                interfaces[if_index] = InterfaceInfo(name=str(val))

        # Walk ifOperStatus
        async for err_ind, err_status, _, var_binds in bulkWalkCmd(
            engine,
            auth,
            transport,
            context,
            0,
            25,
            ObjectType(ObjectIdentity(OID_IF_OPER_STATUS)),
        ):
            if err_ind or err_status:
                break
            for oid, val in var_binds:
                if_index = str(oid).split(".")[-1]
                if if_index in interfaces:
                    interfaces[if_index].status = _IF_STATUS_MAP.get(int(val), "unknown")

        return list(interfaces.values())

    async def _get_lldp_neighbors(
        self,
        engine: Any,
        auth: Any,
        transport: Any,
        context: Any,
    ) -> list[NeighborRecord]:
        """Walk LLDP-MIB lldpRemTable for LLDP neighbors."""
        neighbors: dict[str, dict[str, str]] = {}

        # Walk lldpRemSysName
        async for err_ind, err_status, _, var_binds in bulkWalkCmd(
            engine,
            auth,
            transport,
            context,
            0,
            25,
            ObjectType(ObjectIdentity(OID_LLDP_REM_SYS_NAME)),
        ):
            if err_ind or err_status:
                break
            for oid, val in var_binds:
                key = str(oid).replace(OID_LLDP_REM_SYS_NAME + ".", "")
                neighbors.setdefault(key, {})["device_id"] = str(val)

        # Walk lldpRemPortId
        async for err_ind, err_status, _, var_binds in bulkWalkCmd(
            engine,
            auth,
            transport,
            context,
            0,
            25,
            ObjectType(ObjectIdentity(OID_LLDP_REM_PORT_ID)),
        ):
            if err_ind or err_status:
                break
            for oid, val in var_binds:
                key = str(oid).replace(OID_LLDP_REM_PORT_ID + ".", "")
                neighbors.setdefault(key, {})["remote_interface"] = str(val)

        records: list[NeighborRecord] = []
        for data in neighbors.values():
            device_id = data.get("device_id", "")
            if not device_id:
                continue
            records.append(
                NeighborRecord(
                    device_id=device_id.split(".")[0],
                    local_interface=data.get("local_interface", ""),
                    remote_interface=data.get("remote_interface"),
                    protocol="LLDP",
                )
            )
        return records

    async def _get_cdp_neighbors(
        self,
        engine: Any,
        auth: Any,
        transport: Any,
        context: Any,
    ) -> list[NeighborRecord]:
        """Walk CISCO-CDP-MIB cdpCacheTable for CDP neighbors."""
        neighbors: dict[str, dict[str, str]] = {}

        # Walk cdpCacheDeviceId
        async for err_ind, err_status, _, var_binds in bulkWalkCmd(
            engine,
            auth,
            transport,
            context,
            0,
            25,
            ObjectType(ObjectIdentity(OID_CDP_CACHE_DEVICE_ID)),
        ):
            if err_ind or err_status:
                break
            for oid, val in var_binds:
                key = str(oid).replace(OID_CDP_CACHE_DEVICE_ID + ".", "")
                neighbors.setdefault(key, {})["device_id"] = str(val)

        # Walk cdpCacheDevicePort
        async for err_ind, err_status, _, var_binds in bulkWalkCmd(
            engine,
            auth,
            transport,
            context,
            0,
            25,
            ObjectType(ObjectIdentity(OID_CDP_CACHE_DEVICE_PORT)),
        ):
            if err_ind or err_status:
                break
            for oid, val in var_binds:
                key = str(oid).replace(OID_CDP_CACHE_DEVICE_PORT + ".", "")
                neighbors.setdefault(key, {})["remote_interface"] = str(val)

        # Walk cdpCacheAddress for IP
        async for err_ind, err_status, _, var_binds in bulkWalkCmd(
            engine,
            auth,
            transport,
            context,
            0,
            25,
            ObjectType(ObjectIdentity(OID_CDP_CACHE_ADDRESS)),
        ):
            if err_ind or err_status:
                break
            for oid, val in var_binds:
                key = str(oid).replace(OID_CDP_CACHE_ADDRESS + ".", "")
                # CDP address is binary — convert to dotted-decimal
                addr_bytes = bytes(val)
                if len(addr_bytes) == 4:
                    ip_str = ".".join(str(b) for b in addr_bytes)
                    neighbors.setdefault(key, {})["ip_address"] = ip_str

        records: list[NeighborRecord] = []
        for data in neighbors.values():
            device_id = data.get("device_id", "")
            if not device_id:
                continue
            records.append(
                NeighborRecord(
                    device_id=device_id.split(".")[0],
                    ip_address=data.get("ip_address"),
                    local_interface=data.get("local_interface", ""),
                    remote_interface=data.get("remote_interface"),
                    protocol="CDP",
                )
            )
        return records


def _extract_platform(sys_descr: str) -> str | None:
    """Best-effort platform extraction from sysDescr."""
    if not sys_descr:
        return None
    # Cisco: "Cisco IOS Software, C3750E Software ..."
    # Arista: "Arista Networks EOS version ..."
    # Juniper: "Juniper Networks, Inc. ex4200-48t ..."
    first_line = sys_descr.split("\n")[0].strip()
    return first_line[:100] if first_line else None
