<template>
  <form class="flex flex-col gap-4 p-4 overflow-y-auto" @submit.prevent="handleDiscover">
    <!-- Seeds -->
    <div>
      <label for="seeds" class="label">Seed IPs / Hostnames</label>
      <textarea
        id="seeds"
        v-model="seedsRaw"
        class="input font-mono text-xs"
        :class="{ 'border-red-500': seedsRaw.trim() && invalidSeeds.length }"
        rows="4"
        placeholder="10.0.0.1&#10;10.0.0.2&#10;switch.corp.local"
      />
      <p v-if="seedsRaw.trim() && invalidSeeds.length" class="mt-1 text-xs text-red-400">
        Invalid: {{ invalidSeeds.join(', ') }}
      </p>
      <p v-else-if="suspiciousSeeds.length" class="mt-1 text-xs text-orange-400">
        Possible network/broadcast address: {{ suspiciousSeeds.join(', ') }}
      </p>
      <p v-else class="mt-1 text-xs text-gray-500">One per line</p>
    </div>

    <!-- Scope -->
    <div>
      <label for="scope" class="label">Scope (CIDR, optional)</label>
      <input
        id="scope"
        v-model="form.scope"
        class="input"
        :class="{ 'border-red-500': form.scope.trim() && !scopeValid }"
        type="text"
        placeholder="10.0.0.0/24"
      />
      <p v-if="form.scope.trim() && !scopeValid" class="mt-1 text-xs text-red-400">
        Invalid CIDR notation (e.g. 10.0.0.0/24)
      </p>
      <p v-else class="mt-1 text-xs text-gray-500">Leave blank to follow all neighbors</p>
    </div>

    <!-- Credential Sets -->
    <div class="border-t border-gray-700 pt-4">
      <div class="flex items-center justify-between mb-3">
        <p class="text-xs font-semibold text-gray-400 uppercase tracking-wider">Credential Sets</p>
        <button
          type="button"
          class="text-xs text-orange-500 hover:text-orange-300 flex items-center gap-1"
          @click="addCredSet"
        >
          + Add set
        </button>
      </div>
      <div class="flex flex-col gap-2">
        <div
          v-for="(cred, i) in credSets"
          :key="cred._id"
          class="rounded-lg border border-gray-700 bg-gray-900/40 p-3 flex flex-col gap-2"
        >
          <div class="flex items-center justify-between">
            <div class="flex items-center gap-1">
              <div v-if="credSets.length > 1" class="flex flex-col -my-1">
                <button
                  type="button"
                  class="text-gray-600 hover:text-orange-400 leading-none text-[10px]"
                  :disabled="i === 0"
                  :class="{ 'opacity-30 cursor-default': i === 0 }"
                  aria-label="Move credential set up"
                  @click="moveCredSet(i, -1)"
                >&#9650;</button>
                <button
                  type="button"
                  class="text-gray-600 hover:text-orange-400 leading-none text-[10px]"
                  :disabled="i === credSets.length - 1"
                  :class="{ 'opacity-30 cursor-default': i === credSets.length - 1 }"
                  aria-label="Move credential set down"
                  @click="moveCredSet(i, 1)"
                >&#9660;</button>
              </div>
              <span class="text-xs text-gray-500">
                {{ cred.label || `Set ${i + 1}` }}
              </span>
            </div>
            <button
              v-if="credSets.length > 1"
              type="button"
              class="text-xs text-gray-600 hover:text-red-400"
              @click="removeCredSetWithUndo(i)"
            >
              Remove
            </button>
          </div>
          <input
            v-model="cred.label"
            class="input text-xs py-1"
            type="text"
            placeholder="Label (e.g. Switches, APs)"
            aria-label="Credential set label"
          />
          <!-- Auth type selector -->
          <div class="grid grid-cols-2 gap-1">
            <button
              v-for="at in authTypes"
              :key="at.value"
              type="button"
              class="text-xs py-1 px-1.5 rounded border transition-colors truncate"
              :class="cred.auth_type === at.value
                ? 'border-orange-500 bg-orange-900/20 text-orange-300'
                : 'border-gray-700 text-gray-500 hover:border-gray-600'"
              @click="cred.auth_type = at.value"
            >{{ at.label }}</button>
          </div>
          <!-- SSH-based auth fields (password + key) -->
          <template v-if="cred.auth_type === 'password' || cred.auth_type === 'ssh_key'">
            <input
              v-model="cred.username"
              class="input text-xs py-1"
              type="text"
              placeholder="Username"
              autocomplete="off"
              aria-label="SSH username"
            />
            <!-- Password auth -->
            <div v-if="cred.auth_type === 'password'" class="relative">
              <input
                v-model="cred.password"
                class="input text-xs py-1 pr-8"
                :type="cred._showPw ? 'text' : 'password'"
                placeholder="Password"
                autocomplete="off"
                aria-label="SSH password"
              />
              <button
                type="button"
                class="absolute right-2 top-1/2 -translate-y-1/2 text-gray-500 hover:text-gray-300"
                :aria-label="cred._showPw ? 'Hide password' : 'Show password'"
                @click="cred._showPw = !cred._showPw"
              >
                <svg v-if="!cred._showPw" class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"/><path d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"/></svg>
                <svg v-else class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l3.59 3.59m0 0A9.953 9.953 0 0112 5c4.478 0 8.268 2.943 9.543 7a10.025 10.025 0 01-4.132 5.411m0 0L21 21"/></svg>
              </button>
            </div>
            <!-- SSH key auth -->
            <template v-else>
              <textarea
                v-model="cred.ssh_private_key"
                class="input text-xs py-1 font-mono"
                rows="3"
                placeholder="Paste SSH private key (PEM format)"
                aria-label="SSH private key"
              />
              <div class="relative">
                <input
                  v-model="cred.ssh_key_passphrase"
                  class="input text-xs py-1 pr-8"
                  :type="cred._showPw ? 'text' : 'password'"
                  placeholder="Key passphrase (optional)"
                  autocomplete="off"
                  aria-label="SSH key passphrase"
                />
                <button
                  type="button"
                  class="absolute right-2 top-1/2 -translate-y-1/2 text-gray-500 hover:text-gray-300"
                  :aria-label="cred._showPw ? 'Hide passphrase' : 'Show passphrase'"
                  @click="cred._showPw = !cred._showPw"
                >
                  <svg v-if="!cred._showPw" class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"/><path d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"/></svg>
                  <svg v-else class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l3.59 3.59m0 0A9.953 9.953 0 0112 5c4.478 0 8.268 2.943 9.543 7a10.025 10.025 0 01-4.132 5.411m0 0L21 21"/></svg>
                </button>
              </div>
            </template>
            <div class="relative">
              <input
                v-model="cred.enable_password"
                class="input text-xs py-1 pr-8"
                :type="cred._showEnable ? 'text' : 'password'"
                placeholder="Enable password (optional)"
                autocomplete="off"
                aria-label="Enable password"
              />
              <button
                type="button"
                class="absolute right-2 top-1/2 -translate-y-1/2 text-gray-500 hover:text-gray-300"
                :aria-label="cred._showEnable ? 'Hide enable password' : 'Show enable password'"
                @click="cred._showEnable = !cred._showEnable"
              >
                <svg v-if="!cred._showEnable" class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"/><path d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"/></svg>
                <svg v-else class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l3.59 3.59m0 0A9.953 9.953 0 0112 5c4.478 0 8.268 2.943 9.543 7a10.025 10.025 0 01-4.132 5.411m0 0L21 21"/></svg>
              </button>
            </div>
          </template>
          <!-- SNMP v2c fields -->
          <template v-if="cred.auth_type === 'snmp_v2c'">
            <div class="relative">
              <input
                v-model="cred.snmp_community"
                class="input text-xs py-1 pr-8"
                :type="cred._showPw ? 'text' : 'password'"
                placeholder="Community string (e.g. public)"
                autocomplete="off"
                aria-label="SNMP community string"
              />
              <button
                type="button"
                class="absolute right-2 top-1/2 -translate-y-1/2 text-gray-500 hover:text-gray-300"
                :aria-label="cred._showPw ? 'Hide community' : 'Show community'"
                @click="cred._showPw = !cred._showPw"
              >
                <svg v-if="!cred._showPw" class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"/><path d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"/></svg>
                <svg v-else class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l3.59 3.59m0 0A9.953 9.953 0 0112 5c4.478 0 8.268 2.943 9.543 7a10.025 10.025 0 01-4.132 5.411m0 0L21 21"/></svg>
              </button>
            </div>
            <input
              v-model.number="cred.snmp_port"
              class="input text-xs py-1"
              type="number"
              min="1"
              max="65535"
              placeholder="Port (default 161)"
              aria-label="SNMP port"
            />
          </template>
          <!-- SNMP v3 fields -->
          <template v-if="cred.auth_type === 'snmp_v3'">
            <input
              v-model="cred.username"
              class="input text-xs py-1"
              type="text"
              placeholder="Security name (username)"
              autocomplete="off"
              aria-label="SNMP v3 security name"
            />
            <div class="grid grid-cols-2 gap-2">
              <select v-model="cred.snmp_auth_protocol" class="input text-xs py-1" aria-label="Auth protocol">
                <option value="">No Auth</option>
                <option value="MD5">MD5</option>
                <option value="SHA">SHA</option>
                <option value="SHA256">SHA-256</option>
              </select>
              <input
                v-model="cred.snmp_auth_password"
                class="input text-xs py-1"
                type="password"
                placeholder="Auth password"
                autocomplete="off"
                aria-label="SNMP auth password"
              />
            </div>
            <div class="grid grid-cols-2 gap-2">
              <select v-model="cred.snmp_priv_protocol" class="input text-xs py-1" aria-label="Privacy protocol">
                <option value="">No Privacy</option>
                <option value="DES">DES</option>
                <option value="AES128">AES-128</option>
                <option value="AES256">AES-256</option>
              </select>
              <input
                v-model="cred.snmp_priv_password"
                class="input text-xs py-1"
                type="password"
                placeholder="Privacy password"
                autocomplete="off"
                aria-label="SNMP privacy password"
              />
            </div>
            <input
              v-model.number="cred.snmp_port"
              class="input text-xs py-1"
              type="number"
              min="1"
              max="65535"
              placeholder="Port (default 161)"
              aria-label="SNMP port"
            />
          </template>
        </div>
      </div>
      <p class="text-xs text-gray-600 mt-2">Tried in order — first success wins per device</p>
      <!-- Undo remove toast -->
      <div
        v-if="removedCred"
        class="mt-2 flex items-center justify-between px-3 py-2 rounded-lg bg-gray-800 border border-gray-600 text-xs"
      >
        <span class="text-gray-300">Removed {{ removedCred.item.label || 'credential set' }}</span>
        <button type="button" class="text-orange-400 hover:text-orange-300 font-medium" @click="undoRemove">Undo</button>
      </div>
    </div>

    <!-- Collection Profile -->
    <div class="border-t border-gray-700 pt-4">
      <p class="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-3">Collection Profile</p>
      <div class="flex flex-col gap-2">
        <label
          v-for="p in profiles"
          :key="p.value"
          class="flex items-start gap-3 p-2.5 rounded-lg border cursor-pointer transition-colors"
          :class="form.collection_profile === p.value
            ? 'border-orange-500 bg-orange-900/20'
            : 'border-gray-700 bg-gray-900/20 hover:border-gray-600'"
        >
          <input
            v-model="form.collection_profile"
            type="radio"
            name="collection_profile"
            :id="`profile-${p.value}`"
            :value="p.value"
            class="accent-orange-500 mt-0.5 shrink-0"
          />
          <div>
            <p class="text-sm font-medium" :class="form.collection_profile === p.value ? 'text-orange-300' : 'text-gray-300'">
              {{ p.label }}
            </p>
            <p class="text-xs text-gray-500 mt-0.5">{{ p.desc }}</p>
          </div>
        </label>
      </div>

      <!-- Custom group checkboxes -->
      <div v-if="form.collection_profile === 'custom'" class="mt-3 pl-1">
        <p class="text-xs text-gray-400 mb-2">Select data groups:</p>
        <div class="grid grid-cols-2 gap-1.5">
          <label
            v-for="g in allGroups"
            :key="g.value"
            class="flex items-center gap-2 text-xs text-gray-300 cursor-pointer"
          >
            <input
              type="checkbox"
              :id="`group-${g.value}`"
              :value="g.value"
              v-model="form.custom_groups"
              class="accent-orange-500 w-3.5 h-3.5"
            />
            {{ g.label }}
          </label>
        </div>
      </div>
    </div>

    <!-- Options -->
    <div class="border-t border-gray-700 pt-4">
      <p class="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-3">Options</p>

      <!-- Auto-follow toggle -->
      <label class="flex items-start gap-3 p-2.5 rounded-lg bg-orange-900/20 border border-orange-800/40 cursor-pointer mb-3 hover:bg-orange-900/30 transition-colors">
        <input id="auto-follow" v-model="form.auto_follow" type="checkbox" class="accent-orange-500 w-4 h-4 mt-0.5 shrink-0" aria-label="Auto-follow all neighbors" />
        <div>
          <p class="text-sm font-medium text-orange-300">Auto-follow all neighbors</p>
          <p class="text-xs text-gray-500 mt-0.5">
            Start from seed IPs and automatically discover the entire network via CDP/LLDP.
            Set a <strong class="text-gray-400">Scope</strong> above to limit the range.
          </p>
        </div>
      </label>

      <div class="grid grid-cols-2 gap-3">
        <!-- Max Hops — hidden when auto-follow is on -->
        <div v-if="!form.auto_follow">
          <label for="max-hops" class="label">Max Hops</label>
          <input
            id="max-hops"
            v-model.number="form.max_hops"
            class="input"
            :class="{ 'border-red-500': !isInRange(form.max_hops, 0, 10) }"
            type="number"
            min="0"
            max="10"
            @blur="form.max_hops = clamp(form.max_hops, 0, 10)"
          />
          <p v-if="!isInRange(form.max_hops, 0, 10)" class="text-xs text-red-400 mt-0.5">Must be 0–10</p>
        </div>
        <div v-else>
          <label class="label">Max Hops</label>
          <div class="input flex items-center text-gray-500 italic cursor-default">∞ unlimited</div>
        </div>
        <div>
          <label for="concurrency" class="label">Concurrency</label>
          <input
            id="concurrency"
            v-model.number="form.max_concurrency"
            class="input"
            :class="{ 'border-red-500': !isInRange(form.max_concurrency, 1, 50) }"
            type="number"
            min="1"
            max="50"
            @blur="form.max_concurrency = clamp(form.max_concurrency, 1, 50)"
          />
          <p v-if="!isInRange(form.max_concurrency, 1, 50)" class="text-xs text-red-400 mt-0.5">Must be 1–50</p>
        </div>
        <div>
          <label for="timeout" class="label">Timeout (s)</label>
          <input
            id="timeout"
            v-model.number="form.timeout"
            class="input"
            :class="{ 'border-red-500': !isInRange(form.timeout, 5, 120) }"
            type="number"
            min="5"
            max="120"
            @blur="form.timeout = clamp(form.timeout, 5, 120)"
          />
          <p v-if="!isInRange(form.timeout, 5, 120)" class="text-xs text-red-400 mt-0.5">Must be 5–120</p>
        </div>
        <div>
          <label for="discovery-protocol" class="label">Discovery Protocol</label>
          <select id="discovery-protocol" v-model="form.discovery_protocol" class="select">
            <option value="cdp_prefer">CDP Prefer</option>
            <option value="lldp_prefer">LLDP Prefer</option>
            <option value="both">Both</option>
          </select>
        </div>
      </div>
    </div>

    <!-- Actions -->
    <div class="border-t border-gray-700 pt-4 flex flex-col gap-2">
      <button
        type="submit"
        class="btn-primary w-full py-2"
        :disabled="loading || !canSubmit"
      >
        <span v-if="loading" class="flex items-center justify-center gap-2">
          <svg class="animate-spin h-4 w-4" viewBox="0 0 24 24" fill="none">
            <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"/>
            <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z"/>
          </svg>
          Discovering…
        </span>
        <span v-else>Discover</span>
      </button>
      <button type="button" class="btn-secondary w-full" :disabled="loading || !canSubmit" @click="handleProbe">
        Test Credentials
      </button>
      <button type="button" class="btn-ghost w-full border border-dashed border-gray-600 text-gray-500 hover:text-orange-400 hover:border-orange-500" :disabled="loading" @click="handleDemo">
        ⚡ Load Demo Topology
      </button>
    </div>

    <!-- Probe result -->
    <div v-if="probeResult" class="card p-3 text-xs">
      <div v-if="probeResult.success" class="text-green-400">
        ✓ Connected to <strong>{{ probeResult.hostname || probeResult.host }}</strong>
        <div class="text-gray-400 mt-1">{{ probeResult.platform }} · {{ probeResult.os_version }}</div>
      </div>
      <div v-else class="text-red-400">
        ✗ {{ probeResult.error || 'Connection failed' }}
      </div>
    </div>

    <!-- Past Sessions -->
    <div v-if="sessions.length" class="border-t border-gray-700 pt-4">
      <p class="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">Past Sessions</p>
      <ul class="flex flex-col gap-1">
        <li
          v-for="s in sessions"
          :key="s.session_id"
          class="flex items-center justify-between px-2 py-1 rounded hover:bg-gray-700 cursor-pointer text-xs"
          @click="$emit('session-selected', s)"
        >
          <span class="text-gray-300 font-mono">{{ s.session_id.slice(0, 8) }}</span>
          <span class="text-gray-500">{{ formatDate(s.discovered_at) }}</span>
          <span class="text-orange-400">{{ s.devices.length }}d / {{ s.links.length }}l</span>
        </li>
      </ul>
    </div>
  </form>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import { probe, listSessions, loadDemo } from '../api.js'

const emit = defineEmits(['discover-requested', 'session-selected'])
defineProps({ loading: Boolean })

const seedsRaw = ref('')
const sessions = ref([])
const probeResult = ref(null)

const profiles = [
  { value: 'minimal',  label: 'Minimal',  desc: 'Topology only — version + neighbors. Fastest.' },
  { value: 'standard', label: 'Standard', desc: 'Adds interfaces, VLANs, ARP, MAC tables.' },
  { value: 'full',     label: 'Full',     desc: 'Adds routing, STP, EtherChannel, VXLAN/EVPN.' },
  { value: 'custom',   label: 'Custom',   desc: 'Choose specific data groups to collect.' },
]

const authTypes = [
  { value: 'password', label: 'Password' },
  { value: 'ssh_key', label: 'SSH Key' },
  { value: 'snmp_v2c', label: 'SNMP v2c' },
  { value: 'snmp_v3', label: 'SNMP v3' },
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

const form = ref({
  scope: '',
  auto_follow: false,
  max_hops: 2,
  max_concurrency: 10,
  timeout: 30,
  discovery_protocol: 'cdp_prefer',
  collection_profile: 'standard',
  custom_groups: [],
})

let credSetId = 1
const credSets = ref([
  { _id: credSetId++, label: '', auth_type: 'password', username: '', password: '', ssh_private_key: '', ssh_key_passphrase: '', enable_password: '', snmp_community: '', snmp_port: 161, snmp_auth_protocol: '', snmp_auth_password: '', snmp_priv_protocol: '', snmp_priv_password: '', _showPw: false, _showEnable: false }
])

// --- localStorage persistence (excludes passwords/keys for security) ---
const STORAGE_KEY = 'netscope-discover-form'
const SENSITIVE_FIELDS = ['password', 'ssh_private_key', 'ssh_key_passphrase', 'enable_password', 'snmp_community', 'snmp_auth_password', 'snmp_priv_password']

function stripSecrets(cred) {
  const clean = { ...cred }
  for (const f of SENSITIVE_FIELDS) clean[f] = ''
  delete clean._showPw
  delete clean._showEnable
  return clean
}

function saveFormState() {
  try {
    const state = {
      seedsRaw: seedsRaw.value,
      form: form.value,
      credSets: credSets.value.map(stripSecrets),
    }
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state))
  } catch (_) { /* quota exceeded or private mode */ }
}

function restoreFormState() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return
    const state = JSON.parse(raw)
    if (state.seedsRaw != null) seedsRaw.value = state.seedsRaw
    if (state.form) Object.assign(form.value, state.form)
    if (Array.isArray(state.credSets) && state.credSets.length) {
      credSets.value = state.credSets.map(c => ({
        ...c,
        _id: credSetId++,
        _showPw: false,
        _showEnable: false,
        // Ensure sensitive fields exist (empty after restore)
        password: c.password || '',
        ssh_private_key: c.ssh_private_key || '',
        ssh_key_passphrase: c.ssh_key_passphrase || '',
        enable_password: c.enable_password || '',
        snmp_community: c.snmp_community || '',
        snmp_auth_password: c.snmp_auth_password || '',
        snmp_priv_password: c.snmp_priv_password || '',
      }))
    }
  } catch (_) { /* corrupt data — ignore */ }
}

function addCredSet() {
  credSets.value.push({ _id: credSetId++, label: '', auth_type: 'password', username: '', password: '', ssh_private_key: '', ssh_key_passphrase: '', enable_password: '', snmp_community: '', snmp_port: 161, snmp_auth_protocol: '', snmp_auth_password: '', snmp_priv_protocol: '', snmp_priv_password: '', _showPw: false, _showEnable: false })
}

const removedCred = ref(null)
let undoTimer = null

function removeCredSetWithUndo(i) {
  const item = credSets.value.splice(i, 1)[0]
  clearTimeout(undoTimer)
  removedCred.value = { item, index: i }
  undoTimer = setTimeout(() => { removedCred.value = null }, 5000)
}

function undoRemove() {
  if (!removedCred.value) return
  const { item, index } = removedCred.value
  credSets.value.splice(index, 0, item)
  removedCred.value = null
  clearTimeout(undoTimer)
}

function removeCredSet(i) {
  credSets.value.splice(i, 1)
}

function moveCredSet(i, dir) {
  const j = i + dir
  if (j < 0 || j >= credSets.value.length) return
  const arr = credSets.value
  ;[arr[i], arr[j]] = [arr[j], arr[i]]
}

const IPV4_RE = /^(\d{1,3}\.){3}\d{1,3}$/
const CIDR_RE = /^(\d{1,3}\.){3}\d{1,3}\/\d{1,2}$/
const HOSTNAME_RE = /^[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*$/

function isValidIPv4(s) {
  if (!IPV4_RE.test(s)) return false
  return s.split('.').every(o => { const n = Number(o); return n >= 0 && n <= 255 })
}

function isValidSeed(s) {
  return isValidIPv4(s) || HOSTNAME_RE.test(s)
}

function isValidCIDR(s) {
  if (!CIDR_RE.test(s)) return false
  const [ip, prefix] = s.split('/')
  const prefixNum = Number(prefix)
  return isValidIPv4(ip) && prefixNum >= 0 && prefixNum <= 32
}

const invalidSeeds = computed(() => {
  const lines = seedsRaw.value.split('\n').map(s => s.trim()).filter(Boolean)
  return lines.filter(l => !isValidSeed(l))
})

const suspiciousSeeds = computed(() => {
  const lines = seedsRaw.value.split('\n').map(s => s.trim()).filter(Boolean)
  return lines.filter(l => {
    if (!isValidIPv4(l)) return false
    const octets = l.split('.')
    const last = Number(octets[3])
    return last === 0 || last === 255
  })
})

const scopeValid = computed(() => {
  const s = form.value.scope.trim()
  if (!s) return true
  return s.split(/[,\s]+/).filter(Boolean).every(isValidCIDR)
})

function clamp(val, min, max) {
  if (typeof val !== 'number' || Number.isNaN(val)) return min
  return Math.min(max, Math.max(min, val))
}

function isInRange(val, min, max) {
  return typeof val === 'number' && !Number.isNaN(val) && val >= min && val <= max
}

function isCredValid(c) {
  if (c.auth_type === 'ssh_key') return c.username && c.ssh_private_key
  if (c.auth_type === 'snmp_v2c') return !!c.snmp_community
  if (c.auth_type === 'snmp_v3') return !!c.username
  return c.username && c.password
}

const canSubmit = computed(() => {
  return seedsRaw.value.trim().length > 0 &&
    invalidSeeds.value.length === 0 &&
    scopeValid.value &&
    credSets.value.some(isCredValid)
})

const AUTO_FOLLOW_HOPS = 10   // effectively unlimited for any real network

function buildPayload() {
  const validSets = credSets.value
    .filter(isCredValid)
    .map(c => {
      const isSNMP = c.auth_type === 'snmp_v2c' || c.auth_type === 'snmp_v3'
      const entry = {
        username: c.username,
        password: c.auth_type === 'password' ? c.password : '',
        auth_type: c.auth_type,
        ssh_private_key: c.auth_type === 'ssh_key' ? c.ssh_private_key : null,
        ssh_key_passphrase: c.auth_type === 'ssh_key' ? (c.ssh_key_passphrase || null) : null,
        enable_password: c.enable_password || null,
        label: c.label || null,
      }
      if (c.auth_type === 'snmp_v2c') {
        entry.snmp_community = c.snmp_community
        entry.snmp_port = c.snmp_port
      }
      if (c.auth_type === 'snmp_v3') {
        entry.snmp_port = c.snmp_port
        entry.snmp_auth_protocol = c.snmp_auth_protocol || null
        entry.snmp_auth_password = c.snmp_auth_password || null
        entry.snmp_priv_protocol = c.snmp_priv_protocol || null
        entry.snmp_priv_password = c.snmp_priv_password || null
      }
      return entry
    })
  return {
    seeds: seedsRaw.value.split('\n').map(s => s.trim()).filter(Boolean),
    scope: form.value.scope.trim() || null,
    credential_sets: validSets,
    // Keep primary credential fields for backward compat (RetryRequest etc.)
    username: validSets[0]?.username || '',
    password: validSets[0]?.password || '',
    enable_password: validSets[0]?.enable_password || null,
    max_hops: form.value.auto_follow ? AUTO_FOLLOW_HOPS : form.value.max_hops,
    max_concurrency: form.value.max_concurrency,
    timeout: form.value.timeout,
    discovery_protocol: form.value.discovery_protocol,
    collection_profile: form.value.collection_profile,
    custom_groups: form.value.collection_profile === 'custom' ? form.value.custom_groups : [],
  }
}

function handleDiscover() {
  probeResult.value = null
  emit('discover-requested', buildPayload())
}

async function handleProbe() {
  probeResult.value = null
  const seeds = seedsRaw.value.split('\n').map(s => s.trim()).filter(Boolean)
  if (!seeds.length) return
  const firstCred = credSets.value.find(c => c.username && c.password)
  if (!firstCred) return
  try {
    probeResult.value = await probe({
      host: seeds[0],
      username: firstCred.username,
      password: firstCred.password,
      enable_password: firstCred.enable_password || null,
      timeout: form.value.timeout,
    })
  } catch (e) {
    probeResult.value = { success: false, host: seeds[0], error: e.message }
  }
}

async function handleDemo() {
  probeResult.value = null
  try {
    const result = await loadDemo()
    emit('session-selected', result)
    sessions.value = await listSessions()
  } catch (e) {
    probeResult.value = { success: false, host: 'demo', error: e.message }
  }
}

function formatDate(iso) {
  return new Date(iso).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

// Persist form state on changes
watch(seedsRaw, saveFormState)
watch(form, saveFormState, { deep: true })
watch(credSets, saveFormState, { deep: true })

onMounted(async () => {
  restoreFormState()
  try {
    sessions.value = await listSessions()
  } catch (_err) {
    // ignore
  }
})
</script>
