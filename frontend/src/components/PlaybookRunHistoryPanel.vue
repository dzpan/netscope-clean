<template>
  <div class="flex flex-col h-full overflow-hidden">
    <!-- Header -->
    <div class="flex items-center justify-between px-4 py-3 border-b border-gray-700 shrink-0">
      <div>
        <h2 class="font-semibold text-gray-100 font-display text-sm">Playbook Runs</h2>
        <p class="text-xs text-gray-500">{{ runs.length }} execution{{ runs.length !== 1 ? 's' : '' }}</p>
      </div>
      <div class="flex items-center gap-2">
        <button
          class="btn-ghost btn-sm text-xs text-gray-400"
          title="Back to library"
          @click="$emit('back')"
        >&larr; Library</button>
        <button class="btn-ghost p-1 text-gray-500 hover:text-gray-200" @click="$emit('close')">&#x2715;</button>
      </div>
    </div>

    <!-- Filters -->
    <div class="flex items-center gap-2 px-4 py-2 border-b border-gray-700/50 shrink-0">
      <select
        v-model="filterStatus"
        class="select text-xs bg-gray-800 border-gray-600 py-1"
      >
        <option value="">All statuses</option>
        <option value="success">Success</option>
        <option value="failed">Failed</option>
        <option value="running">Running</option>
      </select>
      <select
        v-model="filterDevice"
        class="select text-xs bg-gray-800 border-gray-600 py-1"
      >
        <option value="">All devices</option>
        <option v-for="d in uniqueDevices" :key="d" :value="d">{{ d }}</option>
      </select>
      <button
        v-if="filterStatus || filterDevice"
        class="text-xs text-gray-500 hover:text-gray-300"
        @click="filterStatus = ''; filterDevice = ''"
      >Clear</button>
      <button
        class="ml-auto btn-ghost btn-sm text-xs text-gray-400"
        title="Refresh"
        @click="fetchRuns"
      >
        <svg class="w-3.5 h-3.5" :class="{ 'animate-spin': refreshing }" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
            d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/>
        </svg>
      </button>
    </div>

    <!-- Runs table -->
    <div class="flex-1 overflow-y-auto">
      <div v-if="refreshing && runs.length === 0" class="flex items-center justify-center py-12 text-gray-500">
        <svg class="animate-spin w-5 h-5 mr-2" viewBox="0 0 24 24" fill="none">
          <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"/>
          <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z"/>
        </svg>
        Loading…
      </div>

      <table v-else-if="filteredRuns.length" class="w-full text-xs">
        <thead class="sticky top-0 z-10">
          <tr class="text-gray-500 bg-gray-900 border-b border-gray-700">
            <th class="text-left px-3 py-2">Time</th>
            <th class="text-left px-3 py-2">Playbook</th>
            <th class="text-left px-3 py-2">Device(s)</th>
            <th class="text-left px-3 py-2">Status</th>
            <th class="text-left px-3 py-2">Action</th>
          </tr>
        </thead>
        <tbody>
          <template v-for="run in filteredRuns" :key="run.id">
            <tr
              class="border-b border-gray-800 hover:bg-gray-800/50 cursor-pointer"
              @click="toggleExpanded(run.id)"
            >
              <td class="px-3 py-2 text-gray-400">{{ formatTime(run.timestamp || run.created_at) }}</td>
              <td class="px-3 py-2 text-gray-200">{{ run.playbook_title || run.playbook_id?.slice(0, 8) }}</td>
              <td class="px-3 py-2 font-mono text-gray-300">
                {{ (run.device_ids || []).length }} device{{ (run.device_ids || []).length !== 1 ? 's' : '' }}
              </td>
              <td class="px-3 py-2">
                <span :class="statusBadge(run.status)" class="badge text-xs">{{ run.status }}</span>
              </td>
              <td class="px-3 py-2 flex items-center gap-1">
                <button
                  v-if="run.status === 'success' && run.undo_available !== false"
                  class="btn-ghost btn-sm text-xs text-gray-400 hover:text-orange-400"
                  title="Undo this execution"
                  @click.stop="$emit('undo', run)"
                >Undo</button>
                <button
                  v-if="run.device_results?.some(d => Object.keys(d.pre_check_outputs || {}).length || Object.keys(d.post_check_outputs || {}).length)"
                  class="btn-ghost btn-sm text-xs text-gray-400 hover:text-cyan-400"
                  title="View config diff"
                  @click.stop="fetchDiff(run.id)"
                >Diff</button>
              </td>
            </tr>
            <!-- Expanded detail row -->
            <tr v-if="expandedId === run.id">
              <td colspan="5" class="px-3 py-3 bg-gray-800/30 border-b border-gray-800">
                <div class="flex flex-col gap-2">
                  <div v-if="run.variables && Object.keys(run.variables).length" class="text-xs">
                    <span class="text-gray-500">Variables: </span>
                    <span
                      v-for="(val, key) in run.variables"
                      :key="key"
                      class="inline-block mr-2"
                    >
                      <span class="font-mono text-orange-400">{{ key }}</span>=<span class="font-mono text-gray-300">{{ val }}</span>
                    </span>
                  </div>
                  <div v-if="run.device_results?.length" class="space-y-1">
                    <div
                      v-for="dr in run.device_results"
                      :key="dr.device_id"
                      class="flex items-center gap-2 text-xs"
                    >
                      <span :class="dr.status === 'success' ? 'text-green-400' : 'text-red-400'">
                        {{ dr.status === 'success' ? '&#x2713;' : '&#x2717;' }}
                      </span>
                      <span class="font-mono text-gray-300">{{ dr.device_id }}</span>
                      <span v-if="dr.error" class="text-red-400 truncate">{{ dr.error }}</span>
                    </div>
                  </div>
                  <!-- Config Diff Viewer -->
                  <div v-if="diffData?.run_id === run.id" class="mt-2 border-t border-gray-700 pt-2">
                    <p class="text-xs text-gray-500 mb-1 font-medium">Config Diff (pre vs post)</p>
                    <div v-if="diffLoading" class="text-xs text-gray-500">Loading diff...</div>
                    <div v-else-if="diffData.device_diffs?.length">
                      <div
                        v-for="dd in diffData.device_diffs"
                        :key="dd.device_id"
                        class="mb-2"
                      >
                        <p class="text-xs text-gray-400 font-mono mb-0.5">{{ dd.device_id }} ({{ dd.device_ip }})</p>
                        <div v-if="Object.keys(dd.commands || {}).length">
                          <div v-for="(diff, cmd) in dd.commands" :key="cmd" class="mb-1">
                            <p class="text-xs text-gray-500 font-mono">$ {{ cmd }}</p>
                            <pre class="text-xs font-mono bg-gray-950 rounded p-2 overflow-x-auto whitespace-pre max-h-40 overflow-y-auto"><template v-for="(line, li) in diff.split('\n')" :key="li"><span :class="line.startsWith('+') ? 'text-green-400' : line.startsWith('-') ? 'text-red-400' : line.startsWith('@') ? 'text-cyan-400' : 'text-gray-500'">{{ line }}
</span></template></pre>
                          </div>
                        </div>
                        <p v-else class="text-xs text-gray-600 italic">No changes detected</p>
                      </div>
                    </div>
                    <p v-else class="text-xs text-gray-600 italic">No diff data available</p>
                  </div>
                </div>
              </td>
            </tr>
          </template>
        </tbody>
      </table>

      <!-- Empty state -->
      <div v-else class="flex flex-col items-center justify-center h-full text-gray-600 gap-2 py-12">
        <svg class="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5"
            d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"/>
        </svg>
        <p class="text-xs">No playbook runs{{ filterStatus || filterDevice ? ' matching filters' : ' yet' }}</p>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { listPlaybookRuns, diffPlaybookRun } from '../api.js'

defineProps({})
/* eslint-disable no-unused-vars */
const emit = defineEmits(['close', 'back', 'undo'])
/* eslint-enable no-unused-vars */

const runs = ref([])
const refreshing = ref(false)
const filterStatus = ref('')
const filterDevice = ref('')
const expandedId = ref(null)
const diffData = ref(null)
const diffLoading = ref(false)

const uniqueDevices = computed(() => {
  const set = new Set()
  for (const r of runs.value) {
    for (const d of (r.device_ids || [])) set.add(d)
  }
  return [...set].sort()
})

const filteredRuns = computed(() => {
  let list = runs.value
  if (filterStatus.value) list = list.filter(r => r.status === filterStatus.value)
  if (filterDevice.value) list = list.filter(r => (r.device_ids || []).includes(filterDevice.value))
  return list
})

function toggleExpanded(id) {
  expandedId.value = expandedId.value === id ? null : id
}

function statusBadge(status) {
  const map = {
    success: 'bg-green-900/50 text-green-400',
    failed: 'bg-red-900/50 text-red-400',
    running: 'bg-orange-900/50 text-orange-400',
  }
  return map[status] || 'bg-gray-700 text-gray-400'
}

function formatTime(ts) {
  if (!ts) return '\u2014'
  const d = new Date(ts)
  const now = new Date()
  const isToday = d.toDateString() === now.toDateString()
  const time = d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  return isToday ? time + ' today' : d.toLocaleDateString([], { month: 'short', day: 'numeric' }) + ' ' + time
}

async function fetchRuns() {
  refreshing.value = true
  try {
    const resp = await listPlaybookRuns({ limit: 100 })
    runs.value = resp.runs || resp || []
  } catch {
    runs.value = []
  } finally {
    refreshing.value = false
  }
}

async function fetchDiff(runId) {
  if (diffData.value?.run_id === runId) {
    diffData.value = null
    return
  }
  diffLoading.value = true
  try {
    diffData.value = await diffPlaybookRun(runId)
  } catch {
    diffData.value = null
  } finally {
    diffLoading.value = false
  }
}

defineExpose({ refresh: fetchRuns })

onMounted(fetchRuns)
</script>
