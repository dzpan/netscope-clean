# Changelog

All notable changes to NetScope are documented in this file.

## [1.0.1] — 2026-03-22

### Bug Fixes

- Fix integer validation error when running discovery (NET-133)
- Fix `[object Object]` error banner by normalizing FastAPI error details (NET-128)
- Fix SNMP credential auth type tabs overflow in sidebar (NET-123, NET-126)
- Fix legend collapse leaving 8px gap (NET-124)
- Fix topology graph nodes unreadable in dark theme (NET-123)
- Fix missing platform for Cisco C1200/CBS switches (NET-120)
- Fix Summary and VLAN Map tabs both appearing active simultaneously (NET-119)
- Fix health endpoint reporting stale version `0.1.0` instead of `1.0.0`

### Enhancements

- Add interfaces, VLANs, ARP, MAC, routes, and trunks to Excel/CSV exports (NET-127)
- Add credential set support to config dump (NET-125)
- Add failure reason tooltip on placeholder device status badges (NET-121)
- Normalize hostname sorting and add display case option (NET-122)
- Wrap discovery inputs in a `<form>` element for better semantics (NET-116)
- Add collapsible left sidebar with toggle button (NET-115)
- Persist discovery form state across page reloads (NET-118)
- Add undo toast when removing credential sets (NET-117)
- Add up/down reordering controls for credential sets (NET-114)
- Add SNMP credential support to credential sets (NET-113)
- Add SSH key authentication support to credential sets (NET-112)
- Add password visibility toggle for credential fields (NET-111)
- Add seed IP and CIDR scope validation (NET-107, NET-108)
- Add visual validation and clamping for number inputs (NET-109)
- Add accessible labels to all form inputs (NET-106)
- Fix topology link label overlap with split labels and display toggle (NET-101)
- Make device detail panel resizable with better table layout (NET-99)
- Add per-tab data table export, sort, filter, and copy (NET-102)
- Add dark/light theme toggle with CSS variable architecture (NET-96)
- Add PWA manifest for installable app experience (NET-100)
- Add discovery summary dashboard and placeholder device resolution (NET-105)
- Add aria-labels to form inputs missing accessibility labels (NET-98)
- Fix ARP/MAC/Routes table column truncation in device panel (NET-97)
- Group export buttons into dropdown menu (NET-104)
- Make topology legend collapsible to prevent map overlap (NET-103)
- Fix SSE discovery stream hanging after BFS completes (NET-95)

## [1.0.0] — 2026-03-21

First stable release. NetScope provides SSH-based network topology intelligence for Cisco networks with auto-discovery, deep data collection, write operations, and a modern Vue 3 frontend.

### Core Platform

- **BFS topology discovery** via CDP and LLDP from seed IPs (NET-3, NET-72)
- **Multi-credential rotation** — tries credential sets in order per device (NET-3)
- **Dual-protocol discovery** — CDP + LLDP combined or independent (NET-72)
- **Unified CLI parser module** — regex-based parsing for all Cisco show commands (NET-4)
- **Collection profiles** — minimal, standard, full, and custom command sets (NET-6)
- **SQLite persistence** with in-memory LRU fallback (NET-8)
- **Graceful failure handling** — partial results, retry, and progress reporting (NET-76)

### Multi-Vendor Support

- **Cisco IOS-XE** (Catalyst 9000, ISR) — full discovery and data collection
- **Cisco NX-OS** (Nexus 9000) — full support including VXLAN/EVPN
- **Cisco CBS / C1200 Small Business** — CDP discovery, VLAN/ARP/MAC collection (NET-44)
- **Multi-vendor LLDP parser variants** with TLV extensions (NET-73)
- **Multi-vendor parser framework** — plugin architecture, Arista EOS support, template engine, SNMP fallback (NET-83)

### Data Collection

- Version, hostname, platform, serial, OS, uptime
- CDP and LLDP neighbor details for topology links
- Interface status, speed, VLAN assignment, IP addresses
- VLAN database (ID, name, status)
- ARP table (IP-to-MAC mappings)
- MAC address table (MAC-to-port mappings)
- Routing table with protocol, destination, and next-hop (NET-45)
- STP per-VLAN root bridge, port roles, and states
- EtherChannel summary (port-channels, members, protocol)
- VXLAN NVE peers, VNI mappings, BGP L2VPN EVPN summary
- On-demand running-config collection
- Trunk native VLAN collection and mismatch detection (NET-35)

### Frontend & Visualization

- **Vue 3 + Cytoscape.js** interactive topology graph (NET-9, NET-10)
- **NetScope design system** — gray/orange theme, full UI redesign (NET-41)
- **Device detail panels** with tabbed data views (NET-9)
- **Network-wide VLAN map** — cross-device summary at a glance (NET-10)
- **STP root bridge visualization** and blocked port highlighting (NET-10)
- **STP root per-VLAN summary panel** in topology view (NET-36)
- **Port-channel link collapse** — member links merged into single labeled edge (NET-37)
- **L3 path trace** — backend engine, API, and frontend UI (NET-38)
- **Resizable column widths** on all data tables (NET-43)
- **Resizable bottom drawer and right sidebar panels** (NET-46)
- **LLDP frontend** — protocol filter, badges, detail panel, search (NET-74)
- **Help panel** with accordion guide (NET-56)
- **Saved views** for custom topology layouts

### Advanced Mode (Write Operations)

- **VLAN port assignment changes** directly from the UI (NET-51, NET-52)
- **In-app password prompt** — no environment variable needed to enable (NET-50)
- **Playbook system** — library, editor, execute modal, execution history (NET-60)
- **Playbook templates** — VLAN change, configure replace, config diff, custom commands (NET-65, NET-66)
- **YAML parse error feedback** and config diff display (NET-67)
- **Immutable audit log** with CSV/JSON export and undo capability
- **Safety guardrails** — protected interfaces, trunk lock, port-channel lock, VLAN existence check, max-port limit, device-level locking, auto-rollback on verification failure
- **Production hardening** — undo handlers with credentials, backend engine tests (NET-64, NET-66)

### Monitoring & Change Detection

- **Scheduled re-discovery** with topology diff (NET-17)
- **Change detection alerts** and webhook notifications (NET-18)
- **Historical snapshot browser** with timeline navigation (NET-19)
- **Alert rules & webhook management UI** (NET-81)
- **Settings UI** — frontend configuration panel + backend API (NET-80)

### Search & Data Access

- **Full-text search** across all collected network data (NET-20)
- **OpenAPI / Swagger docs** with `/api/v1` versioning prefix (NET-84)

### Security & Authentication

- **API authentication** with RBAC groundwork (NET-75)
- **SSH credential encryption** at rest (NET-75)
- **First-run setup wizard** for guided onboarding (NET-79)

### Export Formats

- DrawIO (editable diagrams for draw.io / diagrams.net)
- Excel (multi-sheet workbook with all device data)
- CSV (zip archive with devices, links, interfaces)
- DOT (Graphviz format)
- SVG (vector graphic via Graphviz)
- JSON (full session data)

### Operations & Deployment

- **Docker multi-stage build** with health check (NET-13)
- **Docker Compose** production configuration (NET-22)
- **Production deployment guide** — reverse proxy, systemd, TLS (NET-22)
- **`bin/netscope` CLI** management script (NET-16)
- **Structured JSON logging** with configurable levels (NET-78)
- **Enhanced `/health` endpoint** and `/logs` API (NET-78)
- **Database backup/restore** and session import/export (NET-82)
- **SQLite schema migration framework** (NET-87)

### Code Quality

- **ruff + mypy --strict** clean pass on all backend code (NET-14)
- **Frontend Vite build pipeline** with static serving from backend (NET-15)
- **Integration tests** for Advanced Mode contracts (NET-53)
- **E2E test fixes** for MAC format and VLAN type mismatches (NET-77)

### Product Website

- **netscope.dev** landing page with interactive topology demo (NET-21)
- Features, use-cases, and documentation pages (NET-24)
- Per-page SEO metadata and static export config (NET-21)
