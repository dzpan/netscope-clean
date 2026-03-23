# NetScope Design System

> Version 1.0 · Gray/Orange Theme · Dark-mode-first

The NetScope design system defines the visual identity for the application. Gray is the foundation. Orange is the signal. Everything else follows from that principle.

---

## Color Palette

### Gray Foundation

| Token | Hex | Usage |
|-------|-----|-------|
| `--gray-950` | `#0a0a0f` | App background (deepest surface) |
| `--gray-900` | `#111118` | Primary surface — sidebar, topbar, main panels |
| `--gray-850` | `#18181f` | Elevated surface — cards, modals |
| `--gray-800` | `#1f1f28` | Secondary surface — table row alt, hover states |
| `--gray-750` | `#252530` | Subtle hover on cards |
| `--gray-700` | `#2a2a35` | Borders, dividers, subtle separators |
| `--gray-600` | `#3a3a48` | Disabled elements, inactive borders |
| `--gray-500` | `#5a5a6a` | Placeholder text, muted labels |
| `--gray-400` | `#7a7a8a` | Secondary text, timestamps, metadata |
| `--gray-300` | `#9a9aaa` | Body text on dark backgrounds |
| `--gray-200` | `#bababc` | Primary text — tables, descriptions |
| `--gray-100` | `#e0e0e4` | Headings, important labels |
| `--gray-50`  | `#f0f0f2` | Bright text, active items, emphasis |

### Orange Accent

| Token | Hex | Usage |
|-------|-----|-------|
| `--orange-700` | `#c2410c` | Dark accent for badges on light backgrounds |
| `--orange-600` | `#ea580c` | Pressed/click state |
| `--orange-500` | `#f97316` | **Primary accent** — buttons, active states, links |
| `--orange-400` | `#fb923c` | Hover states, lighter accent |
| `--orange-300` | `#fdba74` | Selected items, active borders |
| `--orange-100` | `#ffedd5` | Subtle orange tint for highlighted rows |
| `--orange-glow` | `rgba(249,115,22,0.15)` | Glow for active topology nodes |

### Semantic / Status Colors

| Token | Hex | Usage |
|-------|-----|-------|
| `--status-up`      | `#22c55e` | Device up, interface up, discovery complete |
| `--status-down`    | `#ef4444` | Device unreachable, interface down, errors |
| `--status-warning` | `#f97316` | Warnings, partial failures (reuses orange) |
| `--status-info`    | `#94a3b8` | Informational, neutral status |
| `--status-unknown` | `#6b7280` | Placeholder devices, pending discovery |

### Usage Rules

- **Never pure black** (#000) for backgrounds. Minimum `--gray-950`.
- **Orange is the signal** — use sparingly. Orange loses power when overused.
- **Orange used for**: primary buttons, active tab indicators, selected device highlights, link hovers, progress bars, the NetScope logo accent, notification badges.
- **Orange never used for**: large background fills, body text, status-up indicators, decorative borders.
- **No rogue blues, teals, or purples** in the primary UI.

---

## Typography

| Token | Value | Usage |
|-------|-------|-------|
| `--font-display` | `Space Grotesk, sans-serif` | Headings, panel titles, device hostnames |
| `--font-body` | `Inter, sans-serif` | Body text, descriptions, form labels |
| `--font-mono` | `JetBrains Mono, monospace` | CLI output, IPs, MACs, interfaces, config dumps |

### Font Sizes

| Token | Value | Usage |
|-------|-------|-------|
| `--text-xs` | 12px | Timestamps, metadata, table footnotes |
| `--text-sm` | 13px | Table cells, secondary labels, status tags |
| `--text-base` | 14px | Primary body text (dashboard density) |
| `--text-lg` | 16px | Panel headings, section titles |
| `--text-xl` | 20px | Page headings |
| `--text-2xl` | 24px | Main header |

### Monospace Rule

**All network data MUST use monospace font** (`font-mono` / `JetBrains Mono`):
- IP addresses
- MAC addresses
- Interface names (Gi0/0, Te1/1/1, etc.)
- VLAN IDs when displayed as data
- Serial numbers
- Session IDs
- CLI command output
- Config dumps

This is a network tool — the data should look like it came from a terminal.

---

## Spacing & Layout

| Token | Value | Usage |
|-------|-------|-------|
| `--panel-padding` | 16px | Consistent padding inside all panels |
| `--cell-padding` | 8px 12px | Table cell padding |
| `--panel-gap` | 12px | Gap between panels |
| `--sidebar-width` | 280px | Expanded sidebar |
| `--sidebar-collapsed` | 56px | Icon-only sidebar |
| `--topbar-height` | 48px | Top bar height |
| `--statusbar-height` | 28px | Status/bottom bar height |

---

## Border Radius

| Token | Value | Usage |
|-------|-------|-------|
| `--radius-none` | 0 | Tables (sharp edges for data density) |
| `--radius-sm` | 4px | Buttons, inputs, small tags |
| `--radius-md` | 6px | Cards, panels, modals |
| `--radius-lg` | 8px | Large containers, topology panel |

---

## Shadows & Depth

Depth is communicated primarily through surface color stepping (`gray-900` → `gray-850` → `gray-800`), not shadows. Shadows should be darker/more opaque than light-theme conventions.

| Token | Value | Usage |
|-------|-------|-------|
| `--shadow-sm` | `0 1px 2px rgba(0,0,0,0.3)` | Buttons, tags |
| `--shadow-md` | `0 4px 12px rgba(0,0,0,0.4)` | Floating panels, dropdowns |
| `--shadow-lg` | `0 8px 24px rgba(0,0,0,0.5)` | Modals, overlays |
| `--shadow-glow` | `0 0 12px rgba(249,115,22,0.25)` | Orange glow on focus/active |

---

## Component Library

### Atoms

#### Button

```html
<!-- Primary (orange) -->
<button class="btn-primary">Start Discovery</button>
<button class="btn-primary btn-sm">Save</button>
<button class="btn-primary btn-lg">Export</button>

<!-- Secondary (gray) -->
<button class="btn-secondary">Cancel</button>

<!-- Ghost (transparent) -->
<button class="btn-ghost">Settings</button>

<!-- Danger (red) -->
<button class="btn-danger">Delete Session</button>
```

States: `disabled` attribute for disabled state (opacity-40, cursor-not-allowed).

#### Input

```html
<input class="input" type="text" placeholder="10.1.1.1" />
<input class="input-sm" type="text" placeholder="username" />
<label class="label">Seed Device IP</label>
```

Focus state: orange ring + orange border.

#### Select

```html
<select class="select">
  <option>Minimal</option>
  <option>Standard</option>
</select>
```

#### Badge

```html
<span class="badge badge-up">up</span>
<span class="badge badge-down">down</span>
<span class="badge badge-warning">degraded</span>
<span class="badge badge-info">info</span>
<span class="badge badge-orange">42 alerts</span>
```

#### Status Dot

```html
<span class="status-dot status-dot-up"></span>
<span class="status-dot status-dot-down"></span>
<span class="status-dot status-dot-warning"></span>
<span class="status-dot status-dot-unknown"></span>
```

Always pair status dots with text or icon — never rely on color alone.

#### Tag (removable chip)

```html
<span class="tag">10.1.1.1 <button>×</button></span>
```

---

### Molecules

#### Data Table

```html
<table class="data-table">
  <thead>
    <tr>
      <th>Interface</th>
      <th>Status</th>
      <th>IP</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td class="mono">Gi0/0/1</td>
      <td><span class="status-dot status-dot-up"></span> up</td>
      <td class="mono">10.1.1.1</td>
    </tr>
  </tbody>
</table>
```

Table rules:
- `--radius-none` — no rounded corners on tables
- Alternating rows: `gray-900` / `gray-900/50`
- Row hover: `gray-800`
- Selected row: orange left border + `orange-950/30` background
- Header: `gray-800` bg, `gray-400` text, uppercase, tracking-wide
- All technical values in `.mono` cell class

#### Tab Bar

```html
<div class="tab-bar">
  <button class="tab-item active">Interfaces</button>
  <button class="tab-item">VLANs</button>
  <button class="tab-item">Routes</button>
</div>
```

Active tab: `text-orange-400`, `border-b-orange-500`.

#### Progress Bar

```html
<div class="progress-track">
  <div class="progress-fill" :style="{ width: progress + '%' }"></div>
</div>
```

Orange fill on gray track.

---

### Organisms

#### Top Bar (48px, gray-900)

Contains: NetScope logo (orange accent), session badge (mono), backend status dot, search input, export controls, action buttons.

Logo wordmark: `Net` in `gray-50`, `Scope` in `orange-500`, Space Grotesk font.

#### Sidebar (280px expanded, 56px collapsed, gray-900)

Navigation items use `.nav-item`. Active item: orange left border + orange text + subtle orange background.

#### Topology Panel

Cytoscape.js container with:
- Background: `gray-950`
- Nodes: `gray-800` fill, `gray-600` border, `gray-50` labels in JetBrains Mono
- Selected node: `orange-500` border + glow
- Edges: `gray-600` lines
- Selected edges: `orange-500` lines
- Controls overlay: top-right, gray-800 buttons
- STP blocked: red dashed edges
- Placeholder devices: dashed gray border

#### Device Detail Panel

Header shows: status dot, hostname (mono, large), platform (gray-400), IP/serial/version/uptime (mono, small).

Tabs use `.tab-bar` with orange active indicator. 10 tabs: Overview, Interfaces, VLANs, Neighbors, ARP, MAC, Routes, EtherChannel, STP, Config.

---

## Topology Theme (Cytoscape.js)

```json
{
  "node": {
    "background-color": "#1f1f28",
    "border-color": "#3a3a48",
    "border-width": 2,
    "color": "#f0f0f2",
    "font-family": "JetBrains Mono, monospace",
    "font-size": "11px",
    "shape": "round-rectangle",
    "width": 40,
    "height": 40
  },
  "node:selected": {
    "border-color": "#f97316",
    "border-width": 3,
    "overlay-color": "#f97316",
    "overlay-opacity": 0.12
  },
  "edge": {
    "line-color": "#3a3a48",
    "color": "#7a7a8a",
    "text-background-color": "#111118",
    "width": 2
  },
  "edge:selected": {
    "line-color": "#f97316",
    "width": 3
  }
}
```

Status colors:
- `ok`: `#1f1f28` fill, `#3a3a48` border
- `unreachable`: `#7f1d1d` fill, `#ef4444` border
- `auth_failed`/`timeout`: `#78350f` fill, `#f59e0b` border
- `placeholder`: `#2a2a35` fill, dashed border
- `no_cdp_lldp`: `#3b0764` fill, `#a78bfa` border
- STP Root: `#f97316` border (3px)

---

## Icons (Device Types)

Monoline SVG icons at `frontend/src/assets/icons/`. Work at 16px, 24px, 32px.

| File | Device Type |
|------|------------|
| `switch.svg` | L2 Switch |
| `router.svg` | L3 Router |
| `firewall.svg` | Firewall / ASA |
| `wlc.svg` | Wireless LAN Controller |
| `ap.svg` | Access Point |
| `server.svg` | Server |
| `cloud.svg` | Cloud / WAN |
| `unknown.svg` | Unknown / Placeholder |

Color states:
- Default: `gray-400` (`currentColor`)
- Active/discovered: `gray-100`
- Selected in topology: `orange-500`

---

## Interactions & Animations

| Interaction | Duration | Easing |
|-------------|----------|--------|
| Button hover | 100ms | ease-out |
| Tab switch | 150ms | ease-out |
| Tooltip appear | 150ms | ease-out |
| Panel open/close | 200ms | ease-out |
| Device selection glow | 200ms | ease-out |
| Sidebar collapse | 200ms | ease-out |
| Progress bar fill | 300ms | ease-out |

---

## Accessibility

- All text meets WCAG AA: 4.5:1 for body text, 3:1 for large text
- `orange-500` (#f97316) on `gray-900` (#111118): passes at 4.52:1
- Focus indicators: orange ring (not just browser default)
- Status never indicated by color alone — always with icon or text
- All icon-only buttons have `title` and `aria-label`
- Keyboard navigation: `/` to focus search, `Esc` to close panels

---

## Quality Checklist

- [ ] All text WCAG AA contrast on dark backgrounds
- [ ] Orange used sparingly — accent only, never decorative
- [ ] Monospace font on all IPs, MACs, interface names, CLI data
- [ ] No rogue blues, teals, or purples in primary UI
- [ ] Consistent 16px panel padding
- [ ] Consistent 8px 12px table cell padding
- [ ] Status dots paired with text (never color alone)
- [ ] Topology renders smoothly at 200+ nodes
- [ ] Tables handle 500+ rows
