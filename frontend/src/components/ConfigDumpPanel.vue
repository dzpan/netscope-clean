<template>
  <div class="flex flex-col h-full overflow-hidden">

    <!-- Header -->
    <div v-if="showHeader" class="flex items-center justify-between px-4 py-3 border-b border-gray-700 shrink-0">
      <div>
        <h2 class="font-semibold text-gray-100">Config Dump</h2>
        <p class="text-xs text-gray-400 mt-0.5">{{ device?.hostname || device?.mgmt_ip }}</p>
      </div>
      <button class="btn-ghost p-1 text-gray-500 hover:text-gray-200" @click="$emit('close')">✕</button>
    </div>

    <!-- Credentials + Run -->
    <div class="px-4 py-3 border-b border-gray-700 shrink-0 flex flex-col gap-2">
      <!-- Credential set selector (when sets are available) -->
      <div v-if="credentialSets.length > 0" class="flex flex-col gap-1">
        <label class="label">Credential Set</label>
        <select v-model="selectedSetIndex" class="input text-xs py-1.5">
          <option :value="-1">Manual entry</option>
          <option v-for="(s, idx) in credentialSets" :key="idx" :value="idx">
            {{ s.label || s.username }}{{ s.auth_type === 'ssh_key' ? ' (key)' : '' }}
          </option>
          <option :value="-2">All sets (try in order)</option>
        </select>
      </div>

      <div class="grid grid-cols-2 gap-2">
        <div>
          <label class="label">Username</label>
          <input v-model="creds.username" type="text" class="input text-xs" autocomplete="username"
            :disabled="selectedSetIndex === -2" :class="{ 'opacity-50': selectedSetIndex === -2 }" />
        </div>
        <div>
          <label class="label">Password</label>
          <input v-model="creds.password" type="password" class="input text-xs"
            :disabled="selectedSetIndex === -2" :class="{ 'opacity-50': selectedSetIndex === -2 }" />
        </div>
        <div>
          <label class="label">Enable Password <span class="text-gray-600">(opt)</span></label>
          <input v-model="creds.enable_password" type="password" class="input text-xs"
            :disabled="selectedSetIndex === -2" :class="{ 'opacity-50': selectedSetIndex === -2 }" />
        </div>
        <div class="flex items-end">
          <button
            class="btn-primary w-full text-xs py-2"
            :disabled="running || (!canRun)"
            @click="runDump"
          >
            <span v-if="running" class="flex items-center justify-center gap-1.5">
              <svg class="animate-spin h-3 w-3" viewBox="0 0 24 24" fill="none">
                <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"/>
                <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z"/>
              </svg>
              Running…
            </span>
            <span v-else>▶ Run Dump</span>
          </button>
        </div>
      </div>
      <p v-if="selectedSetIndex === -2" class="text-xs text-gray-500">
        All {{ credentialSets.length }} credential sets will be tried in order until one succeeds.
      </p>
      <div v-if="runError" class="text-xs text-red-400 bg-red-900/20 border border-red-800 rounded p-2">
        {{ runError }}
      </div>
    </div>

    <!-- Tab: current dump | history -->
    <div class="flex border-b border-gray-700 shrink-0">
      <button
        v-for="tab in ['output', 'history']"
        :key="tab"
        class="px-4 py-2 text-xs font-medium capitalize border-b-2 transition-colors"
        :class="activeTab === tab
          ? 'border-orange-500 text-orange-400'
          : 'border-transparent text-gray-500 hover:text-gray-300'"
        @click="activeTab = tab"
      >
        {{ tab === 'output' ? 'Output' : 'History' }}
        <span v-if="tab === 'history' && history.length" class="ml-1 badge bg-gray-700 text-gray-400">{{ history.length }}</span>
      </button>

      <!-- Download button (when output is shown) -->
      <div v-if="activeTab === 'output' && currentDump" class="ml-auto flex items-center pr-3 gap-2">
        <span class="text-xs text-gray-600">{{ formatDate(currentDump.dumped_at) }}</span>
        <button class="btn-secondary text-xs py-0.5 px-2" @click="downloadDump(currentDump.dump_id)">
          ↓ .txt
        </button>
      </div>
    </div>

    <!-- OUTPUT TAB -->
    <div v-if="activeTab === 'output'" class="flex-1 overflow-hidden flex flex-col">
      <!-- No dump yet -->
      <div v-if="!currentDump && !running" class="flex-1 flex items-center justify-center text-gray-600 text-sm">
        Enter credentials and click Run Dump
      </div>

      <!-- Running placeholder -->
      <div v-else-if="running" class="flex-1 flex flex-col items-center justify-center gap-3 text-gray-500">
        <svg class="animate-spin h-8 w-8 text-orange-500" viewBox="0 0 24 24" fill="none">
          <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"/>
          <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z"/>
        </svg>
        <p class="text-sm">Collecting show commands…</p>
        <p class="text-xs text-gray-600">This takes 30–60 seconds</p>
      </div>

      <!-- Dump results -->
      <template v-else-if="currentDump">
        <!-- Search -->
        <div class="px-3 py-2 border-b border-gray-800 shrink-0">
          <input v-model="search" class="input text-xs py-1" placeholder="Search output…" aria-label="Search config output" />
        </div>

        <!-- Command sections -->
        <div class="flex-1 overflow-y-auto">
          <div
            v-for="cmd in filteredCommands"
            :key="cmd.command"
            class="border-b border-gray-800"
          >
            <!-- Section header -->
            <button
              class="w-full flex items-center justify-between px-3 py-2 hover:bg-gray-800/50 text-left"
              @click="toggleSection(cmd.command)"
            >
              <span class="font-mono text-xs text-orange-400">{{ cmd.command }}</span>
              <div class="flex items-center gap-2">
                <span v-if="cmd.error" class="badge bg-red-900/50 text-red-400 text-xs">error</span>
                <span v-else-if="!cmd.output" class="badge bg-gray-700 text-gray-500 text-xs">empty</span>
                <span v-else class="text-xs text-gray-600">{{ cmd.output.split('\n').length }} lines</span>
                <span class="text-gray-600 text-xs">{{ collapsed.has(cmd.command) ? '▶' : '▼' }}</span>
              </div>
            </button>

            <!-- Section body -->
            <div v-if="!collapsed.has(cmd.command)" class="bg-gray-950 px-3 pb-3">
              <pre v-if="cmd.error" class="text-xs text-red-400 whitespace-pre-wrap">{{ cmd.error }}</pre>
              <pre v-else-if="cmd.output" class="text-xs text-gray-300 whitespace-pre-wrap font-mono leading-5">{{ highlightSearch(cmd.output) }}</pre>
              <p v-else class="text-xs text-gray-600 italic py-1">No output</p>
            </div>
          </div>

          <div v-if="filteredCommands.length === 0" class="p-4 text-center text-gray-600 text-sm">
            No commands match "{{ search }}"
          </div>
        </div>
      </template>
    </div>

    <!-- HISTORY TAB -->
    <div v-else class="flex-1 overflow-y-auto">
      <div v-if="!history.length" class="flex items-center justify-center h-32 text-gray-600 text-sm">
        No dumps yet for this device
      </div>
      <div
        v-for="d in history"
        :key="d.dump_id"
        class="flex items-center px-4 py-2.5 border-b border-gray-800 hover:bg-gray-800/40 gap-3"
      >
        <div class="flex-1 min-w-0">
          <p class="text-xs font-mono text-gray-300">{{ formatDate(d.dumped_at) }}</p>
          <p class="text-xs text-gray-600">{{ d.commands.filter(c => !c.error && c.output).length }} / {{ d.commands.length }} commands</p>
        </div>
        <button class="btn-ghost text-xs px-2 py-1" @click="loadDump(d)">View</button>
        <button class="btn-ghost text-xs px-2 py-1" @click="downloadDump(d.dump_id)">↓</button>
      </div>
    </div>

  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { createConfigDump, listConfigDumps, downloadConfigDump } from '../api.js'

const props = defineProps({
  device: { type: Object, default: null },
  initialCreds: { type: Object, default: () => ({ username: '', password: '', enable_password: '' }) },
  credentialSets: { type: Array, default: () => [] },
  showHeader: { type: Boolean, default: true },
})
defineEmits(['close'])

const creds = ref({ ...props.initialCreds })
const running = ref(false)
const runError = ref(null)
const currentDump = ref(null)
const history = ref([])
const activeTab = ref('output')
const search = ref('')
const collapsed = ref(new Set())
// -1 = manual, -2 = all sets, 0..N = specific set index
const selectedSetIndex = ref(props.credentialSets.length > 0 ? -2 : -1)

// When a specific set is picked, populate the creds fields
watch(selectedSetIndex, (idx) => {
  if (idx >= 0 && idx < props.credentialSets.length) {
    const s = props.credentialSets[idx]
    creds.value = { username: s.username || '', password: s.password || '', enable_password: s.enable_password || '' }
  }
})

const canRun = computed(() => {
  if (selectedSetIndex.value === -2) return props.credentialSets.length > 0
  return creds.value.username && creds.value.password
})

// Sync creds when prop changes
watch(() => props.initialCreds, (v) => { creds.value = { ...v } }, { deep: true })

// Reload history when device changes
watch(() => props.device, async (d) => {
  if (!d) return
  currentDump.value = null
  search.value = ''
  activeTab.value = 'output'
  await loadHistory()
}, { immediate: true })

async function loadHistory() {
  if (!props.device) return
  try {
    history.value = await listConfigDumps(props.device.hostname || props.device.id)
  } catch (_err) {
    history.value = []
  }
}

async function runDump() {
  if (!props.device) return
  running.value = true
  runError.value = null
  currentDump.value = null
  collapsed.value = new Set()
  try {
    const payload = {
      device_ip: props.device.mgmt_ip,
      device_id: props.device.hostname || props.device.id,
    }
    if (selectedSetIndex.value === -2) {
      // Send all credential sets — backend tries each in order
      payload.credential_sets = props.credentialSets
    } else {
      // Single credential (manual entry or specific set)
      payload.credential_sets = [{
        username: creds.value.username,
        password: creds.value.password,
        enable_password: creds.value.enable_password || null,
      }]
    }
    const dump = await createConfigDump(payload)
    currentDump.value = dump
    activeTab.value = 'output'
    await loadHistory()
    // Auto-collapse empty/error sections
    for (const cmd of dump.commands) {
      if (!cmd.output || cmd.error) collapsed.value.add(cmd.command)
    }
  } catch (e) {
    runError.value = e.message || 'Dump failed'
  } finally {
    running.value = false
  }
}

function loadDump(d) {
  currentDump.value = d
  activeTab.value = 'output'
  collapsed.value = new Set()
  for (const cmd of d.commands) {
    if (!cmd.output || cmd.error) collapsed.value.add(cmd.command)
  }
}

function toggleSection(cmd) {
  if (collapsed.value.has(cmd)) collapsed.value.delete(cmd)
  else collapsed.value.add(cmd)
  collapsed.value = new Set(collapsed.value) // trigger reactivity
}

function downloadDump(dumpId) {
  downloadConfigDump(dumpId)
}

const filteredCommands = computed(() => {
  if (!currentDump.value) return []
  const q = search.value.toLowerCase()
  if (!q) return currentDump.value.commands
  return currentDump.value.commands.filter(cmd =>
    cmd.command.toLowerCase().includes(q) ||
    cmd.output?.toLowerCase().includes(q) ||
    cmd.error?.toLowerCase().includes(q)
  )
})

function highlightSearch(text) {
  // Plain text for now — browser Ctrl+F handles in-page search
  return text
}

function formatDate(iso) {
  return new Date(iso).toLocaleString(undefined, {
    month: 'short', day: 'numeric',
    hour: '2-digit', minute: '2-digit', second: '2-digit',
  })
}
</script>
