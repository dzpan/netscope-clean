<template>
  <div class="flex flex-col h-full overflow-hidden">
    <!-- Header -->
    <div class="panel-header">
      <div class="flex items-center gap-2">
        <svg class="w-4 h-4 text-orange-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
            d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.066 2.573c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.573 1.066c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.066-2.573c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
        </svg>
        <h3 class="panel-title">Settings</h3>
      </div>
      <button class="btn-ghost p-1" @click="$emit('close')" title="Close">
        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
        </svg>
      </button>
    </div>

    <!-- Tabs -->
    <div class="tab-bar">
      <button
        v-for="tab in tabs"
        :key="tab.key"
        class="tab-item"
        :class="{ active: activeTab === tab.key }"
        @click="activeTab = tab.key"
      >
        {{ tab.label }}
      </button>
    </div>

    <!-- Loading state -->
    <div v-if="loadingSettings" class="flex-1 flex items-center justify-center">
      <svg class="animate-spin h-6 w-6 text-orange-500" viewBox="0 0 24 24" fill="none">
        <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"/>
        <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z"/>
      </svg>
    </div>

    <!-- Tab content -->
    <div v-else class="flex-1 overflow-y-auto">

      <!-- ============================================================
           DISCOVERY TAB
           ============================================================ -->
      <div v-if="activeTab === 'discovery'" class="p-4 flex flex-col gap-4">
        <p class="text-xs text-gray-500">Default discovery parameters. These are used as defaults when starting a new scan.</p>

        <div class="grid grid-cols-2 gap-3">
          <div>
            <label class="label">SSH Timeout (seconds)</label>
            <input
              v-model.number="form.discovery.timeout"
              class="input"
              type="number"
              min="5"
              max="120"
            />
            <OverrideBadge v-if="overrides.timeout" />
          </div>
          <div>
            <label class="label">Max Concurrent Connections</label>
            <input
              v-model.number="form.discovery.max_concurrency"
              class="input"
              type="number"
              min="1"
              max="50"
            />
            <OverrideBadge v-if="overrides.max_concurrency" />
          </div>
          <div>
            <label class="label">BFS Max Hops</label>
            <input
              v-model.number="form.discovery.max_hops"
              class="input"
              type="number"
              min="0"
              max="20"
            />
          </div>
          <div>
            <label class="label">Discovery Protocol</label>
            <select v-model="form.discovery.discovery_protocol" class="select">
              <option value="cdp_prefer">CDP Prefer</option>
              <option value="lldp_prefer">LLDP Prefer</option>
              <option value="both">Both</option>
            </select>
          </div>
        </div>

        <div>
          <label class="label">Default Scope (CIDR)</label>
          <input
            v-model="form.discovery.scope"
            class="input font-mono"
            type="text"
            placeholder="e.g. 10.0.0.0/8 (leave blank for no restriction)"
          />
        </div>

        <label class="flex items-start gap-3 p-2.5 rounded-lg border cursor-pointer transition-colors"
          :class="form.discovery.auto_follow
            ? 'border-orange-500 bg-orange-900/20'
            : 'border-gray-700 bg-gray-900/20 hover:border-gray-600'"
        >
          <input v-model="form.discovery.auto_follow" type="checkbox" class="accent-orange-500 w-4 h-4 mt-0.5 shrink-0" />
          <div>
            <p class="text-sm font-medium" :class="form.discovery.auto_follow ? 'text-orange-300' : 'text-gray-300'">Auto-follow all neighbors</p>
            <p class="text-xs text-gray-500 mt-0.5">Automatically traverse the full network via CDP/LLDP from seed devices.</p>
          </div>
        </label>
      </div>

      <!-- ============================================================
           CREDENTIALS TAB
           ============================================================ -->
      <div v-if="activeTab === 'credentials'" class="p-4 flex flex-col gap-4">
        <div class="flex items-center justify-between">
          <p class="text-xs text-gray-500">Saved credential profiles for SSH access. Tried in order during discovery.</p>
          <button class="btn-secondary btn-sm" @click="addCredentialProfile">+ Add Profile</button>
        </div>

        <div v-if="form.credential_profiles.length === 0" class="empty-state">
          <svg class="empty-state-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5"
              d="M15 7a2 2 0 012 2m4 0a6 6 0 01-7.743 5.743L11 17H9v2H7v2H4a1 1 0 01-1-1v-2.586a1 1 0 01.293-.707l5.964-5.964A6 6 0 1121 9z" />
          </svg>
          <p class="empty-state-title">No credential profiles</p>
          <p class="empty-state-description">Add a credential profile to get started with discovery.</p>
        </div>

        <div
          v-for="(cred, i) in form.credential_profiles"
          :key="cred._id"
          class="card p-4 flex flex-col gap-3"
        >
          <div class="flex items-center justify-between">
            <span class="text-sm font-medium text-gray-200">
              {{ cred.label || `Profile ${i + 1}` }}
            </span>
            <div class="flex items-center gap-2">
              <button
                class="text-xs text-gray-500 hover:text-orange-400 transition-colors"
                title="Test connectivity"
                @click="testCredentialProfile(cred)"
              >
                Test
              </button>
              <button
                class="text-xs text-gray-500 hover:text-red-400 transition-colors"
                @click="removeCredentialProfile(i)"
              >
                Remove
              </button>
            </div>
          </div>

          <input
            v-model="cred.label"
            class="input text-xs"
            type="text"
            placeholder="Profile name (e.g. Core Switches, APs)"
          />
          <div class="grid grid-cols-2 gap-2">
            <input
              v-model="cred.username"
              class="input text-xs"
              type="text"
              placeholder="Username"
              autocomplete="off"
            />
            <input
              v-model="cred.password"
              class="input text-xs"
              type="password"
              placeholder="Password"
              autocomplete="off"
            />
          </div>
          <input
            v-model="cred.enable_password"
            class="input text-xs"
            type="password"
            placeholder="Enable password (optional)"
            autocomplete="off"
          />

          <!-- Test result -->
          <div v-if="cred._testResult" class="text-xs rounded px-2 py-1.5"
            :class="cred._testResult.success ? 'bg-green-900/30 text-green-400' : 'bg-red-900/30 text-red-400'"
          >
            <span v-if="cred._testResult.success">
              ✓ Connected — {{ cred._testResult.hostname || 'OK' }}
            </span>
            <span v-else>✗ {{ cred._testResult.error || 'Connection failed' }}</span>
          </div>
          <div v-if="cred._testing" class="flex items-center gap-2 text-xs text-gray-400">
            <svg class="animate-spin w-3 h-3" viewBox="0 0 24 24" fill="none">
              <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"/>
              <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z"/>
            </svg>
            Testing…
          </div>
        </div>
      </div>

      <!-- ============================================================
           COLLECTION PROFILES TAB
           ============================================================ -->
      <div v-if="activeTab === 'profiles'" class="p-4 flex flex-col gap-4">
        <p class="text-xs text-gray-500">Default collection profile determines which data groups are gathered during discovery.</p>

        <div class="flex flex-col gap-2">
          <label
            v-for="p in profileOptions"
            :key="p.value"
            class="flex items-start gap-3 p-3 rounded-lg border cursor-pointer transition-colors"
            :class="form.collection_profile === p.value
              ? 'border-orange-500 bg-orange-900/20'
              : 'border-gray-700 bg-gray-900/20 hover:border-gray-600'"
          >
            <input
              v-model="form.collection_profile"
              type="radio"
              :value="p.value"
              class="accent-orange-500 mt-0.5 shrink-0"
            />
            <div class="flex-1">
              <p class="text-sm font-medium" :class="form.collection_profile === p.value ? 'text-orange-300' : 'text-gray-300'">
                {{ p.label }}
              </p>
              <p class="text-xs text-gray-500 mt-0.5">{{ p.desc }}</p>
              <div v-if="p.groups" class="flex flex-wrap gap-1 mt-2">
                <span v-for="g in p.groups" :key="g" class="tag text-[10px]">{{ g }}</span>
              </div>
            </div>
          </label>
        </div>

        <!-- Custom group picker -->
        <div v-if="form.collection_profile === 'custom'" class="card p-4">
          <p class="text-xs text-gray-400 mb-3 font-medium">Select data groups:</p>
          <div class="grid grid-cols-2 gap-2">
            <label
              v-for="g in allGroups"
              :key="g.value"
              class="flex items-center gap-2 px-2 py-1.5 rounded cursor-pointer text-xs transition-colors"
              :class="form.custom_groups.includes(g.value) ? 'bg-orange-900/20 text-orange-300' : 'text-gray-400 hover:text-gray-200'"
            >
              <input
                type="checkbox"
                :value="g.value"
                v-model="form.custom_groups"
                class="accent-orange-500 w-3.5 h-3.5"
              />
              {{ g.label }}
            </label>
          </div>
        </div>
      </div>

      <!-- ============================================================
           GENERAL TAB
           ============================================================ -->
      <div v-if="activeTab === 'general'" class="p-4 flex flex-col gap-4">
        <p class="text-xs text-gray-500">Application-wide settings. Values set via environment variables are shown but cannot be overridden from the UI.</p>

        <div class="grid grid-cols-2 gap-3">
          <div>
            <label class="label">Log Level</label>
            <select v-model="form.general.log_level" class="select">
              <option value="debug">Debug</option>
              <option value="info">Info</option>
              <option value="warning">Warning</option>
              <option value="error">Error</option>
              <option value="critical">Critical</option>
            </select>
            <OverrideBadge v-if="overrides.log_level" />
          </div>
          <div>
            <label class="label">Max Sessions</label>
            <input
              v-model.number="form.general.max_sessions"
              class="input"
              type="number"
              min="1"
              max="1000"
            />
            <OverrideBadge v-if="overrides.max_sessions" />
          </div>
          <div>
            <label class="label">Snapshot Retention (days)</label>
            <input
              v-model.number="form.general.snapshot_retention_days"
              class="input"
              type="number"
              min="0"
              max="3650"
            />
            <p class="text-[10px] text-gray-600 mt-0.5">0 = keep forever</p>
          </div>
          <div>
            <label class="label">Rediscovery Interval (seconds)</label>
            <input
              v-model.number="form.general.rediscovery_interval"
              class="input"
              type="number"
              min="0"
            />
            <p class="text-[10px] text-gray-600 mt-0.5">0 = disabled</p>
          </div>
        </div>

        <!-- Database path (read-only, from env) -->
        <div>
          <label class="label">Database Path</label>
          <div class="input bg-gray-850 text-gray-400 cursor-not-allowed font-mono text-xs">
            {{ form.general.db_path || '(in-memory — set NETSCOPE_DB_PATH to persist)' }}
          </div>
          <OverrideBadge v-if="true" label="Environment only" />
        </div>

        <!-- Reset -->
        <div class="border-t border-gray-700 pt-4 mt-2">
          <div class="flex items-center justify-between">
            <div>
              <p class="text-sm text-gray-300 font-medium">Reset to Defaults</p>
              <p class="text-xs text-gray-500 mt-0.5">Restore all settings to their default values.</p>
            </div>
            <button
              class="btn-danger btn-sm"
              @click="handleReset"
              :disabled="saving"
            >
              Reset
            </button>
          </div>
        </div>
      </div>

      <!-- ============================================================
           BACKUP & IMPORT TAB
           ============================================================ -->
      <div v-if="activeTab === 'backup'" class="p-4 flex flex-col gap-5">
        <p class="text-xs text-gray-500">Backup and restore the database, or import/export individual discovery sessions.</p>

        <!-- Database Backup -->
        <div class="border border-gray-700 rounded-lg p-4">
          <h4 class="text-sm font-medium text-gray-200 mb-1">Database Backup</h4>
          <p class="text-xs text-gray-500 mb-3">Download a full copy of the SQLite database including all sessions, settings, and metadata.</p>
          <button
            class="btn-primary btn-sm"
            :disabled="!form.general.db_path"
            @click="downloadBackup"
          >
            Download Backup
          </button>
          <p v-if="!form.general.db_path" class="text-[10px] text-amber-500/80 mt-1.5">
            Requires NETSCOPE_DB_PATH (SQLite mode)
          </p>
        </div>

        <!-- Database Restore -->
        <div class="border border-gray-700 rounded-lg p-4">
          <h4 class="text-sm font-medium text-gray-200 mb-1">Database Restore</h4>
          <p class="text-xs text-gray-500 mb-3">Upload a previously exported .db backup file. The current database will be backed up before overwrite. Server restart is required after restore.</p>
          <div class="flex items-center gap-2">
            <input
              ref="restoreFileInput"
              type="file"
              accept=".db,.sqlite,.sqlite3"
              class="hidden"
              aria-label="Database restore file"
              @change="handleRestoreFile"
            />
            <button
              class="btn-danger btn-sm"
              :disabled="!form.general.db_path || backupRestoring"
              @click="$refs.restoreFileInput.click()"
            >
              <span v-if="backupRestoring" class="flex items-center gap-1.5">
                <svg class="animate-spin w-3 h-3" viewBox="0 0 24 24" fill="none">
                  <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"/>
                  <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z"/>
                </svg>
                Restoring...
              </span>
              <span v-else>Upload & Restore</span>
            </button>
          </div>
          <p v-if="backupRestoreMessage" :class="backupRestoreError ? 'text-red-400' : 'text-green-400'" class="text-xs mt-2">{{ backupRestoreMessage }}</p>
        </div>

        <!-- Session Export -->
        <div class="border border-gray-700 rounded-lg p-4">
          <h4 class="text-sm font-medium text-gray-200 mb-1">Session Export</h4>
          <p class="text-xs text-gray-500 mb-3">Export a discovery session as a portable JSON bundle (topology + saved views).</p>
          <div class="flex items-center gap-2">
            <select v-model="selectedExportSession" class="select flex-1 text-sm" aria-label="Select export session">
              <option value="">Select a session...</option>
              <option v-for="s in sessionList" :key="s.session_id" :value="s.session_id">
                {{ s.discovered_at ? new Date(s.discovered_at).toLocaleString() : s.session_id.slice(0,8) }}
                — {{ s.device_count }} device{{ s.device_count !== 1 ? 's' : '' }}
              </option>
            </select>
            <button
              class="btn-primary btn-sm whitespace-nowrap"
              :disabled="!selectedExportSession"
              @click="downloadSessionBundle(selectedExportSession)"
            >
              Export
            </button>
          </div>
          <button v-if="sessionList.length === 0" class="text-xs text-gray-500 mt-2 underline" @click="loadSessionList">Load sessions</button>
        </div>

        <!-- Session Import -->
        <div class="border border-gray-700 rounded-lg p-4">
          <h4 class="text-sm font-medium text-gray-200 mb-1">Session Import</h4>
          <p class="text-xs text-gray-500 mb-3">Import a session bundle (JSON) exported from another NetScope instance.</p>
          <div class="flex items-center gap-2">
            <input
              ref="importFileInput"
              type="file"
              accept=".json"
              class="hidden"
              aria-label="Session import file"
              @change="handleImportFile"
            />
            <button
              class="btn-primary btn-sm"
              :disabled="sessionImporting"
              @click="$refs.importFileInput.click()"
            >
              <span v-if="sessionImporting" class="flex items-center gap-1.5">
                <svg class="animate-spin w-3 h-3" viewBox="0 0 24 24" fill="none">
                  <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"/>
                  <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z"/>
                </svg>
                Importing...
              </span>
              <span v-else>Import Session Bundle</span>
            </button>
          </div>
          <p v-if="sessionImportMessage" :class="sessionImportError ? 'text-red-400' : 'text-green-400'" class="text-xs mt-2">{{ sessionImportMessage }}</p>
        </div>
      </div>
    </div>

    <!-- Footer: Save bar -->
    <div v-if="!loadingSettings && hasChanges" class="shrink-0 flex items-center justify-between px-4 py-3 border-t border-gray-700 bg-gray-850">
      <span class="text-xs text-orange-400">Unsaved changes</span>
      <div class="flex items-center gap-2">
        <button class="btn-ghost btn-sm" @click="discardChanges" :disabled="saving">Discard</button>
        <button class="btn-primary btn-sm" @click="saveSettings" :disabled="saving">
          <span v-if="saving" class="flex items-center gap-1.5">
            <svg class="animate-spin w-3 h-3" viewBox="0 0 24 24" fill="none">
              <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"/>
              <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z"/>
            </svg>
            Saving…
          </span>
          <span v-else>Save</span>
        </button>
      </div>
    </div>

    <!-- Success toast -->
    <Transition name="fade">
      <div v-if="saveSuccess" class="absolute bottom-16 left-1/2 -translate-x-1/2 bg-green-900/80 text-green-300 text-xs px-3 py-1.5 rounded shadow-md border border-green-800/40">
        ✓ Settings saved
      </div>
    </Transition>

    <!-- Error toast -->
    <Transition name="fade">
      <div v-if="saveError" class="absolute bottom-16 left-1/2 -translate-x-1/2 bg-red-900/80 text-red-300 text-xs px-3 py-1.5 rounded shadow-md border border-red-800/40 max-w-[90%] text-center">
        {{ saveError }}
      </div>
    </Transition>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, watch } from 'vue'
import { getSettings, updateSettings, testCredential, resetSettings, downloadBackup, restoreBackup, listSnapshots, downloadSessionBundle, importSessionBundle } from '../api.js'

/* eslint-disable no-unused-vars */
const emit = defineEmits(['close'])
/* eslint-enable no-unused-vars */

// ---------------------------------------------------------------------------
// Tab definitions
// ---------------------------------------------------------------------------
const tabs = [
  { key: 'discovery', label: 'Discovery' },
  { key: 'credentials', label: 'Credentials' },
  { key: 'profiles', label: 'Profiles' },
  { key: 'general', label: 'General' },
  { key: 'backup', label: 'Backup' },
]
const activeTab = ref('discovery')

// ---------------------------------------------------------------------------
// Profile & group definitions
// ---------------------------------------------------------------------------
const profileOptions = [
  { value: 'minimal',  label: 'Minimal',  desc: 'Topology only — version + neighbors. Fastest.', groups: ['version', 'neighbors'] },
  { value: 'standard', label: 'Standard', desc: 'Adds interfaces, VLANs, ARP, MAC tables.', groups: ['interfaces', 'vlans', 'arp', 'mac'] },
  { value: 'full',     label: 'Full',     desc: 'Adds routing, STP, EtherChannel, VXLAN/EVPN.', groups: ['routes', 'stp', 'etherchannel', 'vxlan'] },
  { value: 'custom',   label: 'Custom',   desc: 'Choose specific data groups to collect.' },
]

const allGroups = [
  { value: 'interfaces',    label: 'Interfaces' },
  { value: 'vlans',         label: 'VLANs' },
  { value: 'arp',           label: 'ARP' },
  { value: 'mac',           label: 'MAC Table' },
  { value: 'routes',        label: 'Routes' },
  { value: 'etherchannel',  label: 'EtherChannel' },
  { value: 'spanning_tree', label: 'Spanning Tree' },
  { value: 'vxlan',         label: 'VXLAN/EVPN' },
]

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------
const loadingSettings = ref(true)
const saving = ref(false)
const saveSuccess = ref(false)
const saveError = ref(null)

// The original settings from the server (for change detection)
const originalJson = ref('')

// Environment variable overrides (which fields are set via env)
const overrides = ref({})

// Form data
const form = reactive({
  discovery: {
    timeout: 30,
    max_concurrency: 10,
    max_hops: 2,
    discovery_protocol: 'cdp_prefer',
    scope: '',
    auto_follow: false,
  },
  credential_profiles: [],
  collection_profile: 'standard',
  custom_groups: [],
  general: {
    log_level: 'info',
    max_sessions: 50,
    snapshot_retention_days: 90,
    rediscovery_interval: 0,
    db_path: null,
  },
})

let credProfileId = 1

// ---------------------------------------------------------------------------
// Change detection
// ---------------------------------------------------------------------------
const hasChanges = computed(() => {
  return JSON.stringify(formSnapshot()) !== originalJson.value
})

function formSnapshot() {
  return {
    discovery: { ...form.discovery },
    credential_profiles: form.credential_profiles.map(c => ({
      label: c.label, username: c.username,
      password: c.password, enable_password: c.enable_password,
    })),
    collection_profile: form.collection_profile,
    custom_groups: [...form.custom_groups],
    general: { ...form.general },
  }
}

// ---------------------------------------------------------------------------
// Load settings
// ---------------------------------------------------------------------------
async function loadSettings() {
  loadingSettings.value = true
  try {
    const data = await getSettings()
    applyServerData(data)
  } catch (e) {
    // If the endpoint doesn't exist yet, use defaults
    console.warn('Settings endpoint not available:', e.message)
  } finally {
    loadingSettings.value = false
  }
}

function applyServerData(data) {
  if (data.discovery) {
    Object.assign(form.discovery, data.discovery)
  }
  if (data.credential_profiles) {
    form.credential_profiles = data.credential_profiles.map(c => ({
      ...c,
      _id: credProfileId++,
      _testResult: null,
      _testing: false,
    }))
  }
  if (data.collection_profile) form.collection_profile = data.collection_profile
  if (data.custom_groups) form.custom_groups = [...data.custom_groups]
  if (data.general) {
    Object.assign(form.general, data.general)
  }
  if (data.overrides) overrides.value = data.overrides
  originalJson.value = JSON.stringify(formSnapshot())
}

// ---------------------------------------------------------------------------
// Save settings
// ---------------------------------------------------------------------------
async function saveSettings() {
  saving.value = true
  saveError.value = null
  try {
    const payload = formSnapshot()
    const data = await updateSettings(payload)
    applyServerData(data)
    saveSuccess.value = true
    setTimeout(() => { saveSuccess.value = false }, 2500)
  } catch (e) {
    saveError.value = e.message || 'Failed to save settings'
    setTimeout(() => { saveError.value = null }, 4000)
  } finally {
    saving.value = false
  }
}

function discardChanges() {
  const original = JSON.parse(originalJson.value)
  Object.assign(form.discovery, original.discovery)
  form.credential_profiles = original.credential_profiles.map(c => ({
    ...c,
    _id: credProfileId++,
    _testResult: null,
    _testing: false,
  }))
  form.collection_profile = original.collection_profile
  form.custom_groups = [...original.custom_groups]
  Object.assign(form.general, original.general)
}

async function handleReset() {
  saving.value = true
  saveError.value = null
  try {
    const data = await resetSettings()
    applyServerData(data)
    saveSuccess.value = true
    setTimeout(() => { saveSuccess.value = false }, 2500)
  } catch (e) {
    saveError.value = e.message || 'Failed to reset settings'
    setTimeout(() => { saveError.value = null }, 4000)
  } finally {
    saving.value = false
  }
}

// ---------------------------------------------------------------------------
// Credential profiles
// ---------------------------------------------------------------------------
function addCredentialProfile() {
  form.credential_profiles.push({
    _id: credProfileId++,
    label: '',
    username: '',
    password: '',
    enable_password: '',
    _testResult: null,
    _testing: false,
  })
}

function removeCredentialProfile(index) {
  form.credential_profiles.splice(index, 1)
}

async function testCredentialProfile(cred) {
  if (!cred.username || !cred.password) return
  cred._testResult = null
  cred._testing = true
  try {
    const result = await testCredential({
      username: cred.username,
      password: cred.password,
      enable_password: cred.enable_password || null,
    })
    cred._testResult = result
  } catch (e) {
    cred._testResult = { success: false, error: e.message }
  } finally {
    cred._testing = false
  }
}

// ---------------------------------------------------------------------------
// Backup & Import state
// ---------------------------------------------------------------------------
const backupRestoring = ref(false)
const backupRestoreMessage = ref('')
const backupRestoreError = ref(false)

const sessionList = ref([])
const selectedExportSession = ref('')
const sessionImporting = ref(false)
const sessionImportMessage = ref('')
const sessionImportError = ref(false)

async function loadSessionList() {
  try {
    sessionList.value = await listSnapshots()
  } catch {
    sessionList.value = []
  }
}

async function handleRestoreFile(event) {
  const file = event.target.files?.[0]
  if (!file) return
  backupRestoring.value = true
  backupRestoreMessage.value = ''
  backupRestoreError.value = false
  try {
    const result = await restoreBackup(file)
    backupRestoreMessage.value = result.message || 'Database restored successfully.'
    backupRestoreError.value = false
  } catch (e) {
    backupRestoreMessage.value = e.message || 'Restore failed'
    backupRestoreError.value = true
  } finally {
    backupRestoring.value = false
    event.target.value = ''
  }
}

async function handleImportFile(event) {
  const file = event.target.files?.[0]
  if (!file) return
  sessionImporting.value = true
  sessionImportMessage.value = ''
  sessionImportError.value = false
  try {
    const result = await importSessionBundle(file)
    sessionImportMessage.value = `Imported session with ${result.device_count} devices, ${result.link_count} links, ${result.imported_views} views.`
    sessionImportError.value = false
    // Refresh session list if loaded
    if (sessionList.value.length > 0) await loadSessionList()
  } catch (e) {
    sessionImportMessage.value = e.message || 'Import failed'
    sessionImportError.value = true
  } finally {
    sessionImporting.value = false
    event.target.value = ''
  }
}

// ---------------------------------------------------------------------------
// Lifecycle
// ---------------------------------------------------------------------------
onMounted(loadSettings)

watch(activeTab, (tab) => {
  if (tab === 'backup' && sessionList.value.length === 0) loadSessionList()
})
</script>

<script>
// Inline sub-component for env override badges
const OverrideBadge = {
  props: {
    label: { type: String, default: 'Set via env var' },
  },
  template: `<p class="text-[10px] text-orange-500/70 mt-0.5 flex items-center gap-1">
    <svg class="w-2.5 h-2.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
    </svg>
    {{ label }}
  </p>`,
}

export default {
  components: { OverrideBadge },
}
</script>
