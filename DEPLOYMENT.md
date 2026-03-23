# NetScope Deployment Guide

The definitive guide for running NetScope in production.

## 1. Quick Start

```bash
git clone https://github.com/paperclipai/netscope.git
cd netscope
docker compose up -d
# Open http://localhost:8000
```

That's it. No configuration needed.

## 2. System Requirements

| Resource | Minimum | Recommended |
|----------|---------|-------------|
| CPU | 1 core | 2 cores |
| RAM | 512 MB | 1 GB |
| Disk | 500 MB | 1 GB |
| Docker | Engine 24.0+ with Compose v2 | Latest stable |

**Network requirements:**
- Outbound TCP/22 from the container to target network devices (SSH)
- No inbound ports needed from network devices
- Container must have L3 reachability to management IPs of Cisco devices

## 3. Configuration Reference

All variables use the `NETSCOPE_` prefix. Set them in `docker-compose.yml`, a `.env` file, or pass via `-e` flags.

| Variable | Default | Description |
|----------|---------|-------------|
| `NETSCOPE_LOG_LEVEL` | `info` | Logging verbosity: `debug`, `info`, `warning`, `error`, `critical` |
| `NETSCOPE_DEBUG` | `false` | Enable OpenAPI docs at `/api/docs` |
| `NETSCOPE_MAX_SESSIONS` | `50` | Max concurrent topology sessions (1-1000) |
| `NETSCOPE_STATIC_DIR` | `frontend/dist` | Path to built Vue frontend assets |
| `NETSCOPE_CORS_ORIGINS` | `["http://localhost:5173","http://localhost:8000"]` | Allowed CORS origins (JSON array) |
| `NETSCOPE_DB_PATH` | *(unset)* | SQLite path for persistence. Unset = in-memory LRU |
| `NETSCOPE_REDISCOVERY_INTERVAL` | `0` | Auto re-discovery interval in seconds (0 = disabled, requires `DB_PATH`) |
| `NETSCOPE_SNAPSHOT_RETENTION_DAYS` | `90` | Delete snapshots older than N days (0 = keep forever) |

See `.env.example` for a copy-ready template.

## 4. Production Deployment

### 4a. Standalone Docker (small networks, labs)

The default `docker-compose.yml` is production-ready for networks under 200 devices:

```bash
docker compose up -d
```

Data persists in the `netscope-data` Docker volume (SQLite at `/data/netscope.db`).

### 4b. Hardened Production

Use the production override for resource limits, security hardening, and log rotation:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

This adds:
- CPU/memory limits (2 CPU, 1 GB RAM)
- Read-only root filesystem
- Dropped Linux capabilities (only `NET_RAW` retained for SSH)
- `no-new-privileges` security option
- JSON log rotation (10 MB max, 3 files)

### 4c. Behind Reverse Proxy (recommended for production)

**Nginx example** (save as `/etc/nginx/conf.d/netscope.conf`):

```nginx
server {
    listen 443 ssl http2;
    server_name netscope.example.com;

    ssl_certificate     /etc/ssl/certs/netscope.pem;
    ssl_certificate_key /etc/ssl/private/netscope.key;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # WebSocket support (for future SSE/WS features)
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }

    # Rate limiting
    limit_req_zone $binary_remote_addr zone=netscope:10m rate=30r/m;
    limit_req zone=netscope burst=10 nodelay;
}
```

**Caddy example** (simpler, auto-HTTPS):

```
netscope.example.com {
    reverse_proxy localhost:8000
}
```

### 4d. Bare Metal (no Docker)

```bash
# 1. Clone and install
git clone https://github.com/paperclipai/netscope.git
cd netscope
python3.11 -m venv .venv
source .venv/bin/activate
pip install .

# 2. Build frontend
cd frontend && npm ci && npm run build && cd ..

# 3. Run
uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

**systemd unit** (save as `/etc/systemd/system/netscope.service`):

```ini
[Unit]
Description=NetScope Network Topology Intelligence
After=network.target

[Service]
Type=simple
User=netscope
Group=netscope
WorkingDirectory=/opt/netscope
Environment=NETSCOPE_DB_PATH=/opt/netscope/data/netscope.db
Environment=NETSCOPE_LOG_LEVEL=info
ExecStart=/opt/netscope/.venv/bin/uvicorn backend.main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now netscope
```

## 5. Security Hardening

- **Non-root container**: The Docker image runs as an unprivileged `app` user
- **SSH credentials**: Never stored on disk — held in-memory only during active discovery sessions
- **Network segmentation**: Run NetScope in your management VLAN/subnet with access to device management IPs
- **TLS**: Always use a reverse proxy with HTTPS in production (see section 4c)
- **Read-only filesystem**: Use `docker-compose.prod.yml` for a read-only root filesystem
- **Capabilities**: Production overlay drops all Linux capabilities except `NET_RAW` (needed for SSH connections)

## 6. Persistence & Backups

When `NETSCOPE_DB_PATH` is set, NetScope stores all session data in SQLite.

**Docker volume location:**
```bash
docker volume inspect netscope-data
```

**Backup:**
```bash
docker compose exec netscope cp /data/netscope.db /data/netscope.db.bak
# Or from the host:
docker cp netscope:/data/netscope.db ./netscope-backup.db
```

**Restore:**
```bash
docker cp ./netscope-backup.db netscope:/data/netscope.db
docker compose restart
```

When `NETSCOPE_DB_PATH` is unset, sessions are stored in an in-memory LRU cache (lost on restart).

## 7. Monitoring & Health

**Health endpoint:**
```bash
curl http://localhost:8000/health
# {"status":"ok","version":"0.1.0"}
```

**Docker health check** is built into the image (30s interval, 5s timeout, 3 retries). Check status:
```bash
docker compose ps    # STATUS column shows "healthy"
docker inspect --format='{{.State.Health.Status}}' netscope
```

**Logs:**
```bash
docker compose logs -f            # Follow logs
docker compose logs --tail=100    # Last 100 lines
```

## 8. Upgrading

```bash
docker compose pull           # Pull latest image (if using registry)
# Or rebuild from source:
docker compose build --no-cache
docker compose up -d
```

- SQLite schema is forward-compatible — no manual migrations needed
- Check release notes for breaking changes before major version upgrades
- **Rollback**: restore the database backup from section 6, then `docker compose up -d` with the previous image

## 9. Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| Container starts but UI doesn't load | Frontend assets not built | Rebuild: `docker compose build --no-cache` |
| "Connection refused" on port 8000 | Container not running or port conflict | `docker compose ps` to check status |
| Discovery times out | Container can't reach devices via SSH | `docker exec netscope python -c "import socket; socket.create_connection(('DEVICE_IP', 22), 5)"` |
| SSH auth failures | Wrong credentials | Verify creds from host first: `ssh user@device` |
| Container keeps restarting | Application crash — check logs | `docker compose logs --tail=50` |
| High memory during discovery | Too many concurrent SSH sessions | Lower `NETSCOPE_MAX_SESSIONS` |
| SQLite "database locked" | Concurrent write contention | Normal under heavy load — retries automatically |

## 10. Platform-Specific Notes

### Linux
- Docker Engine (not Docker Desktop) recommended for servers
- Add your user to the `docker` group: `sudo usermod -aG docker $USER`
- If using UFW, allow Docker bridge: `sudo ufw allow in on docker0`
- For host-network SSH access: add `network_mode: host` to compose

### macOS
- Docker Desktop required
- If network devices are on the local LAN, you may need `host.docker.internal` routing or `network_mode: host` (limited on macOS)

### Windows
- Docker Desktop with WSL2 backend recommended
- Use named volumes (not bind mounts) for best performance
- Windows Defender may slow builds — add a Docker exclusion
