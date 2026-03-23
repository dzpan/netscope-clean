<template>
  <div class="flex flex-col h-full overflow-hidden">
    <!-- Header -->
    <div class="flex items-center justify-between px-4 py-3 border-b border-gray-700 shrink-0">
      <div>
        <h2 class="font-semibold text-gray-100 font-display">Help</h2>
        <p class="text-xs text-gray-400 mt-0.5">NetScope quick-start guide</p>
      </div>
      <button class="btn-ghost p-1 text-gray-500 hover:text-gray-200" @click="$emit('close')">✕</button>
    </div>

    <!-- Accordion sections -->
    <div class="flex-1 overflow-y-auto">
      <div v-for="(section, sIdx) in sections" :key="section.id" class="border-b border-gray-800/50">
        <button
          class="w-full flex items-center gap-2 px-4 py-3 text-left transition-colors hover:bg-gray-800/30"
          @click="toggle(section.id)"
        >
          <span
            class="text-xs text-gray-600 transition-transform duration-200 shrink-0"
            :class="{ 'rotate-90': expanded.has(section.id) }"
          >▶</span>
          <span class="text-orange-400 text-sm shrink-0 w-4 text-center font-mono">{{ sIdx + 1 }}</span>
          <span class="text-sm font-medium" :class="expanded.has(section.id) ? 'text-orange-400' : 'text-gray-200'">
            {{ section.title }}
          </span>
        </button>
        <div v-if="expanded.has(section.id)" class="px-4 pb-4 text-xs text-gray-400 leading-relaxed space-y-2">
          <div v-for="(item, idx) in section.items" :key="idx">
            <p v-if="item.type === 'text'">{{ item.content }}</p>
            <div v-else-if="item.type === 'list'" class="space-y-1">
              <div v-for="(li, i) in item.items" :key="i" class="flex gap-2">
                <span class="text-orange-500/60 shrink-0">•</span>
                <span v-html="li"></span>
              </div>
            </div>
            <div v-else-if="item.type === 'shortcuts'" class="space-y-1.5">
              <div v-for="(sc, i) in item.items" :key="i" class="flex items-center justify-between">
                <span class="text-gray-400">{{ sc.desc }}</span>
                <kbd class="px-1.5 py-0.5 bg-gray-800 border border-gray-700 rounded text-gray-300 font-mono text-xs">{{ sc.key }}</kbd>
              </div>
            </div>
            <div v-else-if="item.type === 'warning'" class="flex items-start gap-2 mt-2 px-2 py-1.5 rounded bg-orange-900/20 border border-orange-800/30">
              <span class="text-orange-400 shrink-0">⚠</span>
              <span class="text-orange-300/80">{{ item.content }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- Footer -->
      <div class="px-4 py-4 text-center">
        <p class="text-xs text-gray-600">NetScope v1.1.0</p>
        <p class="text-xs text-gray-700 mt-0.5">SSH-based network topology intelligence</p>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'

defineEmits(['close'])

const expanded = ref(new Set(['getting-started']))

function toggle(id) {
  const next = new Set(expanded.value)
  if (next.has(id)) {
    next.delete(id)
  } else {
    next.add(id)
  }
  expanded.value = next
}

const sections = [
  {
    id: 'getting-started',
    title: 'Getting Started',
    items: [
      { type: 'text', content: 'NetScope discovers your network topology via SSH using CDP/LLDP neighbor data.' },
      { type: 'list', items: [
        '<strong class="text-gray-200">Seed IPs</strong> — Enter one or more device IPs in the left sidebar to start BFS discovery from.',
        '<strong class="text-gray-200">Credentials</strong> — Provide SSH username/password. Multiple credential sets are tried in order per device.',
        '<strong class="text-gray-200">Scope</strong> — Set max hops, exclude patterns, or limit to specific subnets.',
        '<strong class="text-gray-200">Start Discovery</strong> — Click Discover to begin. Progress is shown in the center overlay.',
      ]},
      { type: 'text', content: 'If some devices fail authentication, a retry modal lets you supply alternate credentials.' },
    ],
  },
  {
    id: 'topology-map',
    title: 'Topology Map',
    items: [
      { type: 'text', content: 'The center canvas shows your discovered network as an interactive graph.' },
      { type: 'list', items: [
        '<strong class="text-gray-200">Click</strong> a device node to view its details in the right panel.',
        '<strong class="text-gray-200">Drag</strong> nodes to rearrange the layout.',
        '<strong class="text-gray-200">Scroll</strong> to zoom in and out. Pinch-to-zoom works on trackpads.',
        '<strong class="text-gray-200">Click + drag</strong> on the background to pan.',
        'Link lines show connections between devices. Thicker lines indicate bundled links (EtherChannel).',
        'Nodes are colored by device role — routers, switches, access points, and unknown devices each have distinct icons.',
      ]},
    ],
  },
  {
    id: 'search',
    title: 'Search',
    items: [
      { type: 'text', content: 'The search bar in the header finds devices, IPs, MACs, VLANs, and routes across all discovered data.' },
      { type: 'list', items: [
        '<strong class="text-gray-200">Hostnames</strong> — type any part of a device name.',
        '<strong class="text-gray-200">IP addresses</strong> — search by management or interface IP.',
        '<strong class="text-gray-200">MAC addresses</strong> — partial or full MAC match.',
        '<strong class="text-gray-200">VLANs</strong> — search by VLAN ID or name.',
        '<strong class="text-gray-200">Routes</strong> — find devices by routing table prefix.',
      ]},
      { type: 'text', content: 'Press / to focus. Arrow keys to navigate, Enter to select. Minimum 2 characters to trigger search.' },
    ],
  },
  {
    id: 'panels',
    title: 'Panels',
    items: [
      { type: 'text', content: 'The right sidebar shows contextual panels. Only one panel is visible at a time.' },
      { type: 'list', items: [
        '<strong class="text-gray-200">Device Detail</strong> — interfaces, VLANs, routes, ARP, and MAC table for the selected device.',
        '<strong class="text-gray-200">Config Dump</strong> — full running-config fetched live via SSH.',
        '<strong class="text-gray-200">VLAN Map</strong> — cross-device VLAN overview. Open from the status bar. Filter the topology by VLAN.',
        '<strong class="text-gray-200">Alerts</strong> — change detection alerts and rule configuration.',
        '<strong class="text-gray-200">Path Trace</strong> — L3 hop-by-hop path between two devices.',
        '<strong class="text-gray-200">STP</strong> — Spanning Tree root bridge per VLAN.',
        '<strong class="text-gray-200">History</strong> — browse and compare past discovery snapshots.',
        '<strong class="text-gray-200">Audit Log</strong> — change audit trail with rollback capability (Advanced Mode only).',
      ]},
    ],
  },
  {
    id: 'data-table',
    title: 'Data Table',
    items: [
      { type: 'text', content: 'The bottom drawer shows tabular data for the current session.' },
      { type: 'list', items: [
        'Click <strong class="text-gray-200">▶ Data Tables</strong> in the status bar to expand or collapse.',
        'Tabs: <strong class="text-gray-200">Devices</strong>, <strong class="text-gray-200">Links</strong>, <strong class="text-gray-200">Failures</strong>.',
        'Click a device row to select it on the map and open its detail panel.',
        'Drag the top edge of the drawer to resize it.',
      ]},
    ],
  },
  {
    id: 'advanced-mode',
    title: 'Advanced Mode',
    items: [
      { type: 'text', content: 'Toggle Advanced Mode with the switch in the header toolbar to enable live configuration changes.' },
      { type: 'list', items: [
        '<strong class="text-gray-200">VLAN Changes</strong> — modify port VLAN assignments on managed switches directly from the device panel.',
        '<strong class="text-gray-200">Audit Log</strong> — every change is recorded with before/after state and timestamps.',
        '<strong class="text-gray-200">Change Detection</strong> — re-discover to detect topology drift between snapshots.',
        '<strong class="text-gray-200">Undo</strong> — revert changes from the audit log with one click.',
      ]},
      { type: 'warning', content: 'Advanced Mode enables live configuration changes on network devices. Use with caution in production environments.' },
    ],
  },
  {
    id: 'shortcuts',
    title: 'Keyboard Shortcuts',
    items: [
      { type: 'shortcuts', items: [
        { key: '/', desc: 'Focus search bar' },
        { key: 'Esc', desc: 'Close panel / dismiss search' },
        { key: '↑ ↓', desc: 'Navigate search results' },
        { key: 'Enter', desc: 'Select search result' },
        { key: 'Scroll', desc: 'Zoom in/out on topology' },
      ]},
    ],
  },
]
</script>
