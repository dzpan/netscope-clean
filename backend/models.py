from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.command_sets import CollectionProfile


class DiscoveryProtocol(StrEnum):
    CDP_PREFER = "cdp_prefer"
    LLDP_PREFER = "lldp_prefer"
    BOTH = "both"


class DeviceStatus(StrEnum):
    OK = "ok"
    UNREACHABLE = "unreachable"
    AUTH_FAILED = "auth_failed"
    TIMEOUT = "timeout"
    NO_CDP_LLDP = "no_cdp_lldp"
    PLACEHOLDER = "placeholder"


class InterfaceInfo(BaseModel):
    name: str
    status: str | None = None
    vlan: str | None = None
    speed: str | None = None
    duplex: str | None = None
    description: str | None = None
    ip_address: str | None = None


class ArpEntry(BaseModel):
    ip_address: str
    mac_address: str
    interface: str
    entry_type: str | None = None  # "dynamic", "static", "incomplete"


class MacTableEntry(BaseModel):
    mac_address: str
    vlan_id: str | None = None
    interface: str
    entry_type: str | None = None  # "dynamic", "static"


class RouteEntry(BaseModel):
    protocol: str | None = None  # code letter: "C", "L", "S", "O", "B", "D", "R"
    route_type: str | None = None  # "connected", "local", "static", "ospf", "bgp", "eigrp", "rip"
    destination: str  # CIDR: "10.0.0.0/24"
    next_hop: str | None = None  # gateway IP, or None for connected/local
    interface: str | None = None  # outgoing interface
    metric: str | None = None  # AD/metric string, e.g. "1/0"


class VlanInfo(BaseModel):
    vlan_id: str
    name: str | None = None
    status: str | None = None


class ChannelMember(BaseModel):
    interface: str  # "GigabitEthernet1/0/1" or "Eth1/1"
    status: str  # flag letter: "P", "D", "I", "s", "H", etc.
    status_desc: str | None = None  # human-readable: "bundled", "down", "stand-alone"


class EtherChannelInfo(BaseModel):
    channel_id: str  # group number: "1", "2"
    port_channel: str  # "Po1", "Po2"
    layer: str | None = None  # "Layer2" or "Layer3"
    status: str  # "up", "down"
    protocol: str | None = None  # "LACP", "PAgP", or None (static/manual)
    members: list[ChannelMember] = []


class STPPortInfo(BaseModel):
    interface: str  # "Gi1/0/1", "Eth1/1"
    role: str  # "Root", "Desg", "Altn", "Back"
    state: str  # "FWD", "BLK", "LRN", "LIS", "DIS"
    cost: str | None = None  # "4", "19"
    port_priority: str | None = None  # "128.1"
    link_type: str | None = None  # "P2p", "Shr", "P2p Edge"


class STPVlanInfo(BaseModel):
    vlan_id: str  # "1", "10"
    protocol: str | None = None  # "rstp", "ieee", "mstp"
    root_priority: str | None = None  # "24577"
    root_address: str | None = None  # "0cd5.d366.2400"
    root_cost: str | None = None  # "4", "0"
    is_root: bool = False  # True when "This bridge is the root"
    bridge_priority: str | None = None  # "32769"
    bridge_address: str | None = None  # "aabb.ccdd.ee00"
    ports: list[STPPortInfo] = []


class NVEPeer(BaseModel):
    interface: str  # "nve1"
    peer_ip: str  # "10.1.1.2"
    state: str  # "Up", "Down"
    learn_type: str | None = None  # "CP" (control-plane), "DP" (data-plane)
    uptime: str | None = None  # "1d02h"
    router_mac: str | None = None  # "n/a" or "5254.0012.3456"


class VNIMapping(BaseModel):
    interface: str  # "nve1"
    vni: str  # "50001"
    multicast_group: str | None = None  # "UnicastBGP" or "239.1.1.1"
    state: str | None = None  # "Up", "Down"
    mode: str | None = None  # "CP" (control-plane)
    vni_type: str | None = None  # "L2 [1001]", "L3 [Tenant-VRF]"
    bd_vrf: str | None = None  # VLAN or VRF name: "1001", "Tenant-VRF"


class EVPNNeighbor(BaseModel):
    neighbor: str  # "10.1.1.2"
    asn: str | None = None  # "65001"
    version: str | None = None  # "4"
    msg_rcvd: str | None = None  # "12345"
    msg_sent: str | None = None  # "12300"
    up_down: str | None = None  # "1d02h"
    state_pfx_rcv: str | None = None  # "100" or "Idle"


class Device(BaseModel):
    id: str
    hostname: str | None = None
    mgmt_ip: str
    platform: str | None = None
    serial: str | None = None
    os_version: str | None = None
    uptime: str | None = None
    status: DeviceStatus
    interfaces: list[InterfaceInfo] = []
    vlans: list[VlanInfo] = []
    arp_table: list[ArpEntry] = []
    mac_table: list[MacTableEntry] = []
    route_table: list[RouteEntry] = []
    etherchannels: list[EtherChannelInfo] = []
    stp_info: list[STPVlanInfo] = []
    nve_peers: list[NVEPeer] = []
    vni_mappings: list[VNIMapping] = []
    evpn_neighbors: list[EVPNNeighbor] = []
    trunk_info: dict[str, TrunkInfo] = {}  # port name → trunk details
    capabilities: list[str] = []  # LLDP system capabilities (bridge, router, etc.)
    base_mac: str | None = None  # Base Ethernet MAC for chassis ID reconciliation


class VlanMapEntry(BaseModel):
    """Network-wide view: one VLAN across all devices."""

    vlan_id: str
    name: str | None = None
    devices: list[str]  # device IDs that have this VLAN
    trunk_ports: int = 0  # total trunk interfaces carrying this VLAN
    access_ports: int = 0  # total access interfaces in this VLAN


class LinkMember(BaseModel):
    """One physical member interface pair within a collapsed port-channel edge."""

    source_intf: str
    target_intf: str | None = None


class Link(BaseModel):
    source: str
    target: str
    source_intf: str
    target_intf: str | None = None
    protocol: Literal["CDP", "LLDP"]
    # Port-channel bundle metadata — populated when ≥2 member links are collapsed
    port_channel: str | None = None  # e.g. "Po1"
    member_count: int = 1
    speed_label: str | None = None  # e.g. "4x10G"
    members: list[LinkMember] = []
    # LLDP-specific metadata (populated when protocol == "LLDP")
    capabilities: list[str] = []  # system capabilities: bridge, router, station, etc.
    system_description: str | None = None  # remote system description / platform
    chassis_id_subtype: str | None = None  # mac, network-addr, ifName
    port_id_subtype: str | None = None  # ifName, ifAlias, mac, local
    port_description: str | None = None
    # LLDP-MED TLVs
    med_device_type: str | None = None  # class-i, class-ii, class-iii
    med_poe_requested: float | None = None  # watts
    med_poe_allocated: float | None = None  # watts
    med_network_policy: str | None = None  # VLAN/DSCP policy string


class Failure(BaseModel):
    target: str
    reason: str
    detail: str | None = None


class DiscoveryProgress(BaseModel):
    """Real-time progress event emitted during BFS discovery."""

    session_id: str
    total_queued: int  # total devices queued for discovery
    discovered: int  # successfully discovered so far
    failed: int  # failed so far
    in_progress: int  # currently being discovered
    latest_device: str | None = None  # hostname or IP of last completed device
    latest_status: str | None = None  # "ok", "auth_failed", "timeout", etc.
    phase: str = "discovering"  # "discovering", "finalizing", "done"


class TopologyResult(BaseModel):
    session_id: str
    discovered_at: datetime
    devices: list[Device]
    links: list[Link]
    failures: list[Failure]
    native_vlan_mismatches: list[NativeVlanMismatch] = []


class AuthType(StrEnum):
    PASSWORD = "password"
    SSH_KEY = "ssh_key"
    SNMP_V2C = "snmp_v2c"
    SNMP_V3 = "snmp_v3"


class CredentialSet(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "username": "admin",
                    "password": "cisco123",
                    "enable_password": "enable123",
                    "label": "Core Switches",
                },
                {
                    "username": "admin",
                    "auth_type": "ssh_key",
                    "ssh_private_key": "-----BEGIN OPENSSH PRIVATE KEY-----\n...",
                    "enable_password": "enable123",
                    "label": "Key-based devices",
                },
            ]
        }
    )

    username: str = ""
    password: str = ""
    auth_type: AuthType = AuthType.PASSWORD
    ssh_private_key: str | None = None  # PEM-encoded private key
    ssh_key_passphrase: str | None = None  # passphrase for encrypted keys
    enable_password: str | None = None
    label: str | None = None  # optional human-readable name, e.g. "Switches"
    # SNMP v2c fields
    snmp_community: str | None = None  # community string for SNMP v2c
    snmp_port: int | None = 161
    # SNMP v3 fields
    snmp_auth_protocol: str | None = None  # MD5, SHA, SHA256
    snmp_auth_password: str | None = None
    snmp_priv_protocol: str | None = None  # DES, AES128, AES256
    snmp_priv_password: str | None = None


class DiscoverRequest(BaseModel):
    """Parameters for a BFS network discovery run."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "seeds": ["10.0.0.1"],
                    "username": "admin",
                    "password": "cisco123",
                    "max_hops": 3,
                    "discovery_protocol": "cdp_prefer",
                    "collection_profile": "standard",
                },
            ]
        }
    )

    seeds: list[str] = Field(min_length=1)
    scope: str | None = None
    username: str = ""
    password: str = ""
    enable_password: str | None = None
    credential_sets: list[CredentialSet] = []  # tried in order; first success wins
    max_hops: int = Field(default=2, ge=0, le=10)
    max_concurrency: int = Field(default=10, ge=1, le=50)
    timeout: int = Field(default=30, ge=5, le=120)
    discovery_protocol: DiscoveryProtocol = DiscoveryProtocol.CDP_PREFER
    prefer_cdp: bool | None = None  # deprecated — mapped to discovery_protocol for backward compat
    switch_only: bool = False  # when True, skip non-switch neighbors (APs, phones, etc.)
    collection_profile: CollectionProfile = CollectionProfile.STANDARD
    custom_groups: list[str] = []  # active group names when profile == CUSTOM

    @field_validator("seeds")
    @classmethod
    def seeds_non_empty(cls, v: list[str]) -> list[str]:
        v = [s.strip() for s in v if s.strip()]
        if not v:
            raise ValueError("At least one seed IP or hostname is required")
        return v

    def model_post_init(self, __context: object) -> None:
        """Map legacy prefer_cdp field to discovery_protocol."""
        if self.prefer_cdp is not None:
            self.discovery_protocol = (
                DiscoveryProtocol.CDP_PREFER if self.prefer_cdp else DiscoveryProtocol.LLDP_PREFER
            )


class ProbeRequest(BaseModel):
    """Probe a single device to collect its state without BFS traversal."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {"host": "10.0.0.1", "username": "admin", "password": "cisco123", "timeout": 15},
            ]
        }
    )

    host: str
    username: str
    password: str
    enable_password: str | None = None
    timeout: int = Field(default=15, ge=5, le=60)


class RetryRequest(BaseModel):
    session_id: str
    targets: list[str]  # IPs to retry
    username: str
    password: str
    enable_password: str | None = None
    timeout: int = Field(default=30, ge=5, le=120)
    max_hops: int = Field(default=2, ge=0, le=10)  # continue BFS from retried devices


class RetryFailedRequest(BaseModel):
    """Retry all failed devices (any failure type) from a session."""

    session_id: str
    credential_sets: list[CredentialSet] = []  # override credentials for retry
    username: str = ""
    password: str = ""
    enable_password: str | None = None
    timeout: int = Field(default=30, ge=5, le=120)
    max_hops: int = Field(default=0, ge=0, le=10)  # default 0 = don't BFS further
    reason_filter: list[str] = []  # empty = all failures; e.g. ["timeout","unreachable"]


class ProbeResult(BaseModel):
    host: str
    success: bool
    hostname: str | None = None
    platform: str | None = None
    os_version: str | None = None
    error: str | None = None


# Config dump models


class CommandResult(BaseModel):
    command: str
    output: str
    error: str | None = None


class ConfigDump(BaseModel):
    dump_id: str
    device_id: str
    device_ip: str
    dumped_at: datetime
    commands: list[CommandResult]


class ConfigDumpRequest(BaseModel):
    """Request to collect running-config from a device via SSH."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "device_ip": "10.0.0.1",
                    "credential_sets": [
                        {"username": "admin", "password": "cisco123"},
                    ],
                    "timeout": 60,
                },
            ]
        }
    )

    device_ip: str
    device_id: str | None = None
    credential_sets: list[CredentialSet] = []  # tried in order; first success wins
    username: str = ""  # fallback credential (backward compat)
    password: str = ""
    enable_password: str | None = None
    timeout: int = Field(default=60, ge=5, le=180)


# Diff models


class DeviceChange(BaseModel):
    """A single changed field on a device between two snapshots."""

    field: str
    before: str | None
    after: str | None


class DeviceDiff(BaseModel):
    """Per-device changes between two snapshots."""

    device_id: str
    hostname: str | None = None
    changes: list[DeviceChange] = []


class LinkKey(BaseModel):
    """Canonical link identifier (order-independent)."""

    source: str
    target: str
    source_intf: str
    target_intf: str | None = None


class TopologyDiff(BaseModel):
    """Diff result between two topology snapshots."""

    diff_id: str
    current_session_id: str
    previous_session_id: str
    computed_at: datetime
    # Device-level changes
    devices_added: list[str] = []  # device IDs added
    devices_removed: list[str] = []  # device IDs removed
    devices_changed: list[DeviceDiff] = []  # devices with field-level changes
    # Link-level changes
    links_added: list[LinkKey] = []
    links_removed: list[LinkKey] = []
    # Summary counts for quick display
    total_changes: int = 0


class RediscoverRequest(BaseModel):
    """Body for POST /sessions/{id}/rediscover — override credentials if needed."""

    username: str | None = None
    password: str | None = None
    enable_password: str | None = None
    credential_sets: list[CredentialSet] = []


# Internal parser result types


class NeighborRecord(BaseModel):
    device_id: str
    ip_address: str | None = None
    local_interface: str
    remote_interface: str | None = None
    platform: str | None = None
    protocol: Literal["CDP", "LLDP"]
    chassis_id_subtype: str | None = None  # mac, network-addr, ifName, etc.
    port_id_subtype: str | None = None  # ifName, ifAlias, mac, local
    capabilities: list[str] = []  # bridge, router, station, telephone, etc.
    port_description: str | None = None
    chassis_id: str | None = None  # raw chassis ID value for reconciliation
    # LLDP-MED TLVs
    med_device_type: str | None = None  # class-i, class-ii, class-iii
    med_poe_requested: float | None = None  # watts
    med_poe_allocated: float | None = None  # watts
    med_network_policy: str | None = None  # VLAN/DSCP policy string
    # 802.1 VLAN TLVs
    vlan_id: int | None = None  # Port VLAN ID (native/access)
    vlan_name: str | None = None
    # 802.3 Link Aggregation
    lag_supported: bool | None = None
    lag_enabled: bool | None = None
    lag_port_channel_id: int | None = None


class VersionInfo(BaseModel):
    hostname: str | None = None
    platform: str | None = None
    serial: str | None = None
    os_version: str | None = None
    uptime: str | None = None
    base_mac: str | None = None  # "Base Ethernet MAC Address" from show version


class InventoryItem(BaseModel):
    name: str  # "Chassis", "Switch 1", "Power Supply 1"
    description: str  # "Cisco Catalyst 3850-48P Switch"
    pid: str | None = None  # product ID: "WS-C3850-48P"
    vid: str | None = None  # version ID: "V02"
    serial: str | None = None  # serial number: "FCW1234A0BC"


class TrunkInfo(BaseModel):
    mode: str | None = None  # "on", "desirable", "auto"
    encapsulation: str | None = None  # "802.1q", "isl"
    status: str | None = None  # "trunking", "not-trunking"
    native_vlan: str | None = None  # "1"
    allowed_vlans: str | None = None  # "1-4094"
    active_vlans: str | None = None  # "1,10,20"
    forwarding_vlans: str | None = None  # "1,10"


class NativeVlanMismatch(BaseModel):
    source: str  # device ID
    target: str  # device ID
    source_intf: str  # port name on source device
    target_intf: str  # port name on target device
    source_native_vlan: str
    target_native_vlan: str


# Search models


# ---------------------------------------------------------------------------
# Alert models
# ---------------------------------------------------------------------------


class AlertTrigger(StrEnum):
    DEVICE_ADDED = "device_added"
    DEVICE_REMOVED = "device_removed"
    LINK_ADDED = "link_added"
    LINK_REMOVED = "link_removed"
    DEVICE_STATUS_CHANGE = "device_status_change"
    STP_CHANGE = "stp_change"  # future: reserved for STP topology change detection


class AlertSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class AlertRule(BaseModel):
    rule_id: str
    name: str
    triggers: list[AlertTrigger]  # rule fires if any of these trigger types match
    severity: AlertSeverity = AlertSeverity.WARNING
    webhook_url: str | None = None  # POST JSON payload here on match
    created_at: datetime


class AlertRuleRequest(BaseModel):
    """Create or update an alert rule."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "name": "New device alert",
                    "triggers": ["device_added"],
                    "severity": "warning",
                    "webhook_url": None,
                },
            ]
        }
    )

    name: str = Field(min_length=1, max_length=200)
    triggers: list[AlertTrigger] = Field(min_length=1)
    severity: AlertSeverity = AlertSeverity.WARNING
    webhook_url: str | None = None


class Alert(BaseModel):
    alert_id: str
    rule_id: str
    rule_name: str
    triggered_at: datetime
    acknowledged_at: datetime | None = None
    severity: AlertSeverity
    trigger: AlertTrigger
    detail: str  # human-readable description of what changed
    current_session_id: str
    previous_session_id: str


class AlertAckRequest(BaseModel):
    acknowledged: bool = True  # set False to un-acknowledge


class TestWebhookRequest(BaseModel):
    url: str = Field(min_length=1)
    secret: str | None = None


class SnapshotMeta(BaseModel):
    """Lightweight metadata for a stored topology snapshot (no full device data)."""

    session_id: str
    discovered_at: datetime
    device_count: int
    link_count: int
    failure_count: int


class PlatformCount(BaseModel):
    """Platform breakdown entry for discovery summary."""

    platform: str
    count: int


class StatusCount(BaseModel):
    """Device status breakdown entry for discovery summary."""

    status: DeviceStatus
    count: int


class FailureReasonCount(BaseModel):
    """Failure reason breakdown entry for discovery summary."""

    reason: str
    count: int


class ProtocolCount(BaseModel):
    """Discovery protocol breakdown for links."""

    protocol: str
    count: int


class DiscoverySummary(BaseModel):
    """Post-discovery dashboard summary with aggregated statistics."""

    session_id: str
    discovered_at: datetime
    # Device counts
    total_devices: int
    ok_devices: int
    placeholder_devices: int
    # Failure counts
    total_failures: int
    failure_breakdown: list[FailureReasonCount] = []
    # Link counts
    total_links: int
    port_channel_links: int
    protocol_breakdown: list[ProtocolCount] = []
    # Breakdowns
    platform_breakdown: list[PlatformCount] = []
    status_breakdown: list[StatusCount] = []
    # Network health indicators
    total_vlans: int = 0
    native_vlan_mismatches: int = 0
    stp_root_bridges: int = 0  # devices that are STP root for at least one VLAN
    # Coverage
    total_interfaces: int = 0
    up_interfaces: int = 0
    down_interfaces: int = 0


class ResolvePlaceholderRequest(BaseModel):
    """Request to manually resolve a placeholder device by assigning an IP for re-discovery."""

    placeholder_device_id: str
    mgmt_ip: str  # IP to assign or re-discover


class SearchHit(BaseModel):
    result_type: str  # 'device', 'interface', 'mac', 'ip', 'vlan', 'route'
    label: str  # primary display text
    detail: str | None = None  # secondary display text
    device_id: str
    session_id: str
    tab: str  # which tab to focus: 'overview', 'interfaces', 'arp', 'mac', 'routes', 'vlans'
    score: float = 0.0


class SearchResponse(BaseModel):
    query: str
    total: int
    results: list[SearchHit]


# ---------------------------------------------------------------------------
# Path trace models
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Advanced Mode models
# ---------------------------------------------------------------------------


class AdvancedStatus(StrEnum):
    SUCCESS = "success"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"
    PARTIAL = "partial"


class PortChange(BaseModel):
    """Record of a single interface VLAN change."""

    interface: str
    field: str  # "access_vlan", "description"
    old_value: str | None = None
    new_value: str | None = None
    verified: bool = False


class VlanChangeRequest(BaseModel):
    """Request to change VLAN assignment on one or more access ports."""

    device_id: str
    device_ip: str
    platform: str | None = None  # "iosxe", "nxos"
    interfaces: list[str] = Field(min_length=1, max_length=48)
    target_vlan: int = Field(ge=1, le=4094)
    description: str | None = None  # optional new port description
    write_memory: bool = False
    # Credentials (session-scoped, not stored)
    username: str
    password: str
    enable_password: str | None = None
    timeout: int = Field(default=30, ge=5, le=120)


class AuditRecord(BaseModel):
    """Immutable record of a VLAN change operation."""

    id: str
    timestamp: datetime
    device_id: str
    device_ip: str
    platform: str | None = None
    operation: str  # "vlan_change", "undo"
    status: AdvancedStatus
    changes: list[PortChange] = []
    commands_sent: list[str] = []
    pre_state: dict[str, str] = {}  # interface -> running-config snippet
    post_state: dict[str, str] = {}
    rollback_commands: list[str] = []
    undo_of: str | None = None  # audit_id this undoes
    undone_by: str | None = None  # audit_id that undid this
    error: str | None = None


class UndoRequest(BaseModel):
    """Credentials for undoing a VLAN change."""

    username: str
    password: str
    enable_password: str | None = None
    timeout: int = Field(default=30, ge=5, le=120)


class AuditExportFormat(StrEnum):
    CSV = "csv"
    JSON = "json"


# ---------------------------------------------------------------------------
# Auth models
# ---------------------------------------------------------------------------


class UserRole(StrEnum):
    ADMIN = "admin"
    OPERATOR = "operator"
    VIEWER = "viewer"


class User(BaseModel):
    id: str
    username: str
    password_hash: str
    role: UserRole = UserRole.VIEWER
    created_at: datetime
    disabled: bool = False


class APIKey(BaseModel):
    id: str
    key_hash: str  # SHA-256 hash of the actual key
    label: str
    user_id: str
    role: UserRole  # inherited from user at creation time
    created_at: datetime
    expires_at: datetime | None = None
    disabled: bool = False


class CreateUserRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=8, max_length=128)
    role: UserRole = UserRole.VIEWER


class CreateAPIKeyRequest(BaseModel):
    label: str = Field(min_length=1, max_length=128)
    expires_in_days: int | None = Field(default=None, ge=1, le=365)


class LoginRequest(BaseModel):
    """Authenticate with username and password to obtain an API token."""

    model_config = ConfigDict(
        json_schema_extra={"examples": [{"username": "admin", "password": "netscope"}]}
    )

    username: str
    password: str


class TokenResponse(BaseModel):
    """Successful authentication response with API token."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "token": "ns_abc123def456",
                    "user_id": "usr-001",
                    "username": "admin",
                    "role": "admin",
                    "expires_at": "2026-04-21T00:00:00Z",
                },
            ]
        }
    )

    token: str
    user_id: str
    username: str
    role: UserRole
    expires_at: datetime | None = None


# ---------------------------------------------------------------------------
# Saved views and annotations
# ---------------------------------------------------------------------------


class NodePosition(BaseModel):
    """Persisted x/y position for a single Cytoscape node."""

    device_id: str
    x: float
    y: float


class AnnotationTarget(StrEnum):
    DEVICE = "device"
    LINK = "link"
    CANVAS = "canvas"


class Annotation(BaseModel):
    """A text note or color highlight attached to a device, link, or canvas position."""

    annotation_id: str
    target_type: AnnotationTarget
    target_id: str  # device_id, "srcId:tgtId" link key, or "" for canvas
    text: str = ""
    color: str = "#f97316"  # highlight color (default: orange)
    x: float | None = None  # canvas position (for canvas annotations)
    y: float | None = None
    created_at: datetime
    updated_at: datetime


class SavedView(BaseModel):
    """A named topology view: layout + filters + annotations."""

    view_id: str
    session_id: str
    name: str
    description: str = ""
    is_default: bool = False
    # Layout state
    zoom: float = 1.0
    pan_x: float = 0.0
    pan_y: float = 0.0
    node_positions: list[NodePosition] = []
    # Filter state
    protocol_filter: str = "all"  # "all", "cdp", "lldp"
    vlan_filter: str | None = None
    # Annotations
    annotations: list[Annotation] = []
    created_at: datetime
    updated_at: datetime


class SavedViewRequest(BaseModel):
    """Request body for creating/updating a saved view."""

    name: str = Field(min_length=1, max_length=200)
    description: str = ""
    is_default: bool = False
    session_id: str
    zoom: float = 1.0
    pan_x: float = 0.0
    pan_y: float = 0.0
    node_positions: list[NodePosition] = []
    protocol_filter: str = "all"
    vlan_filter: str | None = None
    annotations: list[Annotation] = []


class AnnotationRequest(BaseModel):
    """Request body for creating/updating a single annotation."""

    target_type: AnnotationTarget
    target_id: str = ""
    text: str = ""
    color: str = "#f97316"
    x: float | None = None
    y: float | None = None


class PathTraceRequest(BaseModel):
    """Trace the L3 forwarding path between two endpoints."""

    model_config = ConfigDict(
        json_schema_extra={"examples": [{"source": "10.0.0.1", "dest": "10.0.2.1", "vrf": None}]}
    )

    source: str  # source IP or device hostname
    dest: str  # destination IP or device hostname
    vrf: str | None = None  # optional VRF context (Phase 3)


class PathHop(BaseModel):
    hop_number: int
    device_id: str
    hostname: str | None = None
    mgmt_ip: str
    in_interface: str | None = None  # interface traffic arrived on
    out_interface: str | None = None  # interface traffic leaves on
    next_hop_ip: str | None = None  # next-hop gateway IP (None when at destination)


class PathTraceResult(BaseModel):
    session_id: str
    source: str
    dest: str
    success: bool
    hops: list[PathHop] = []
    node_ids: list[str] = []  # device IDs for frontend highlighting
    link_keys: list[str] = []  # "src_id:tgt_id" pairs for edge highlighting
    error: str | None = None  # human-readable error message
    # "no_route", "no_arp", "device_not_discovered", "loop", "max_hops"
    break_reason: str | None = None
