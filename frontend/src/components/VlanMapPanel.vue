<template>
  <div class="flex flex-col h-full overflow-hidden">
    <!-- Header -->
    <div class="flex items-center justify-between px-4 py-3 border-b border-gray-700 shrink-0">
      <div>
        <h2 class="font-semibold text-gray-100">VLAN Map</h2>
        <p class="text-xs text-gray-400 mt-0.5">
          {{ vlanMap.length }} VLANs across {{ deviceCount }} devices
        </p>
      </div>
      <button class="btn-ghost p-1 text-gray-500 hover:text-gray-200" @click="$emit('close')">✕</button>
    </div>

    <!-- Search -->
    <div class="px-4 py-2 border-b border-gray-700 shrink-0">
      <input
        v-model="search"
        class="input text-xs py-1.5"
        placeholder="Filter by VLAN ID or name…"
        aria-label="Filter VLANs"
      />
    </div>

    <!-- Loading -->
    <div v-if="loading" class="flex-1 flex items-center justify-center">
      <svg class="animate-spin h-6 w-6 text-orange-400" viewBox="0 0 24 24" fill="none">
        <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"/>
        <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z"/>
      </svg>
    </div>

    <!-- VLAN Table -->
    <div v-else class="flex-1 overflow-y-auto">
      <table v-resizable-columns="'vlan-map'" class="w-full text-xs">
        <thead class="sticky top-0 bg-gray-900 z-10">
          <tr class="text-gray-500 border-b border-gray-700">
            <th class="text-left px-4 py-2 cursor-pointer hover:text-gray-300" @click="toggleSort('vlan_id')">
              VLAN {{ sortIcon('vlan_id') }}
            </th>
            <th class="text-left px-2 py-2 cursor-pointer hover:text-gray-300" @click="toggleSort('name')">
              Name {{ sortIcon('name') }}
            </th>
            <th class="text-center px-2 py-2 cursor-pointer hover:text-gray-300" @click="toggleSort('devices')">
              Devices {{ sortIcon('devices') }}
            </th>
            <th class="text-center px-2 py-2">Access</th>
            <th class="text-center px-2 py-2">Trunk</th>
            <th class="text-center px-2 py-2">Graph</th>
          </tr>
        </thead>
        <tbody>
          <template v-for="vlan in filteredVlans" :key="vlan.vlan_id">
            <tr
              class="border-b border-gray-800 hover:bg-gray-800/40 cursor-pointer"
              @click="toggle(vlan.vlan_id)"
            >
              <td class="px-4 py-1.5">
                <span class="font-mono font-medium text-gray-200">{{ vlan.vlan_id }}</span>
              </td>
              <td class="px-2 py-1.5 text-gray-400">{{ vlan.name || '—' }}</td>
              <td class="px-2 py-1.5 text-center">
                <span class="badge bg-gray-700 text-gray-300">{{ vlan.devices.length }}</span>
              </td>
              <td class="px-2 py-1.5 text-center text-gray-400">{{ vlan.access_ports }}</td>
              <td class="px-2 py-1.5 text-center text-gray-400">{{ vlan.trunk_ports }}</td>
              <td class="px-2 py-1.5 text-center">
                <button
                  class="text-xs px-1 py-0.5 rounded transition-colors"
                  :class="activeFilter === vlan.vlan_id
                    ? 'bg-orange-500/20 text-orange-400 border border-orange-500/30'
                    : 'text-gray-600 hover:text-gray-300'"
                  :title="activeFilter === vlan.vlan_id ? 'Clear filter' : 'Filter graph to this VLAN'"
                  @click.stop="toggleFilter(vlan.vlan_id)"
                >⊡</button>
              </td>
            </tr>
            <!-- Expanded row: device list -->
            <tr v-if="expanded.has(vlan.vlan_id)">
              <td colspan="6" class="px-4 py-2 bg-gray-900/60">
                <div class="flex flex-wrap gap-1.5">
                  <span
                    v-for="devId in vlan.devices"
                    :key="devId"
                    class="badge bg-gray-700 text-gray-300 cursor-pointer hover:bg-orange-900/50 hover:text-orange-300"
                    @click.stop="$emit('device-selected', devId)"
                  >
                    {{ devId }}
                  </span>
                </div>
              </td>
            </tr>
          </template>
          <tr v-if="filteredVlans.length === 0">
            <td colspan="6" class="px-4 py-6 text-center text-gray-600">
              {{ search ? `No VLANs match "${search}"` : 'No VLAN data available' }}
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import { getVlanMap } from '../api.js'

const props = defineProps({
  sessionId: { type: String, required: true },
})
const emit = defineEmits(['close', 'device-selected', 'vlan-filter'])

const activeFilter = ref(null)

function toggleFilter(vlanId) {
  const next = activeFilter.value === vlanId ? null : vlanId
  activeFilter.value = next
  emit('vlan-filter', next)
}

const vlanMap = ref([])
const loading = ref(false)
const search = ref('')
const expanded = ref(new Set())
const sortKey = ref('vlan_id')
const sortAsc = ref(true)

const deviceCount = computed(() => {
  const ids = new Set()
  for (const v of vlanMap.value) {
    for (const d of v.devices) ids.add(d)
  }
  return ids.size
})

const filteredVlans = computed(() => {
  let list = vlanMap.value
  if (search.value) {
    const q = search.value.toLowerCase()
    list = list.filter(v =>
      v.vlan_id.includes(q) || (v.name || '').toLowerCase().includes(q)
    )
  }
  // Sort
  const key = sortKey.value
  const dir = sortAsc.value ? 1 : -1
  return [...list].sort((a, b) => {
    if (key === 'vlan_id') {
      return dir * (parseInt(a.vlan_id) - parseInt(b.vlan_id))
    }
    if (key === 'name') {
      return dir * (a.name || '').localeCompare(b.name || '')
    }
    if (key === 'devices') {
      return dir * (a.devices.length - b.devices.length)
    }
    return 0
  })
})

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
  return sortAsc.value ? '▲' : '▼'
}

function toggle(vid) {
  const next = new Set(expanded.value)
  if (next.has(vid)) next.delete(vid)
  else next.add(vid)
  expanded.value = next
}

async function fetchMap() {
  loading.value = true
  try {
    vlanMap.value = await getVlanMap(props.sessionId)
  } catch (_e) {
    vlanMap.value = []
  } finally {
    loading.value = false
  }
}

watch(() => props.sessionId, () => {
  activeFilter.value = null
  emit('vlan-filter', null)
  fetchMap()
})
onMounted(fetchMap)
</script>
