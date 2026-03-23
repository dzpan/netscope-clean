<template>
  <div class="flex flex-col h-full overflow-hidden">
    <!-- Tab bar -->
    <div class="flex items-center gap-1 px-3 pt-2 border-b border-gray-700 shrink-0" role="tablist" aria-label="Device data tabs">
      <button
        v-for="tab in tabs"
        :key="tab.key"
        role="tab"
        :aria-selected="activeTab === tab.key"
        :aria-controls="`tabpanel-${tab.key}`"
        :tabindex="activeTab === tab.key ? 0 : -1"
        class="px-3 py-1.5 text-xs font-medium rounded-t border-b-2 transition-colors focus-visible:ring-2 focus-visible:ring-orange-500 focus-visible:ring-offset-1 focus-visible:ring-offset-gray-900 focus-visible:outline-none"
        :class="activeTab === tab.key
          ? 'border-orange-500 text-orange-400 bg-gray-800'
          : 'border-transparent text-gray-500 hover:text-gray-300'"
        @click="activeTab = tab.key"
        @keydown.left.prevent="switchTab(-1)"
        @keydown.right.prevent="switchTab(1)"
      >
        {{ tab.label }}
        <span class="ml-1.5 badge bg-gray-700 text-gray-400">{{ tab.count }}</span>
      </button>
      <div class="ml-auto flex items-center gap-2 pb-1">
        <select
          v-if="activeTab === 'devices'"
          v-model="hostnameCase"
          class="input py-0.5 text-xs w-auto bg-gray-800 text-gray-300 border-gray-600"
          aria-label="Hostname display case"
        >
          <option value="as-is">As-is</option>
          <option value="upper">UPPER</option>
          <option value="lower">lower</option>
        </select>
        <input
          v-model="search"
          class="input py-0.5 text-xs w-36"
          type="text"
          placeholder="Search…"
          aria-label="Filter table data"
        />
      </div>
    </div>

    <!-- Table body -->
    <div class="flex-1 overflow-y-auto overflow-x-auto">
      <!-- Devices -->
      <table v-if="activeTab === 'devices'" v-resizable-columns="'dt-devices'" class="w-full text-xs">
        <thead class="sticky top-0 bg-gray-900 z-10">
          <tr class="text-gray-500 border-b border-gray-700">
            <th v-for="col in deviceCols" :key="col.key"
              scope="col"
              class="text-left px-3 py-2 cursor-pointer hover:text-gray-300 select-none whitespace-nowrap"
              :aria-sort="sort.key === col.key ? (sort.asc ? 'ascending' : 'descending') : 'none'"
              @click="sortBy(col.key)"
            >
              {{ col.label }}
              <span v-if="sort.key === col.key" class="ml-1" aria-hidden="true">{{ sort.asc ? '↑' : '↓' }}</span>
            </th>
            <th scope="col" class="w-8"><span class="sr-only">Actions</span></th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="d in filteredDevices"
            :key="d.id"
            class="border-b border-gray-800 hover:bg-gray-800/50 cursor-pointer"
            @click="$emit('device-selected', d)"
          >
            <td class="px-3 py-1.5 font-mono text-gray-300">{{ formatHostname(d.hostname || d.id) }}</td>
            <td class="px-3 py-1.5 text-gray-400 font-mono">{{ d.mgmt_ip }}</td>
            <td class="px-3 py-1.5 text-gray-400">{{ d.platform || '—' }}</td>
            <td class="px-3 py-1.5 text-gray-400 font-mono text-xs">{{ d.serial || '—' }}</td>
            <td class="px-3 py-1.5">
              <span
                :class="statusBadge(d.status)"
                class="badge"
                :title="failureTooltip(d)"
              >{{ d.status }}</span>
            </td>
            <td class="px-3 py-1.5">
              <button
                v-if="d.status === 'ok'"
                class="text-xs text-gray-500 hover:text-orange-400"
                @click.stop="$emit('config-dump', d)"
              >⬇</button>
            </td>
          </tr>
          <tr v-if="!filteredDevices.length">
            <td colspan="6" class="px-3 py-4 text-center text-gray-600">No devices match</td>
          </tr>
        </tbody>
      </table>

      <!-- Links -->
      <table v-else-if="activeTab === 'links'" v-resizable-columns="'dt-links'" class="w-full text-xs">
        <thead class="sticky top-0 bg-gray-900 z-10">
          <tr class="text-gray-500 border-b border-gray-700">
            <th scope="col" class="text-left px-3 py-2">Source</th>
            <th scope="col" class="text-left px-3 py-2">Src Interface</th>
            <th scope="col" class="text-left px-3 py-2">Target</th>
            <th scope="col" class="text-left px-3 py-2">Tgt Interface</th>
            <th scope="col" class="text-left px-3 py-2">Protocol</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="(lk, i) in filteredLinks"
            :key="`${lk.source}-${lk.source_intf}-${lk.target}-${i}`"
            class="border-b border-gray-800 hover:bg-gray-800/50"
          >
            <td class="px-3 py-1.5 font-mono text-gray-300">{{ lk.source }}</td>
            <td class="px-3 py-1.5 font-mono text-gray-500">{{ lk.source_intf }}</td>
            <td class="px-3 py-1.5 font-mono text-gray-300">{{ lk.target }}</td>
            <td class="px-3 py-1.5 font-mono text-gray-500">{{ lk.target_intf || '—' }}</td>
            <td class="px-3 py-1.5">
              <span :class="lk.protocol === 'CDP' ? 'text-orange-400' : 'text-purple-400'">{{ lk.protocol }}</span>
            </td>
          </tr>
          <tr v-if="!filteredLinks.length">
            <td colspan="5" class="px-3 py-4 text-center text-gray-600">No links match</td>
          </tr>
        </tbody>
      </table>

      <!-- Failures -->
      <table v-else v-resizable-columns="'dt-failures'" class="w-full text-xs">
        <thead class="sticky top-0 bg-gray-900 z-10">
          <tr class="text-gray-500 border-b border-gray-700">
            <th scope="col" class="text-left px-3 py-2">Target</th>
            <th scope="col" class="text-left px-3 py-2">Reason</th>
            <th scope="col" class="text-left px-3 py-2">Detail</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="(f, i) in filteredFailures"
            :key="i"
            class="border-b border-gray-800 hover:bg-gray-800/50"
          >
            <td class="px-3 py-1.5 font-mono text-gray-300">{{ f.target }}</td>
            <td class="px-3 py-1.5">
              <span :class="reasonBadge(f.reason)" class="badge">{{ f.reason }}</span>
            </td>
            <td class="px-3 py-1.5 text-gray-500 truncate max-w-xs" :title="f.detail">{{ f.detail || '—' }}</td>
          </tr>
          <tr v-if="!filteredFailures.length">
            <td colspan="3" class="px-3 py-4 text-center text-gray-600">No failures</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'

const props = defineProps({
  devices: { type: Array, default: () => [] },
  links: { type: Array, default: () => [] },
  failures: { type: Array, default: () => [] },
})
defineEmits(['device-selected', 'config-dump'])

const activeTab = ref('devices')
const search = ref('')
const sort = ref({ key: 'hostname', asc: true })
const hostnameCase = ref('as-is') // 'as-is' | 'upper' | 'lower'

function formatHostname(name) {
  if (!name) return ''
  if (hostnameCase.value === 'upper') return name.toUpperCase()
  if (hostnameCase.value === 'lower') return name.toLowerCase()
  return name
}

const tabs = computed(() => [
  { key: 'devices', label: 'Devices', count: props.devices.length },
  { key: 'links', label: 'Links', count: props.links.length },
  { key: 'failures', label: 'Failures', count: props.failures.length },
])

function switchTab(dir) {
  const keys = tabs.value.map(t => t.key)
  const idx = keys.indexOf(activeTab.value)
  const next = (idx + dir + keys.length) % keys.length
  activeTab.value = keys[next]
}

const deviceCols = [
  { key: 'hostname', label: 'Hostname' },
  { key: 'mgmt_ip', label: 'IP' },
  { key: 'platform', label: 'Platform' },
  { key: 'serial', label: 'Serial' },
  { key: 'status', label: 'Status' },
]

function sortBy(key) {
  if (sort.value.key === key) sort.value.asc = !sort.value.asc
  else { sort.value.key = key; sort.value.asc = true }
}

const filteredDevices = computed(() => {
  const q = search.value.toLowerCase()
  let list = props.devices.filter(d =>
    !q || [d.hostname, d.id, d.mgmt_ip, d.platform, d.serial, d.status].some(v => v?.toLowerCase().includes(q))
  )
  const key = sort.value.key
  list = [...list].sort((a, b) => {
    const av = (a[key] || '').toLowerCase()
    const bv = (b[key] || '').toLowerCase()
    return sort.value.asc ? av.localeCompare(bv) : bv.localeCompare(av)
  })
  return list
})

const filteredLinks = computed(() => {
  const q = search.value.toLowerCase()
  return props.links.filter(lk =>
    !q || [lk.source, lk.target, lk.source_intf, lk.target_intf].some(v => v?.toLowerCase().includes(q))
  )
})

const filteredFailures = computed(() => {
  const q = search.value.toLowerCase()
  return props.failures.filter(f =>
    !q || [f.target, f.reason, f.detail].some(v => v?.toLowerCase().includes(q))
  )
})

const failuresByTarget = computed(() => {
  const map = {}
  for (const f of props.failures) {
    if (f.target && !map[f.target]) map[f.target] = f
  }
  return map
})

function failureTooltip(device) {
  if (device.status !== 'placeholder') return undefined
  const f = failuresByTarget.value[device.mgmt_ip] || failuresByTarget.value[device.id]
  if (!f) return undefined
  return f.detail ? `${f.reason}: ${f.detail}` : f.reason
}

function statusBadge(status) {
  const map = {
    ok: 'bg-green-900/50 text-green-400',
    placeholder: 'bg-gray-700 text-gray-400',
    unreachable: 'bg-red-900/50 text-red-400',
    auth_failed: 'bg-amber-900/50 text-amber-400',
    timeout: 'bg-amber-900/50 text-amber-400',
    no_cdp_lldp: 'bg-purple-900/50 text-purple-400',
  }
  return map[status] || 'bg-gray-700 text-gray-400'
}

function reasonBadge(reason) {
  const map = {
    unreachable: 'bg-red-900/50 text-red-400',
    auth_failed: 'bg-orange-900/50 text-orange-400',
    timeout: 'bg-orange-900/50 text-orange-400',
    no_cdp_lldp: 'bg-purple-900/50 text-purple-400',
    unknown: 'bg-gray-700 text-gray-400',
  }
  return map[reason] || 'bg-gray-700 text-gray-400'
}
</script>
