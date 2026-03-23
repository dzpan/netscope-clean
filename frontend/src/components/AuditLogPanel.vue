<template>
  <div class="flex flex-col h-full overflow-hidden">
    <!-- Header -->
    <div class="flex items-center justify-between px-4 py-3 border-b border-gray-700 shrink-0">
      <div>
        <h2 class="font-semibold text-gray-100 font-display text-sm">Audit Log</h2>
        <p class="text-xs text-gray-500">{{ records.length }} change{{ records.length !== 1 ? 's' : '' }} recorded</p>
      </div>
      <div class="flex items-center gap-2">
        <!-- Export dropdown -->
        <div class="relative" ref="exportRef">
          <button
            class="btn-ghost btn-sm text-xs text-gray-400"
            @click="showExport = !showExport"
          >
            Export
          </button>
          <div
            v-if="showExport"
            class="absolute right-0 top-full mt-1 bg-gray-850 border border-gray-700 rounded shadow-md z-10 min-w-[120px]"
          >
            <button
              class="block w-full text-left px-3 py-1.5 text-xs text-gray-300 hover:bg-gray-700"
              @click="handleExport('csv')"
            >Export CSV</button>
            <button
              class="block w-full text-left px-3 py-1.5 text-xs text-gray-300 hover:bg-gray-700"
              @click="handleExport('json')"
            >Export JSON</button>
          </div>
        </div>
        <button class="btn-ghost p-1 text-gray-500 hover:text-gray-200" @click="$emit('close')">&#x2715;</button>
      </div>
    </div>

    <!-- Filters -->
    <div class="flex items-center gap-2 px-4 py-2 border-b border-gray-700/50 shrink-0">
      <select
        v-model="filterDevice"
        class="select text-xs bg-gray-800 border-gray-600 py-1"
        aria-label="Filter by device"
      >
        <option value="">All devices</option>
        <option v-for="d in uniqueDevices" :key="d" :value="d">{{ d }}</option>
      </select>
      <select
        v-model="filterStatus"
        class="select text-xs bg-gray-800 border-gray-600 py-1"
        aria-label="Filter by status"
      >
        <option value="">All statuses</option>
        <option value="success">Success</option>
        <option value="failed">Failed</option>
        <option value="rolled_back">Rolled Back</option>
      </select>
      <button
        v-if="filterDevice || filterStatus"
        class="text-xs text-gray-500 hover:text-gray-300"
        @click="filterDevice = ''; filterStatus = ''"
      >Clear</button>
      <button
        class="ml-auto btn-ghost btn-sm text-xs text-gray-400"
        title="Refresh audit log"
        @click="fetchRecords"
      >
        <svg class="w-3.5 h-3.5" :class="{ 'animate-spin': refreshing }" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
            d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/>
        </svg>
      </button>
    </div>

    <!-- Table -->
    <div class="flex-1 overflow-y-auto">
      <table v-if="filteredRecords.length" class="w-full text-xs">
        <thead class="sticky top-0 z-10">
          <tr class="text-gray-500 bg-gray-900 border-b border-gray-700">
            <th class="text-left px-3 py-2">ID</th>
            <th class="text-left px-3 py-2 cursor-pointer hover:text-gray-300" @click="toggleSort('timestamp')">
              Time {{ sortField === 'timestamp' ? (sortAsc ? '&#9650;' : '&#9660;') : '' }}
            </th>
            <th class="text-left px-3 py-2">Device</th>
            <th class="text-left px-3 py-2">Operation</th>
            <th class="text-left px-3 py-2">Status</th>
            <th class="text-left px-3 py-2">Action</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="rec in filteredRecords"
            :key="rec.id"
            class="border-b border-gray-800 hover:bg-gray-800/50 cursor-pointer"
            @click="$emit('view-detail', rec)"
          >
            <td class="px-3 py-2 font-mono text-gray-400">{{ shortId(rec.id) }}</td>
            <td class="px-3 py-2 text-gray-400">{{ formatTime(rec.timestamp) }}</td>
            <td class="px-3 py-2 font-mono text-gray-200">{{ rec.device_id }}</td>
            <td class="px-3 py-2">
              <span class="text-gray-300">{{ operationLabel(rec) }}</span>
            </td>
            <td class="px-3 py-2">
              <span :class="statusBadge(rec.status)" class="badge text-xs">{{ rec.status }}</span>
            </td>
            <td class="px-3 py-2">
              <button
                v-if="rec.status === 'success' && rec.rollback_available"
                class="btn-ghost btn-sm text-xs text-gray-400 hover:text-orange-400"
                title="Undo this change"
                @click.stop="$emit('undo', rec)"
              >Undo</button>
              <button
                v-else-if="rec.status === 'failed'"
                class="btn-ghost btn-sm text-xs text-gray-400 hover:text-orange-400"
                title="Retry this change"
                @click.stop="$emit('retry', rec)"
              >Retry</button>
              <span v-else-if="rec.status === 'rolled_back'" class="text-gray-600 text-xs">undone</span>
            </td>
          </tr>
        </tbody>
      </table>

      <!-- Empty state -->
      <div v-else class="flex flex-col items-center justify-center h-full text-gray-600 gap-2 py-12">
        <svg class="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5"
            d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/>
        </svg>
        <p class="text-xs">No audit records{{ filterDevice || filterStatus ? ' matching filters' : '' }}</p>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { listAuditRecords, exportAuditLog } from '../api.js'

const props = defineProps({
  /** Optional: filter to a single device */
  deviceId: { type: String, default: null },
})

/* eslint-disable no-unused-vars */
const emit = defineEmits(['close', 'view-detail', 'undo', 'retry'])
/* eslint-enable no-unused-vars */

const records = ref([])
const refreshing = ref(false)
const filterDevice = ref(props.deviceId || '')
const filterStatus = ref('')
const sortField = ref('timestamp')
const sortAsc = ref(false)
const showExport = ref(false)
const exportRef = ref(null)

const uniqueDevices = computed(() => {
  const set = new Set(records.value.map(r => r.device_id))
  return [...set].sort()
})

const filteredRecords = computed(() => {
  let list = records.value
  if (filterDevice.value) list = list.filter(r => r.device_id === filterDevice.value)
  if (filterStatus.value) list = list.filter(r => r.status === filterStatus.value)
  // Sort
  list = [...list].sort((a, b) => {
    const aVal = a[sortField.value] || ''
    const bVal = b[sortField.value] || ''
    const dir = sortAsc.value ? 1 : -1
    return String(aVal).localeCompare(String(bVal), undefined, { sensitivity: 'base' }) * dir
  })
  return list
})

function toggleSort(field) {
  if (sortField.value === field) {
    sortAsc.value = !sortAsc.value
  } else {
    sortField.value = field
    sortAsc.value = false
  }
}

async function fetchRecords() {
  refreshing.value = true
  try {
    const resp = await listAuditRecords({
      deviceId: props.deviceId || undefined,
      limit: 200,
    })
    records.value = resp.records || resp || []
  } catch {
    records.value = []
  } finally {
    refreshing.value = false
  }
}

function shortId(id) {
  if (!id) return '—'
  return id.length > 12 ? id.slice(0, 12) : id
}

function formatTime(ts) {
  if (!ts) return '—'
  const d = new Date(ts)
  const now = new Date()
  const isToday = d.toDateString() === now.toDateString()
  const time = d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  return isToday ? time + ' today' : d.toLocaleDateString([], { month: 'short', day: 'numeric' }) + ' ' + time
}

function operationLabel(rec) {
  if (!rec.changes?.length) return rec.operation || 'unknown'
  const c = rec.changes[0]
  const intfs = rec.changes.map(ch => ch.interface).join(', ')
  return `VLAN ${c.old_value}\u2192${c.new_value} ${intfs}`
}

function statusBadge(status) {
  const map = {
    success: 'bg-green-900/50 text-green-400',
    failed: 'bg-red-900/50 text-red-400',
    rolled_back: 'bg-orange-900/50 text-orange-400',
  }
  return map[status] || 'bg-gray-700 text-gray-400'
}

function handleExport(format) {
  exportAuditLog(format)
  showExport.value = false
}

// Watch for deviceId prop changes
watch(() => props.deviceId, () => {
  filterDevice.value = props.deviceId || ''
  fetchRecords()
})

onMounted(fetchRecords)
</script>

<style scoped>
.bg-gray-850 {
  background-color: var(--gray-850);
}
</style>
