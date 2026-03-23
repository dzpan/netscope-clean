<template>
  <div class="flex flex-col h-full overflow-hidden">
    <!-- Header -->
    <div class="flex items-center justify-between px-4 py-3 border-b border-gray-700 shrink-0">
      <div>
        <h2 class="font-semibold text-gray-100">STP Root Bridges</h2>
        <p class="text-xs text-gray-400 mt-0.5">
          {{ stpRoots.length }} VLAN{{ stpRoots.length !== 1 ? 's' : '' }} with root data
        </p>
      </div>
      <button class="btn-ghost p-1 text-gray-500 hover:text-gray-200" @click="$emit('close')">✕</button>
    </div>

    <!-- Filter -->
    <div class="px-4 py-2 border-b border-gray-700 shrink-0">
      <input
        v-model="search"
        class="input text-xs py-1.5"
        placeholder="Filter by VLAN ID or root hostname…"
      />
    </div>

    <!-- Risk legend -->
    <div class="px-4 py-2 flex items-center gap-2 text-xs text-amber-400 border-b border-gray-700 shrink-0">
      <span class="inline-block w-2 h-2 rounded-full bg-amber-400 shrink-0"></span>
      Default priority (32768+VLAN) — root not intentionally configured
    </div>

    <!-- Empty state -->
    <div v-if="stpRoots.length === 0" class="flex-1 flex flex-col items-center justify-center text-gray-500 gap-2">
      <svg class="w-8 h-8 opacity-30" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5"
          d="M13 16h-1v-4h-1m1-4h.01M12 2a10 10 0 110 20A10 10 0 0112 2z"/>
      </svg>
      <p class="text-sm">No STP data available</p>
      <p class="text-xs">Run discovery with the Standard profile to collect STP data</p>
    </div>

    <!-- Table -->
    <div v-else class="flex-1 overflow-y-auto">
      <table v-resizable-columns="'stp-roots'" class="w-full text-xs">
        <thead class="sticky top-0 bg-gray-900 z-10">
          <tr class="text-gray-500 border-b border-gray-700">
            <th
              class="text-left px-4 py-2 cursor-pointer hover:text-gray-300"
              @click="toggleSort('vlan_id')"
            >
              VLAN {{ sortIcon('vlan_id') }}
            </th>
            <th
              class="text-left px-2 py-2 cursor-pointer hover:text-gray-300"
              @click="toggleSort('hostname')"
            >
              Root Bridge {{ sortIcon('hostname') }}
            </th>
            <th
              class="text-right px-2 py-2 cursor-pointer hover:text-gray-300"
              @click="toggleSort('root_priority')"
            >
              Priority {{ sortIcon('root_priority') }}
            </th>
            <th class="text-center px-2 py-2 w-8" title="Default priority risk indicator">⚠</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="row in filteredRoots"
            :key="row.vlan_id"
            class="border-b border-gray-800 hover:bg-gray-800/40 cursor-pointer"
            :class="{ 'bg-amber-900/10': row.is_default_priority }"
            @click="$emit('device-selected', row.device_id)"
          >
            <td class="px-4 py-1.5">
              <span class="font-mono font-medium text-gray-200">{{ row.vlan_id }}</span>
            </td>
            <td class="px-2 py-1.5 text-gray-300 truncate max-w-[140px]" :title="row.hostname">
              {{ row.hostname }}
            </td>
            <td class="px-2 py-1.5 text-right font-mono" :class="row.is_default_priority ? 'text-amber-400' : 'text-gray-400'">
              {{ row.root_priority ?? '—' }}
            </td>
            <td class="px-2 py-1.5 text-center">
              <span v-if="row.is_default_priority" class="text-amber-400 text-xs" title="Default priority — root not hardened">⚠</span>
            </td>
          </tr>
        </tbody>
      </table>

      <!-- No filter results -->
      <div v-if="filteredRoots.length === 0" class="py-6 text-center text-gray-500 text-xs">
        No VLANs match "{{ search }}"
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'

const props = defineProps({
  devices: { type: Array, default: () => [] },
})

defineEmits(['close', 'device-selected'])

const search = ref('')
const sortKey = ref('vlan_id')
const sortAsc = ref(true)

function toggleSort(key) {
  if (sortKey.value === key) {
    sortAsc.value = !sortAsc.value
  } else {
    sortKey.value = key
    sortAsc.value = true
  }
}

function sortIcon(key) {
  if (sortKey.value !== key) return ''
  return sortAsc.value ? '↑' : '↓'
}

/** True when root priority is the Cisco default (32768 + VLAN ID). */
function isDefaultPriority(priorityStr, vlanId) {
  const p = parseInt(priorityStr)
  const v = parseInt(vlanId)
  if (isNaN(p) || isNaN(v)) return false
  return p === 32768 + v
}

/** Aggregate STP root bridge per VLAN from all devices' stp_info. */
const stpRoots = computed(() => {
  const roots = new Map()

  for (const device of props.devices) {
    for (const sv of (device.stp_info || [])) {
      if (!sv.is_root) continue
      // A device may claim root for the same VLAN as another (shouldn't happen, but take first)
      if (roots.has(sv.vlan_id)) continue
      roots.set(sv.vlan_id, {
        vlan_id: sv.vlan_id,
        hostname: device.hostname || device.id,
        device_id: device.id,
        root_priority: sv.root_priority,
        root_address: sv.root_address,
        is_default_priority: isDefaultPriority(sv.root_priority, sv.vlan_id),
      })
    }
  }

  return [...roots.values()]
})

const filteredRoots = computed(() => {
  const q = search.value.toLowerCase()
  let rows = q
    ? stpRoots.value.filter(
        r =>
          r.vlan_id.includes(q) ||
          r.hostname.toLowerCase().includes(q) ||
          (r.root_address || '').toLowerCase().includes(q),
      )
    : stpRoots.value

  rows = [...rows].sort((a, b) => {
    let va = a[sortKey.value] ?? ''
    let vb = b[sortKey.value] ?? ''
    if (sortKey.value === 'vlan_id' || sortKey.value === 'root_priority') {
      va = parseInt(va) || 0
      vb = parseInt(vb) || 0
      return sortAsc.value ? va - vb : vb - va
    }
    const dir = sortAsc.value ? 1 : -1
    return String(va).localeCompare(String(vb), undefined, { sensitivity: 'base' }) * dir
  })

  return rows
})
</script>
