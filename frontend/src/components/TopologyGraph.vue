<template>
  <div class="relative w-full h-full">
    <!-- Empty state -->
    <div
      v-if="!devices.length"
      class="absolute inset-0 flex flex-col items-center justify-center text-gray-600 pointer-events-none"
    >
      <svg class="w-16 h-16 mb-4 opacity-30" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1"
          d="M9 3H5a2 2 0 00-2 2v4m6-6h10a2 2 0 012 2v4M9 3v18m0 0h10a2 2 0 002-2V9M9 21H5a2 2 0 01-2-2V9m0 0h18"/>
      </svg>
      <p class="text-lg font-medium">No topology loaded</p>
      <p class="text-sm mt-1">Run a discovery to visualize your network</p>
    </div>

    <!-- Graph canvas -->
    <div ref="cyContainer" class="w-full h-full" role="img" aria-label="Network topology graph — use graph controls to zoom and pan" tabindex="0" />

    <!-- Graph controls -->
    <div v-if="devices.length" class="absolute top-4 right-4 flex flex-col gap-2" role="toolbar" aria-label="Graph controls">
      <button class="btn-secondary p-2 text-lg leading-none" title="Fit graph" aria-label="Fit graph to view" @click="fitGraph">⊡</button>
      <button class="btn-secondary p-2 text-lg leading-none" title="Zoom in" aria-label="Zoom in" @click="zoomIn">+</button>
      <button class="btn-secondary p-2 text-lg leading-none" title="Zoom out" aria-label="Zoom out" @click="zoomOut">−</button>
      <div class="w-px h-px" />
      <button
        class="btn-secondary p-2 text-xs leading-none font-mono"
        :title="`Link labels: ${labelMode}`"
        :aria-label="`Toggle link labels — currently ${labelMode}`"
        @click="cycleLabelMode"
      >
        <span v-if="labelMode === 'full'" class="opacity-90">Aa</span>
        <span v-else-if="labelMode === 'minimal'" class="opacity-60">A</span>
        <span v-else class="opacity-40 line-through">A</span>
      </button>
    </div>

    <!-- Edge detail overlay -->
    <Transition name="fade">
      <div
        v-if="selectedEdge"
        class="absolute bottom-4 left-4 card p-3 text-xs max-w-xs z-10 shadow-lg"
      >
        <div class="flex items-center justify-between mb-2">
          <span class="font-semibold font-display" :class="selectedEdge.protocol === 'LLDP' ? 'text-purple-400' : 'text-orange-400'">
            {{ selectedEdge.portChannel || `${abbrevIntf(selectedEdge.sourceIntf)}↔${abbrevIntf(selectedEdge.targetIntf)}` }}
            <span v-if="selectedEdge.speedLabel" class="text-gray-400 font-normal ml-1">({{ selectedEdge.speedLabel }})</span>
            <span class="ml-1 text-[10px] uppercase font-mono font-normal" :class="selectedEdge.protocol === 'LLDP' ? 'text-purple-400' : 'text-gray-400'">{{ selectedEdge.protocol }}</span>
          </span>
          <button class="text-gray-500 hover:text-gray-300 ml-3" @click="selectedEdge = null">✕</button>
        </div>
        <!-- Port-channel members -->
        <template v-if="selectedEdge.members?.length">
          <div class="text-gray-500 mb-1">{{ selectedEdge.memberCount }} member link{{ selectedEdge.memberCount !== 1 ? 's' : '' }}</div>
          <table class="w-full border-collapse">
            <thead>
              <tr class="text-gray-500">
                <th class="text-left pr-3 pb-1">Source</th>
                <th class="text-left pb-1">Target</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(m, idx) in selectedEdge.members" :key="idx" class="border-t border-gray-700/50">
                <td class="pr-3 py-0.5 font-mono text-gray-300">{{ abbrevIntf(m.source_intf) }}</td>
                <td class="py-0.5 font-mono text-gray-300">{{ abbrevIntf(m.target_intf) }}</td>
              </tr>
            </tbody>
          </table>
        </template>
        <!-- LLDP detail section -->
        <template v-if="selectedEdge.protocol === 'LLDP' && (selectedEdge.capabilities?.length || selectedEdge.medDeviceType || selectedEdge.portDescription)">
          <div class="border-t border-gray-700/50 mt-2 pt-2">
            <div class="text-purple-400 font-semibold mb-1 uppercase tracking-wider text-[10px]">LLDP Detail</div>
            <dl class="grid grid-cols-[auto_1fr] gap-x-2 gap-y-0.5">
              <template v-if="selectedEdge.capabilities?.length">
                <dt class="text-gray-500">Capabilities</dt>
                <dd class="text-gray-300">
                  <span v-for="cap in selectedEdge.capabilities" :key="cap" class="badge bg-purple-900/30 text-purple-300 mr-1 text-[10px]">{{ cap }}</span>
                </dd>
              </template>
              <template v-if="selectedEdge.systemDescription">
                <dt class="text-gray-500">System</dt>
                <dd class="text-gray-300 truncate">{{ selectedEdge.systemDescription }}</dd>
              </template>
              <template v-if="selectedEdge.portDescription">
                <dt class="text-gray-500">Port Desc</dt>
                <dd class="text-gray-300 truncate">{{ selectedEdge.portDescription }}</dd>
              </template>
              <template v-if="selectedEdge.medDeviceType">
                <dt class="text-gray-500">MED Type</dt>
                <dd class="text-gray-300">{{ selectedEdge.medDeviceType }}</dd>
              </template>
              <template v-if="selectedEdge.medPoeRequested != null">
                <dt class="text-gray-500">PoE Req/Alloc</dt>
                <dd class="text-gray-300 font-mono">{{ selectedEdge.medPoeRequested }}W / {{ selectedEdge.medPoeAllocated ?? '—' }}W</dd>
              </template>
              <template v-if="selectedEdge.medNetworkPolicy">
                <dt class="text-gray-500">Net Policy</dt>
                <dd class="text-gray-300">{{ selectedEdge.medNetworkPolicy }}</dd>
              </template>
            </dl>
          </div>
        </template>
      </div>
    </Transition>

    <!-- Legend (collapsible) -->
    <div v-if="devices.length" class="absolute top-3 left-3 z-10 card text-xs">
      <button
        class="flex items-center gap-1.5 px-2 py-1.5 w-full text-left text-gray-400 hover:text-gray-200 transition-colors"
        :title="legendOpen ? 'Collapse legend' : 'Expand legend'"
        :aria-expanded="legendOpen"
        aria-controls="topology-legend-items"
        @click="legendOpen = !legendOpen"
      >
        <svg
          class="w-3 h-3 transition-transform duration-200"
          :class="{ '-rotate-90': !legendOpen }"
          fill="none" stroke="currentColor" viewBox="0 0 24 24"
        >
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
        </svg>
        <span class="font-medium text-gray-300">Legend</span>
      </button>
      <div
        id="topology-legend-items"
        class="legend-body"
        :class="{ 'legend-body--open': legendOpen }"
      >
        <div class="legend-inner flex flex-col gap-1 px-2">
          <div v-for="item in legend" :key="item.label" class="flex items-center gap-2">
            <span
              v-if="item.dashed"
              class="w-3 h-0 inline-block border-t-2 border-dashed"
              :style="{ borderColor: item.color }"
            />
            <span
              v-else-if="item.border"
              class="w-3 h-3 rounded-sm inline-block border-2"
              :style="{ borderColor: item.border, background: item.color }"
            />
            <span
              v-else
              class="w-3 h-3 rounded-sm inline-block"
              :style="{ background: item.color }"
            />
            <span class="text-gray-400">{{ item.label }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, watch, onMounted, onUnmounted, nextTick } from 'vue'
import cytoscape from 'cytoscape'
import fcose from 'cytoscape-fcose'
import { useTheme } from '../composables/useTheme.js'

cytoscape.use(fcose)

const { theme } = useTheme()

/** Hex color palettes for Cytoscape, keyed by theme.
 *  Cytoscape renders to <canvas>, not DOM, so CSS custom properties (which use
 *  nested var() refs like `rgb(var(--gray-50-rgb))`) cannot be used directly.
 *  getComputedStyle returns the unresolved specified value for custom properties,
 *  making runtime resolution fragile and browser-dependent.
 *  These hex maps mirror the design tokens in variables.css — keep them in sync. */
const CYTO_COLORS = {
  dark: {
    gray950: '#0a0a0f',
    gray900: '#111118',
    gray800: '#1f1f28',
    gray700: '#2a2a35',
    gray600: '#3a3a48',
    gray400: '#7a7a8a',
    gray50:  '#f0f0f2',
    orange500: '#f97316',
  },
  light: {
    gray950: '#f8f8fa',
    gray900: '#f0f0f3',
    gray800: '#e0e0e5',
    gray700: '#cbcbd4',
    gray600: '#b0b0bc',
    gray400: '#6a6a78',
    gray50:  '#0f0f1a',
    orange500: '#ea580c',
  },
}

/** Get a Cytoscape-safe hex color for the current theme. */
function cyColor(key) {
  const palette = CYTO_COLORS[theme.value] || CYTO_COLORS.dark
  return palette[key] || '#1f1f28'
}

const props = defineProps({
  devices: { type: Array, default: () => [] },
  links: { type: Array, default: () => [] },
  highlightVlan: { type: String, default: null },
  // Path trace highlighting: arrays of device IDs and "srcId:tgtId" link keys
  pathNodeIds: { type: Array, default: () => [] },
  pathLinkKeys: { type: Array, default: () => [] },
  // Protocol filter: 'all' | 'cdp' | 'lldp'
  protocolFilter: { type: String, default: 'all' },
})

const emit = defineEmits(['node-selected'])

const cyContainer = ref(null)
let cy = null

const selectedEdge = ref(null)
const legendOpen = ref(false)
// Label display mode: 'full' = interface labels + center, 'minimal' = center only, 'off' = no labels
const labelMode = ref('full')
const LABEL_MODES = ['full', 'minimal', 'off']

function cycleLabelMode() {
  const idx = LABEL_MODES.indexOf(labelMode.value)
  labelMode.value = LABEL_MODES[(idx + 1) % LABEL_MODES.length]
}

function applyLabelMode(mode) {
  if (!cy) return
  cy.batch(() => {
    cy.edges().forEach(edge => {
      switch (mode) {
        case 'full':
          edge.style({
            'label': edge.data('label'),
            'source-label': edge.data('srcLabel'),
            'target-label': edge.data('tgtLabel'),
          })
          break
        case 'minimal':
          edge.style({
            'label': edge.data('label'),
            'source-label': '',
            'target-label': '',
          })
          break
        case 'off':
          edge.style({
            'label': '',
            'source-label': '',
            'target-label': '',
          })
          break
      }
    })
  })
}

/** Build theme-aware legend — uses CSS vars so it updates on theme switch */
function buildLegend() {
  return [
    { label: 'Device (OK)', color: cyColor('gray800'), border: cyColor('gray600') },
    { label: 'Root Bridge (STP)', color: cyColor('orange500'), isRoot: true },
    { label: 'Placeholder', color: cyColor('gray700'), dashed: true },
    { label: 'Unreachable', color: '#ef4444' },
    { label: 'Auth Failed / Timeout', color: '#f59e0b' },
    { label: 'No CDP/LLDP', color: '#a78bfa' },
    { label: 'CDP Link', color: cyColor('gray600') },
    { label: 'LLDP Link', color: '#a78bfa', dashed: true },
    { label: 'Port-Channel', color: cyColor('orange500'), dashed: false },
    { label: 'Blocked (STP)', color: '#ef4444', dashed: true },
  ]
}

const legend = ref(buildLegend())

function getStatusColors() {
  const dark = theme.value !== 'light'
  return {
    ok: { bg: cyColor('gray800'), border: cyColor('gray600') },
    placeholder: { bg: cyColor('gray700'), border: cyColor('gray800') },
    unreachable: { bg: dark ? '#7f1d1d' : '#fecaca', border: dark ? '#ef4444' : '#dc2626' },
    auth_failed: { bg: dark ? '#78350f' : '#fed7aa', border: dark ? '#f59e0b' : '#ea580c' },
    timeout: { bg: dark ? '#78350f' : '#fed7aa', border: dark ? '#f59e0b' : '#ea580c' },
    no_cdp_lldp: { bg: dark ? '#3b0764' : '#e9d5ff', border: dark ? '#a78bfa' : '#7c3aed' },
  }
}

let STATUS_COLORS = getStatusColors()

function abbrevIntf(name) {
  if (!name) return ''
  // Order matters: longer/more-specific names must come before shorter ones
  return name
    .replace(/Wlan-GigabitEthernet/gi, 'WGi')
    .replace(/AppGigabitEthernet/gi, 'AppGi')
    .replace(/TwentyFiveGigabitEthernet/gi, 'Twe')
    .replace(/TwentyFiveGigE/gi, 'Twe')
    .replace(/HundredGigabitEthernet/gi, 'Hu')
    .replace(/HundredGigE/gi, 'Hu')
    .replace(/FortyGigabitEthernet/gi, 'Fo')
    .replace(/TenGigabitEthernet/gi, 'Te')
    .replace(/GigabitEthernet/gi, 'Gi')
    .replace(/FastEthernet/gi, 'Fa')
    .replace(/Ethernet/gi, 'Et')
    .replace(/Port-channel/gi, 'Po')
    .replace(/Loopback/gi, 'Lo')
    .replace(/Serial/gi, 'Se')
    .replace(/Management/gi, 'Mg')
    .replace(/mgmt/gi, 'Mg')
}

function buildElements() {
  // Build a device lookup for STP checks
  const deviceMap = {}
  for (const d of props.devices) {
    deviceMap[d.id] = d
  }

  // Compute per-node protocol presence (which protocols discover links to/from this node)
  const nodeProtocols = {}  // deviceId -> Set<'CDP'|'LLDP'>
  for (const lk of props.links) {
    if (!nodeProtocols[lk.source]) nodeProtocols[lk.source] = new Set()
    if (!nodeProtocols[lk.target]) nodeProtocols[lk.target] = new Set()
    nodeProtocols[lk.source].add(lk.protocol)
    nodeProtocols[lk.target].add(lk.protocol)
  }

  const nodes = props.devices.map(d => {
    const isRoot = d.stp_info?.some(sv => sv.is_root) || false
    const vlanIds = (d.vlans || []).map(v => v.vlan_id).join(',')
    const protos = nodeProtocols[d.id] || new Set()
    // protocolIndicator: 'lldp' = LLDP only, 'both' = CDP+LLDP, '' = CDP only or none
    const protocolIndicator = protos.has('LLDP') && protos.has('CDP')
      ? 'both'
      : protos.has('LLDP') ? 'lldp' : ''
    return {
      data: {
        id: d.id,
        label: (isRoot ? '★ ' : '') + (d.hostname || d.id),
        ip: d.mgmt_ip,
        status: d.status,
        isRoot: isRoot ? 'true' : 'false',
        vlanIds,
        protocolIndicator,
        device: d,
      },
    }
  })

  const edges = props.links.map((lk, i) => {
    // Check if any STP VLAN on either endpoint has this link's interface in BLK state
    let stpBlocked = false
    const srcDev = deviceMap[lk.source]
    const tgtDev = deviceMap[lk.target]
    if (srcDev?.stp_info) {
      for (const sv of srcDev.stp_info) {
        if (sv.ports?.some(p => p.interface === lk.source_intf && p.state === 'BLK')) {
          stpBlocked = true
          break
        }
      }
    }
    if (!stpBlocked && tgtDev?.stp_info && lk.target_intf) {
      for (const sv of tgtDev.stp_info) {
        if (sv.ports?.some(p => p.interface === lk.target_intf && p.state === 'BLK')) {
          stpBlocked = true
          break
        }
      }
    }

    const isPortChannel = !!lk.port_channel
    // Split labels: source interface near source, target interface near target
    const srcLabel = abbrevIntf(lk.source_intf)
    const tgtLabel = abbrevIntf(lk.target_intf)
    // Center label: port-channel name or protocol badge
    let centerLabel
    if (isPortChannel) {
      centerLabel = lk.speed_label ? `${lk.port_channel} (${lk.speed_label})` : lk.port_channel
    } else {
      centerLabel = lk.protocol
    }
    // Legacy combined label for data reference
    const fullLabel = isPortChannel
      ? `${centerLabel} · ${lk.protocol}`
      : `${srcLabel}↔${tgtLabel} · ${lk.protocol}`

    return {
      data: {
        id: `e${i}`,
        source: lk.source,
        target: lk.target,
        sourceIntf: lk.source_intf,
        targetIntf: lk.target_intf || '',
        protocol: lk.protocol,
        stpBlocked: stpBlocked ? 'true' : 'false',
        isPortChannel: isPortChannel ? 'true' : 'false',
        portChannel: lk.port_channel || '',
        memberCount: lk.member_count ?? 1,
        speedLabel: lk.speed_label || '',
        members: lk.members || [],
        label: centerLabel,
        srcLabel,
        tgtLabel,
        fullLabel,
        // LLDP metadata for detail overlay
        capabilities: lk.capabilities || [],
        systemDescription: lk.system_description || '',
        medDeviceType: lk.med_device_type || '',
        medPoeRequested: lk.med_poe_requested,
        medPoeAllocated: lk.med_poe_allocated,
        medNetworkPolicy: lk.med_network_policy || '',
        portDescription: lk.port_description || '',
      },
    }
  })

  return [...nodes, ...edges]
}

function _getNodeStyle(status) {
  const c = STATUS_COLORS[status] || STATUS_COLORS.ok
  return { 'background-color': c.bg, 'border-color': c.border }
}

function initCy() {
  if (!cyContainer.value) return
  if (cy) { cy.destroy(); cy = null }

  const orange = cyColor('orange500')
  const edgeColor = cyColor('gray600')
  const nodeBg = cyColor('gray800')
  const nodeBorder = cyColor('gray600')
  const textColor = cyColor('gray50')
  const edgeTextColor = cyColor('gray400')
  const edgeLabelBg = cyColor('gray900')
  const placeholderBg = cyColor('gray700')
  const placeholderBorder = cyColor('gray800')
  const canvasBg = cyColor('gray950')

  cy = cytoscape({
    container: cyContainer.value,
    elements: buildElements(),
    style: [
      {
        selector: 'node',
        style: {
          'background-color': nodeBg,
          'border-width': 2,
          'border-color': nodeBorder,
          'label': 'data(label)',
          'color': textColor,
          'text-valign': 'bottom',
          'text-halign': 'center',
          'font-size': '11px',
          'font-family': 'JetBrains Mono, monospace',
          'text-margin-y': 4,
          'width': 40,
          'height': 40,
          'shape': 'round-rectangle',
          'text-wrap': 'wrap',
          'text-max-width': 80,
          'text-outline-color': canvasBg,
          'text-outline-width': 2,
        },
      },
      {
        selector: 'node[status="placeholder"]',
        style: { 'background-color': placeholderBg, 'border-color': placeholderBorder, 'border-style': 'dashed' },
      },
      {
        selector: 'node[status="unreachable"]',
        style: { 'background-color': STATUS_COLORS.unreachable.bg, 'border-color': STATUS_COLORS.unreachable.border },
      },
      {
        selector: 'node[status="auth_failed"], node[status="timeout"]',
        style: { 'background-color': STATUS_COLORS.auth_failed.bg, 'border-color': STATUS_COLORS.auth_failed.border },
      },
      {
        selector: 'node[status="no_cdp_lldp"]',
        style: { 'background-color': STATUS_COLORS.no_cdp_lldp.bg, 'border-color': STATUS_COLORS.no_cdp_lldp.border },
      },
      {
        selector: 'node[isRoot="true"]',
        style: { 'border-width': 3, 'border-color': orange },
      },
      {
        selector: 'node:selected',
        style: {
          'border-width': 3,
          'border-color': orange,
          'overlay-opacity': 0.12,
          'overlay-color': orange,
        },
      },
      {
        selector: 'edge',
        style: {
          'width': 2,
          'line-color': edgeColor,
          'target-arrow-color': edgeColor,
          'target-arrow-shape': 'none',
          'curve-style': 'bezier',
          // Center label: protocol or port-channel name
          'label': 'data(label)',
          'font-size': '8px',
          'color': edgeTextColor,
          'text-rotation': 'autorotate',
          'text-background-color': edgeLabelBg,
          'text-background-opacity': 0.85,
          'text-background-padding': '3px',
          'font-family': 'JetBrains Mono, monospace',
          'text-outline-color': edgeLabelBg,
          'text-outline-width': 1,
          'text-margin-y': -8,
          // Source interface label (near source node)
          'source-label': 'data(srcLabel)',
          'source-text-offset': 28,
          'source-text-rotation': 'autorotate',
          'source-text-margin-y': -8,
          // Target interface label (near target node)
          'target-label': 'data(tgtLabel)',
          'target-text-offset': 28,
          'target-text-rotation': 'autorotate',
          'target-text-margin-y': -8,
        },
      },
      {
        selector: 'edge[protocol="LLDP"]',
        style: { 'line-color': '#a78bfa', 'line-style': 'dashed', 'line-dash-pattern': [6, 3], 'color': '#a78bfa' },
      },
      {
        selector: 'edge[isPortChannel="true"]',
        style: { 'width': 4, 'line-color': orange, 'color': orange, 'opacity': 0.85 },
      },
      {
        selector: 'edge[stpBlocked="true"]',
        style: { 'line-color': '#ef4444', 'line-style': 'dashed', 'line-dash-pattern': [4, 4], 'opacity': 0.7 },
      },
      {
        selector: 'edge:selected',
        style: { 'line-color': orange, 'width': 3 },
      },
      // Path trace highlights
      {
        selector: 'node.path-node',
        style: { 'border-width': 4, 'border-color': orange, 'overlay-opacity': 0.1, 'overlay-color': orange },
      },
      {
        selector: 'edge.path-edge',
        style: { 'line-color': orange, 'width': 4, 'z-index': 10 },
      },
      {
        selector: 'node.path-dim, edge.path-dim',
        style: { 'opacity': 0.25 },
      },
    ],
    layout: { name: 'fcose', quality: 'proof', randomize: true, animate: true, animationDuration: 600, edgeElasticity: 0.45, idealEdgeLength: 120, nodeSeparation: 100 },
    wheelSensitivity: 0.3,
    minZoom: 0.1,
    maxZoom: 4,
  })

  cy.on('tap', 'node', evt => {
    selectedEdge.value = null
    emit('node-selected', evt.target.data('device'))
  })

  cy.on('tap', 'edge', evt => {
    const d = evt.target.data()
    if (d.isPortChannel === 'true') {
      selectedEdge.value = {
        portChannel: d.portChannel,
        memberCount: d.memberCount,
        speedLabel: d.speedLabel,
        members: d.members,
        protocol: d.protocol,
        capabilities: d.capabilities,
        systemDescription: d.systemDescription,
        medDeviceType: d.medDeviceType,
        medPoeRequested: d.medPoeRequested,
        medPoeAllocated: d.medPoeAllocated,
        medNetworkPolicy: d.medNetworkPolicy,
        portDescription: d.portDescription,
      }
    } else if (d.protocol === 'LLDP' && (d.capabilities?.length || d.medDeviceType || d.portDescription)) {
      selectedEdge.value = {
        sourceIntf: d.sourceIntf,
        targetIntf: d.targetIntf,
        protocol: d.protocol,
        capabilities: d.capabilities,
        systemDescription: d.systemDescription,
        medDeviceType: d.medDeviceType,
        medPoeRequested: d.medPoeRequested,
        medPoeAllocated: d.medPoeAllocated,
        medNetworkPolicy: d.medNetworkPolicy,
        portDescription: d.portDescription,
      }
    } else {
      selectedEdge.value = null
    }
  })

  cy.on('tap', evt => {
    if (evt.target === cy) {
      selectedEdge.value = null
      emit('node-selected', null)
    }
  })
}

function fitGraph() { cy?.fit(undefined, 40) }
function zoomIn() { cy?.zoom({ level: (cy.zoom() * 1.3), renderedPosition: { x: cy.width() / 2, y: cy.height() / 2 } }) }
function zoomOut() { cy?.zoom({ level: (cy.zoom() / 1.3), renderedPosition: { x: cy.width() / 2, y: cy.height() / 2 } }) }

/** Export PNG — called from parent via expose */
function exportPng() {
  if (!cy) return
  const dataUrl = cy.png({ scale: 2, bg: cyColor('gray950'), full: true })
  const a = document.createElement('a')
  a.href = dataUrl
  a.download = 'netscope-topology.png'
  a.click()
}

/** Capture current layout state (zoom, pan, node positions) */
function getLayout() {
  if (!cy) return null
  const zoom = cy.zoom()
  const pan = cy.pan()
  const positions = cy.nodes().map(node => ({
    device_id: node.id(),
    x: node.position('x'),
    y: node.position('y'),
  }))
  return { zoom, pan_x: pan.x, pan_y: pan.y, node_positions: positions }
}

/** Restore layout from saved state (zoom, pan, node positions) */
function restoreLayout(layout) {
  if (!cy || !layout) return
  cy.batch(() => {
    if (layout.node_positions?.length) {
      const posMap = {}
      for (const np of layout.node_positions) {
        posMap[np.device_id] = { x: np.x, y: np.y }
      }
      cy.nodes().forEach(node => {
        const pos = posMap[node.id()]
        if (pos) node.position(pos)
      })
    }
  })
  if (layout.zoom != null) cy.zoom(layout.zoom)
  if (layout.pan_x != null && layout.pan_y != null) {
    cy.pan({ x: layout.pan_x, y: layout.pan_y })
  }
}

defineExpose({ exportPng, getLayout, restoreLayout })

function applyProtocolFilter(filter) {
  if (!cy) return
  cy.batch(() => {
    if (filter === 'all') {
      cy.edges().style('opacity', null)
      cy.nodes().style('opacity', null)
      return
    }
    const proto = filter.toUpperCase() // 'CDP' or 'LLDP'
    // Dim non-matching edges
    cy.edges().forEach(edge => {
      edge.style('opacity', edge.data('protocol') === proto ? 1 : 0.12)
    })
    // Dim orphaned nodes (no visible edges)
    const connectedNodes = new Set()
    cy.edges().forEach(edge => {
      if (edge.data('protocol') === proto) {
        connectedNodes.add(edge.data('source'))
        connectedNodes.add(edge.data('target'))
      }
    })
    cy.nodes().forEach(node => {
      node.style('opacity', connectedNodes.has(node.id()) ? 1 : 0.25)
    })
  })
}

function applyVlanFilter(vlanId) {
  if (!cy) return
  cy.batch(() => {
    if (!vlanId) {
      cy.nodes().style('opacity', 1)
    } else {
      cy.nodes().forEach(node => {
        const ids = node.data('vlanIds') || ''
        const match = ids.split(',').some(v => v.trim() === vlanId)
        node.style('opacity', match ? 1 : 0.15)
      })
    }
  })
}

function applyPathHighlight(nodeIds, linkKeys) {
  if (!cy) return
  cy.batch(() => {
    cy.elements().removeClass('path-node path-edge path-dim')
    if (!nodeIds || nodeIds.length === 0) return

    const nodeSet = new Set(nodeIds)
    // Build a set of canonical edge keys (both directions)
    const edgeSet = new Set()
    for (const k of (linkKeys || [])) {
      edgeSet.add(k)
      const parts = k.split(':')
      if (parts.length === 2) edgeSet.add(`${parts[1]}:${parts[0]}`)
    }

    cy.nodes().forEach(node => {
      if (nodeSet.has(node.id())) {
        node.addClass('path-node')
      } else {
        node.addClass('path-dim')
      }
    })

    cy.edges().forEach(edge => {
      const key1 = `${edge.data('source')}:${edge.data('target')}`
      const key2 = `${edge.data('target')}:${edge.data('source')}`
      if (edgeSet.has(key1) || edgeSet.has(key2)) {
        edge.addClass('path-edge')
      } else {
        edge.addClass('path-dim')
      }
    })
  })
}

watch(() => [props.devices, props.links], async () => {
  selectedEdge.value = null
  await nextTick()
  initCy()
  if (labelMode.value !== 'full') applyLabelMode(labelMode.value)
  if (props.protocolFilter !== 'all') applyProtocolFilter(props.protocolFilter)
  if (props.highlightVlan) applyVlanFilter(props.highlightVlan)
  if (props.pathNodeIds?.length) applyPathHighlight(props.pathNodeIds, props.pathLinkKeys)
}, { deep: true })

// Re-initialize Cytoscape when theme changes to pick up new CSS variable values
watch(theme, () => {
  STATUS_COLORS = getStatusColors()
  legend.value = buildLegend()
  nextTick(() => {
    if (cy && props.devices.length) {
      initCy()
      if (labelMode.value !== 'full') applyLabelMode(labelMode.value)
      if (props.protocolFilter !== 'all') applyProtocolFilter(props.protocolFilter)
      if (props.highlightVlan) applyVlanFilter(props.highlightVlan)
      if (props.pathNodeIds?.length) applyPathHighlight(props.pathNodeIds, props.pathLinkKeys)
    }
  })
})

watch(labelMode, (mode) => {
  applyLabelMode(mode)
})

watch(() => props.highlightVlan, (vlanId) => {
  applyVlanFilter(vlanId)
})

watch(() => props.protocolFilter, (filter) => {
  applyProtocolFilter(filter)
})

watch(() => [props.pathNodeIds, props.pathLinkKeys], ([nodeIds, linkKeys]) => {
  applyPathHighlight(nodeIds, linkKeys)
}, { deep: true })

/** Keyboard navigation for the topology graph canvas */
function handleKeydown(e) {
  if (!cy) return
  const PAN_STEP = 50
  switch (e.key) {
    case '+': case '=':
      zoomIn()
      e.preventDefault()
      break
    case '-': case '_':
      zoomOut()
      e.preventDefault()
      break
    case 'ArrowUp':
      cy.panBy({ x: 0, y: PAN_STEP })
      e.preventDefault()
      break
    case 'ArrowDown':
      cy.panBy({ x: 0, y: -PAN_STEP })
      e.preventDefault()
      break
    case 'ArrowLeft':
      cy.panBy({ x: PAN_STEP, y: 0 })
      e.preventDefault()
      break
    case 'ArrowRight':
      cy.panBy({ x: -PAN_STEP, y: 0 })
      e.preventDefault()
      break
    case 'f': case 'F':
      fitGraph()
      e.preventDefault()
      break
  }
}

onMounted(() => {
  if (props.devices.length) initCy()
  cyContainer.value?.addEventListener('keydown', handleKeydown)
})

onUnmounted(() => {
  cyContainer.value?.removeEventListener('keydown', handleKeydown)
  cy?.destroy()
})
</script>

<style scoped>
.legend-body {
  display: grid;
  grid-template-rows: 0fr;
  transition: grid-template-rows 0.2s ease;
}
.legend-body--open {
  grid-template-rows: 1fr;
}
.legend-body > div {
  overflow: hidden;
}
.legend-body--open .legend-inner {
  padding-bottom: 0.5rem;
}
</style>
