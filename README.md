# NetScope

**SSH-based network topology intelligence for Cisco networks.**

NetScope auto-discovers your network topology via CDP/LLDP over SSH, collects deep operational data from every device, and presents it as an interactive, exportable map. No SNMP. No agents. No cloud.

## Features

### Discovery & Data Collection
- **Auto-discovery** — BFS topology crawl from seed IPs via CDP and LLDP (dual-protocol)
- **Multi-credential** — Try multiple credential sets per device with automatic retry
- **Multi-vendor** — Cisco IOS-XE, NX-OS, CBS/C1200; Arista EOS via plugin framework; SNMP fallback
- **Deep data collection** — Interfaces, VLANs, ARP, MAC, routing, STP, EtherChannel, VXLAN/EVPN, running configs
- **Collection profiles** — Minimal, standard, full, or custom command sets per discovery
- **Graceful failures** — Partial results on device errors, automatic retry with progress reporting

### Visualization & UI
- **Interactive topology** — Vue 3 + Cytoscape.js graph with click-to-explore device panels
- **STP visualization** — Root bridge indicators, blocked port highlighting, per-VLAN summary
- **Network-wide VLAN map** — Cross-device VLAN summary with trunk native VLAN mismatch detection
- **L3 path trace** — Trace routing paths between devices with visual overlay
- **Port-channel collapse** — EtherChannel member links merged into single labeled edges
- **Resizable panels** — Bottom drawer, right sidebar, and column widths all adjustable
- **Design system** — Clean gray/orange theme across all components

### Write Operations (Advanced Mode)
- **VLAN changes** — Reassign access port VLANs directly from the UI with safety guardrails
- **Playbook system** — Library, editor, execution, and history for custom command playbooks
- **Immutable audit log** — Every change recorded with undo capability and CSV/JSON export
- **Auto-rollback** — Verification failure triggers automatic rollback to previous state

### Monitoring & Change Detection
- **Scheduled re-discovery** — Periodic topology refresh with automatic diff
- **Change detection alerts** — Webhook notifications when topology or config changes
- **Historical snapshots** — Timeline browser to compare network state over time
- **Alert rules UI** — Configure alert rules and webhook targets from the frontend

### Search, Export & API
- **Full-text search** — Search across all collected network data
- **Export everything** — DrawIO, Excel, CSV, JSON, DOT, SVG
- **OpenAPI docs** — Swagger UI at `/api/v1/docs` with versioned API prefix
- **Config dumps** — On-demand `show running-config` per device

### Security & Operations
- **API authentication** — Token-based auth with RBAC groundwork
- **SSH credential encryption** — Credentials encrypted at rest in SQLite
- **First-run setup wizard** — Guided onboarding for new installations
- **Settings UI** — Frontend configuration panel for all runtime settings
- **Database backup/restore** — Full backup and session import/export
- **Structured logging** — JSON logging with `/health` and `/logs` endpoints
- **Schema migrations** — Lightweight SQLite migration framework
- **Cross-platform** — Docker or bare metal on Windows, Linux, macOS

## Quick Start

### Docker (recommended)

```bash
git clone https://github.com/paperclipai/netscope.git
cd netscope
docker compose up -d
```

Open `http://localhost:8000` in your browser. The setup wizard guides you through initial configuration on first launch. The container includes a health check — verify with `docker compose ps` (STATUS: healthy).

To enable API authentication:

```bash
NETSCOPE_AUTH_ENABLED=true NETSCOPE_SECRET_KEY=your-secret-key docker compose up -d
```

For production hardening, reverse proxy setup, and bare-metal systemd deployment, see **[DEPLOYMENT.md](DEPLOYMENT.md)**.

### Bare Metal

```bash
# Backend
python3 -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows
pip install -e ".[dev]"
uvicorn backend.main:app --reload --port 8000

# Frontend (separate terminal)
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173` (Vite dev server proxies API to `:8000`).

### First Discovery

1. Enter a seed IP address (any device with CDP or LLDP enabled)
2. Provide SSH credentials
3. Set the scope (CIDR, IP range, or leave open)
4. Click **Discover**

NetScope will BFS-crawl the network, collecting data from each reachable device, and render the topology graph.

## Architecture

```
┌──────────────────────────────────────────────────┐
│                   Frontend                        │
│   Vue 3 + Vite + Tailwind CSS + Cytoscape.js     │
│   TopologyGraph · DevicePanel · DiscoverForm      │
│   SetupWizard · SettingsPanel · AlertsPanel       │
│   PlaybookLibrary · SavedViews · ExportBar        │
└──────────────────┬───────────────────────────────┘
                   │ REST API (/api/v1)
┌──────────────────┴───────────────────────────────┐
│                   Backend                         │
│   FastAPI (async) + Pydantic v2                   │
│                                                   │
│   discovery.py    BFS engine + credential rotation│
│   parsers.py      Regex parsers for Cisco CLI     │
│   normalizer.py   Link dedup + placeholders       │
│   export.py       DrawIO, Excel, CSV, DOT, SVG    │
│   store.py        In-memory LRU / SQLite          │
│   auth.py         Token auth + RBAC + API keys    │
│   alerts.py       Alert rules + webhook dispatch  │
│   scheduler.py    Re-discovery + snapshot diffs    │
│   vendors/        Multi-vendor plugin framework    │
│   migrations.py   SQLite schema migrations         │
│   playbooks.py    Playbook engine + templates      │
└──────────────────┬───────────────────────────────┘
                   │ SSH (AsyncSSH + Scrapli) / SNMP
┌──────────────────┴───────────────────────────────┐
│              Network Devices                      │
│   Cisco IOS-XE · NX-OS · CBS/C1200 · Arista EOS  │
│   CDP/LLDP neighbors → BFS crawl                  │
└──────────────────────────────────────────────────┘
```

## Supported Platforms

| Platform | Discovery | Data Collection | Notes |
|----------|-----------|-----------------|-------|
| Cisco IOS-XE (Catalyst 9000, ISR) | CDP, LLDP | Full | Primary target |
| Cisco NX-OS (Nexus 9000) | CDP, LLDP | Full | VXLAN/EVPN support |
| Cisco CBS / C1200 Small Business | CDP | Partial | `terminal datadump` pagination |
| Arista EOS | LLDP | Via plugin | YAML template-based vendor plugin |
| Other vendors | SNMP fallback | Basic | sysDescr, interfaces, ARP, MAC via SNMP |

## Data Collected Per Device

| Category | Commands | Parser |
|----------|----------|--------|
| Version/Identity | `show version` | Hostname, platform, serial, OS, uptime |
| Neighbors | `show cdp neighbors detail`, `show lldp neighbors detail` | Topology links |
| Interfaces | `show interfaces status`, `show ip interface brief` | Port status, speed, VLAN, IP |
| VLANs | `show vlan brief` | VLAN ID, name, status |
| ARP | `show ip arp` | IP-to-MAC mappings |
| MAC Table | `show mac address-table` | MAC-to-port mappings |
| Routing | `show ip route` | Protocol, destination, next-hop |
| STP | `show spanning-tree` | Per-VLAN root, port roles/states |
| EtherChannel | `show etherchannel summary` | Port-channels, members, protocol |
| VXLAN | `show nve peers`, `show nve vni`, `show bgp l2vpn evpn summary` | NVE peers, VNI mappings, EVPN |
| Config | `show running-config` (on-demand) | Full device configuration |

## Advanced Mode (Write Operations)

Advanced Mode enables safe VLAN port assignment changes directly from the NetScope UI. It is disabled by default and must be explicitly enabled via environment variable.

### How It Works

1. **Toggle** — Enable Advanced Mode via the orange toggle in the top bar (shows a confirmation warning)
2. **Select ports** — In the Device Panel, check access ports to change
3. **Pick VLAN** — Choose target VLAN, optionally set port description and write-memory
4. **Review** — Preview the exact IOS/NX-OS commands before execution
5. **Execute** — 4-step process: Connect → Pre-check → Apply → Post-check
6. **Audit** — Every change is logged immutably. Undo any change from the audit log.

### Safety Guardrails

- Protected interfaces blocked: Vlan, Loopback, mgmt, port-channel, nve, tunnel
- Trunk ports and port-channel members cannot be modified
- Target VLAN must exist on the device
- Max ports per change is configurable (default 48)
- One concurrent change per device (locked)
- Auto-rollback if post-check verification fails
- All operations produce immutable audit records

### API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/advanced/status` | Check if Advanced Mode is enabled and its config |
| `POST` | `/advanced/vlan-change` | Execute VLAN change on selected ports |
| `GET` | `/advanced/audit` | List audit records (paginated, filterable by device) |
| `GET` | `/advanced/audit/{id}` | Get single audit record with full detail |
| `GET` | `/advanced/audit/export?format=csv` | Export audit log as CSV or JSON |
| `POST` | `/advanced/audit/{id}/undo` | Undo a previous change using stored rollback commands |

## Configuration

All environment variables use the `NETSCOPE_` prefix:

| Variable | Default | Description |
|----------|---------|-------------|
| **General** | | |
| `NETSCOPE_LOG_LEVEL` | `info` | Log level: debug, info, warning, error, critical |
| `NETSCOPE_DB_PATH` | *(none)* | SQLite database path. If unset, uses in-memory LRU |
| `NETSCOPE_MAX_SESSIONS` | `50` | Max sessions in LRU cache (in-memory mode only) |
| `NETSCOPE_DEBUG` | `false` | Enable Swagger docs at `/api/v1/docs` |
| `NETSCOPE_CORS_ORIGINS` | `["*"]` | JSON array of allowed CORS origins |
| `NETSCOPE_STATIC_DIR` | `frontend/dist` | Path to built frontend assets |
| **Authentication** | | |
| `NETSCOPE_AUTH_ENABLED` | `false` | Require token auth on all API endpoints |
| `NETSCOPE_SECRET_KEY` | *(none)* | Master key for Fernet encryption + token signing |
| `NETSCOPE_DEFAULT_ADMIN_PASSWORD` | *(none)* | Bootstrap admin user on first startup |
| **Scheduling** | | |
| `NETSCOPE_REDISCOVERY_INTERVAL` | `0` | Auto re-discovery interval in seconds (0 = disabled) |
| `NETSCOPE_SNAPSHOT_RETENTION_DAYS` | `90` | Purge snapshots older than N days (0 = keep forever) |
| **Advanced Mode** | | |
| `NETSCOPE_ALLOW_ADVANCED` | `false` | Enable Advanced Mode (write operations) |
| `NETSCOPE_ADVANCED_PASSWORD` | *(none)* | Password to unlock Advanced Mode in UI |
| `NETSCOPE_ADVANCED_REQUIRE_WRITE_MEM` | `false` | Force write-memory on every change |
| `NETSCOPE_ADVANCED_MAX_PORTS_PER_CHANGE` | `48` | Max ports per single VLAN change (1–96) |
| `NETSCOPE_AUDIT_RETENTION_DAYS` | `90` | Purge audit records older than N days (0 = keep forever) |
| **Playbooks** | | |
| `NETSCOPE_PLAYBOOK_MAX_TARGETS` | `10` | Max devices per playbook execution (1–100) |
| `NETSCOPE_PLAYBOOK_BLOCKED_COMMANDS` | *(defaults)* | Comma-separated blocked commands |
| `NETSCOPE_PLAYBOOK_REQUIRE_DRY_RUN` | `true` | Require dry-run before live execution |

## Development

```bash
# Lint
ruff check backend/
ruff format backend/ --check

# Type check
mypy backend/

# Test
pytest -v
pytest tests/test_parsers.py -k "test_cdp"  # single test

# Frontend dev
cd frontend && npm run dev
```

## Export Formats

| Format | Endpoint | Description |
|--------|----------|-------------|
| DrawIO | `GET /export/{session_id}/drawio` | Editable diagram for draw.io/diagrams.net |
| Excel | `GET /export/{session_id}/excel` | Multi-sheet workbook with all device data |
| CSV | `GET /export/{session_id}/csv` | Zip archive with devices, links, interfaces |
| DOT | `GET /export/{session_id}/dot` | Graphviz DOT format |
| SVG | `GET /export/{session_id}/svg` | Vector graphic (requires Graphviz `dot`) |
| JSON | `GET /sessions/{session_id}` | Full session data as JSON |

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Backend | Python 3.11+, FastAPI, async |
| SSH | Scrapli + AsyncSSH |
| SNMP | PySNMP (fallback for non-SSH devices) |
| Data models | Pydantic v2 |
| Auth | Fernet encryption, JWT tokens, API keys |
| Frontend | Vue 3, Cytoscape.js, Tailwind CSS, Vite |
| Parsing | Pure regex + YAML templates (vendor plugins) |
| Export | openpyxl, DrawIO XML, Graphviz DOT |
| Persistence | SQLite with migrations, or in-memory LRU |
| Deployment | Docker multi-stage, docker-compose |

## License

MIT
