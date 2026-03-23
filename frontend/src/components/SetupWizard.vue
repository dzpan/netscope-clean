<template>
  <Teleport to="body">
    <Transition name="wizard-fade">
      <div v-if="visible" class="fixed inset-0 z-[60] flex items-center justify-center bg-gray-950/95 backdrop-blur-sm">
        <!-- Wizard card -->
        <div class="w-full max-w-lg mx-4 bg-gray-900 border border-gray-700 rounded-lg shadow-lg overflow-hidden">
          <!-- Header -->
          <div class="flex items-center justify-between px-6 py-4 border-b border-gray-700/50">
            <div class="flex items-center gap-3">
              <svg class="w-6 h-6 text-orange-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5"
                  d="M9 3H5a2 2 0 00-2 2v4m6-6h10a2 2 0 012 2v4M9 3v18m0 0h10a2 2 0 002-2V9M9 21H5a2 2 0 01-2-2V9m0 0h18"/>
              </svg>
              <span class="text-gray-50 font-semibold font-display">Net<span class="text-orange-500">Scope</span></span>
            </div>
            <button
              class="text-xs text-gray-500 hover:text-gray-300 transition-colors"
              @click="handleSkip"
            >
              Skip setup
            </button>
          </div>

          <!-- Step indicators -->
          <div class="flex items-center gap-1.5 px-6 pt-4">
            <div
              v-for="(s, i) in stepDefs"
              :key="s.key"
              class="h-1 flex-1 rounded-full transition-colors duration-300"
              :class="i <= currentStepIndex ? 'bg-orange-500' : 'bg-gray-700'"
            />
          </div>

          <!-- Step content -->
          <div class="px-6 py-6 min-h-[320px] flex flex-col">

            <!-- Step: Welcome -->
            <template v-if="step === 'welcome'">
              <h2 class="text-xl font-semibold text-gray-50 font-display mb-2">Welcome to NetScope</h2>
              <p class="text-sm text-gray-400 leading-relaxed mb-6">
                Let's get your first network topology scan running. This wizard will walk you through
                entering a seed device, SSH credentials, and running your first discovery.
              </p>
              <div class="flex flex-col gap-3 mt-auto">
                <div class="flex items-start gap-3 text-sm text-gray-300">
                  <span class="text-orange-500 mt-0.5">1</span>
                  <span>Enter a seed IP address or hostname</span>
                </div>
                <div class="flex items-start gap-3 text-sm text-gray-300">
                  <span class="text-orange-500 mt-0.5">2</span>
                  <span>Provide SSH credentials for your devices</span>
                </div>
                <div class="flex items-start gap-3 text-sm text-gray-300">
                  <span class="text-orange-500 mt-0.5">3</span>
                  <span>Test connectivity and discover your network</span>
                </div>
              </div>
            </template>

            <!-- Step: Seeds -->
            <template v-else-if="step === 'seeds'">
              <h2 class="text-lg font-semibold text-gray-50 font-display mb-1">Seed Devices</h2>
              <p class="text-sm text-gray-400 mb-4">
                Enter the IP address or hostname of one or more network devices to start discovery from.
              </p>
              <div class="flex flex-col gap-3 flex-1">
                <div>
                  <label class="text-xs font-medium text-gray-400 uppercase tracking-wider mb-1.5 block">IP Address / Hostname</label>
                  <textarea
                    ref="seedInput"
                    v-model="seeds"
                    class="input font-mono text-sm"
                    rows="3"
                    placeholder="10.0.0.1&#10;core-switch.corp.local"
                    @keydown.enter.ctrl="seeds.trim() && goNext()"
                  />
                  <p class="mt-1 text-xs text-gray-500">One per line. Start with your core switch or router.</p>
                </div>
                <div>
                  <label class="text-xs font-medium text-gray-400 uppercase tracking-wider mb-1.5 block">Scope (optional)</label>
                  <input
                    v-model="scope"
                    class="input text-sm"
                    type="text"
                    placeholder="10.0.0.0/24"
                  />
                  <p class="mt-1 text-xs text-gray-500">CIDR scope to limit discovery. Leave blank for no restriction.</p>
                </div>
              </div>
            </template>

            <!-- Step: Credentials -->
            <template v-else-if="step === 'credentials'">
              <h2 class="text-lg font-semibold text-gray-50 font-display mb-1">SSH Credentials</h2>
              <p class="text-sm text-gray-400 mb-4">
                Provide SSH login credentials. NetScope uses these to connect to your Cisco devices via SSH.
              </p>
              <div class="flex flex-col gap-3 flex-1">
                <div>
                  <label class="text-xs font-medium text-gray-400 uppercase tracking-wider mb-1.5 block">Username</label>
                  <input
                    ref="usernameInput"
                    v-model="username"
                    class="input text-sm"
                    type="text"
                    placeholder="admin"
                    autocomplete="off"
                  />
                </div>
                <div>
                  <label class="text-xs font-medium text-gray-400 uppercase tracking-wider mb-1.5 block">Password</label>
                  <input
                    v-model="password"
                    class="input text-sm"
                    type="password"
                    placeholder="••••••••"
                    autocomplete="off"
                  />
                </div>
                <div>
                  <label class="text-xs font-medium text-gray-400 uppercase tracking-wider mb-1.5 block">Enable Password <span class="text-gray-600 normal-case">(optional)</span></label>
                  <input
                    v-model="enablePassword"
                    class="input text-sm"
                    type="password"
                    placeholder="••••••••"
                    autocomplete="off"
                  />
                </div>
              </div>
            </template>

            <!-- Step: Profile -->
            <template v-else-if="step === 'profile'">
              <h2 class="text-lg font-semibold text-gray-50 font-display mb-1">Collection Profile</h2>
              <p class="text-sm text-gray-400 mb-4">
                Choose how much data to collect. You can always re-discover with more detail later.
              </p>
              <div class="flex flex-col gap-2 flex-1">
                <label
                  v-for="p in profiles"
                  :key="p.value"
                  class="flex items-start gap-3 p-3 rounded-md border cursor-pointer transition-colors"
                  :class="profile === p.value
                    ? 'border-orange-500/50 bg-orange-500/5'
                    : 'border-gray-700 hover:border-gray-600 bg-gray-900/40'"
                >
                  <input
                    v-model="profile"
                    type="radio"
                    :value="p.value"
                    class="mt-0.5 accent-orange-500"
                  />
                  <div>
                    <span class="text-sm text-gray-100 font-medium">{{ p.label }}</span>
                    <p class="text-xs text-gray-500 mt-0.5">{{ p.desc }}</p>
                    <span v-if="p.value === 'standard'" class="text-[10px] text-orange-500 uppercase font-semibold tracking-wider mt-1 inline-block">Recommended</span>
                  </div>
                </label>
              </div>
            </template>

            <!-- Step: Test -->
            <template v-else-if="step === 'test'">
              <h2 class="text-lg font-semibold text-gray-50 font-display mb-1">Connection Test</h2>
              <p class="text-sm text-gray-400 mb-4">
                Let's verify SSH connectivity before running the full discovery.
              </p>

              <div class="flex-1 flex flex-col items-center justify-center gap-4">
                <!-- Idle / not tested yet -->
                <template v-if="!testRunning && !testResult">
                  <div class="text-center">
                    <p class="text-sm text-gray-300 mb-1">Target: <span class="font-mono text-orange-400">{{ firstSeed }}</span></p>
                    <p class="text-xs text-gray-500">Credentials: <span class="font-mono">{{ username }}</span></p>
                  </div>
                  <button class="btn-primary px-6 py-2" @click="runTest">
                    Test Connection
                  </button>
                </template>

                <!-- Running -->
                <template v-else-if="testRunning">
                  <svg class="animate-spin h-8 w-8 text-orange-500" viewBox="0 0 24 24" fill="none">
                    <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"/>
                    <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z"/>
                  </svg>
                  <p class="text-sm text-orange-400 font-display">Connecting to <span class="font-mono">{{ firstSeed }}</span>…</p>
                  <p class="text-xs text-gray-500">Testing SSH credentials</p>
                </template>

                <!-- Success -->
                <template v-else-if="testResult && testResult.success">
                  <div class="w-10 h-10 rounded-full bg-green-900/40 flex items-center justify-center">
                    <svg class="w-5 h-5 text-green-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"/>
                    </svg>
                  </div>
                  <div class="text-center">
                    <p class="text-sm text-green-400 font-medium">Connection successful</p>
                    <p v-if="testResult.hostname" class="text-xs text-gray-400 mt-1">
                      Hostname: <span class="font-mono text-gray-200">{{ testResult.hostname }}</span>
                    </p>
                    <p v-if="testResult.platform" class="text-xs text-gray-400">
                      Platform: <span class="font-mono text-gray-200">{{ testResult.platform }}</span>
                    </p>
                    <p v-if="testResult.os_version" class="text-xs text-gray-400">
                      Version: <span class="font-mono text-gray-200">{{ testResult.os_version }}</span>
                    </p>
                  </div>
                </template>

                <!-- Failure -->
                <template v-else-if="testResult && !testResult.success">
                  <div class="w-10 h-10 rounded-full bg-red-900/40 flex items-center justify-center">
                    <svg class="w-5 h-5 text-red-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
                    </svg>
                  </div>
                  <div class="text-center">
                    <p class="text-sm text-red-400 font-medium">Connection failed</p>
                    <p class="text-xs text-gray-400 mt-1 font-mono">{{ testResult.error }}</p>
                  </div>
                  <div class="flex gap-2">
                    <button class="btn-secondary btn-sm" @click="step = 'credentials'">Fix Credentials</button>
                    <button class="btn-secondary btn-sm" @click="testResult = null">Retry</button>
                  </div>
                </template>
              </div>
            </template>

            <!-- Step: Success -->
            <template v-else-if="step === 'success'">
              <div class="flex-1 flex flex-col items-center justify-center gap-4">
                <div class="w-14 h-14 rounded-full bg-green-900/30 flex items-center justify-center">
                  <svg class="w-7 h-7 text-green-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"/>
                  </svg>
                </div>
                <div class="text-center">
                  <h2 class="text-xl font-semibold text-gray-50 font-display mb-2">You're all set!</h2>
                  <p class="text-sm text-gray-400">Your first network topology is now loaded.</p>
                </div>
                <div class="w-full max-w-sm flex flex-col gap-3 mt-4 text-sm">
                  <div class="flex items-start gap-3 text-gray-300">
                    <span class="text-orange-500 shrink-0">◉</span>
                    <span><strong class="text-gray-100">Click a device</strong> in the topology graph to see its details</span>
                  </div>
                  <div class="flex items-start gap-3 text-gray-300">
                    <span class="text-orange-500 shrink-0">◉</span>
                    <span>Use the <strong class="text-gray-100">search bar</strong> (press <kbd class="text-xs px-1 py-0.5 rounded bg-gray-800 border border-gray-600 font-mono">/</kbd>) to find devices, IPs, or VLANs</span>
                  </div>
                  <div class="flex items-start gap-3 text-gray-300">
                    <span class="text-orange-500 shrink-0">◉</span>
                    <span>Open <strong class="text-gray-100">Data Tables</strong> at the bottom for a tabular view</span>
                  </div>
                  <div class="flex items-start gap-3 text-gray-300">
                    <span class="text-orange-500 shrink-0">◉</span>
                    <span>Click <strong class="text-gray-100">? Help</strong> in the toolbar for the full quick-reference</span>
                  </div>
                </div>
              </div>
            </template>
          </div>

          <!-- Footer / actions -->
          <div class="flex items-center justify-between px-6 py-4 border-t border-gray-700/50 bg-gray-900/60">
            <button
              v-if="step !== 'welcome' && step !== 'success'"
              class="btn-secondary btn-sm"
              @click="goBack"
            >
              ← Back
            </button>
            <span v-else />

            <div class="flex items-center gap-2">
              <template v-if="step === 'welcome'">
                <button class="btn-secondary btn-sm" @click="handleDemo">Load Demo</button>
                <button class="btn-primary px-5 py-2" @click="goNext">Get Started</button>
              </template>
              <template v-else-if="step === 'seeds'">
                <button
                  class="btn-primary px-5 py-2"
                  :disabled="!seedsValid"
                  @click="goNext"
                >
                  Next
                </button>
              </template>
              <template v-else-if="step === 'credentials'">
                <button
                  class="btn-primary px-5 py-2"
                  :disabled="!credsValid"
                  @click="goNext"
                >
                  Next
                </button>
              </template>
              <template v-else-if="step === 'profile'">
                <button class="btn-primary px-5 py-2" @click="goNext">
                  Next
                </button>
              </template>
              <template v-else-if="step === 'test'">
                <button
                  v-if="testResult && testResult.success"
                  class="btn-primary px-5 py-2"
                  @click="handleDiscover"
                >
                  Discover Network
                </button>
                <button
                  v-else-if="!testRunning"
                  class="text-xs text-gray-500 hover:text-gray-300 transition-colors"
                  @click="handleDiscover"
                >
                  Skip test & discover
                </button>
              </template>
              <template v-else-if="step === 'success'">
                <button class="btn-primary px-5 py-2" @click="handleFinish">
                  Start Exploring
                </button>
              </template>
            </div>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup>
import { ref, computed, nextTick, watch } from 'vue'
import { probe, loadDemo } from '../api.js'

defineProps({
  visible: Boolean,
})

const emit = defineEmits(['discover', 'demo-loaded', 'skip', 'finish'])

// ---------------------------------------------------------------------------
// Wizard step flow
// ---------------------------------------------------------------------------
const stepDefs = [
  { key: 'welcome' },
  { key: 'seeds' },
  { key: 'credentials' },
  { key: 'profile' },
  { key: 'test' },
]
const step = ref('welcome')
const currentStepIndex = computed(() => {
  if (step.value === 'success') return stepDefs.length - 1
  return stepDefs.findIndex(s => s.key === step.value)
})

// ---------------------------------------------------------------------------
// Form state
// ---------------------------------------------------------------------------
const seeds = ref('')
const scope = ref('')
const username = ref('')
const password = ref('')
const enablePassword = ref('')
const profile = ref('standard')

const seedInput = ref(null)
const usernameInput = ref(null)

const seedsValid = computed(() => seeds.value.trim().length > 0)
const credsValid = computed(() => username.value.trim().length > 0 && password.value.length > 0)
const firstSeed = computed(() => seeds.value.split('\n').map(s => s.trim()).filter(Boolean)[0] || '')

const profiles = [
  { value: 'minimal',  label: 'Minimal',  desc: 'Topology only — version + neighbors. Fastest.' },
  { value: 'standard', label: 'Standard', desc: 'Adds interfaces, VLANs, ARP, MAC tables.' },
  { value: 'full',     label: 'Full',     desc: 'Everything: routing, STP, EtherChannel, VXLAN/EVPN.' },
]

// ---------------------------------------------------------------------------
// Connection test
// ---------------------------------------------------------------------------
const testRunning = ref(false)
const testResult = ref(null)

async function runTest() {
  testRunning.value = true
  testResult.value = null
  try {
    testResult.value = await probe({
      host: firstSeed.value,
      username: username.value,
      password: password.value,
      enable_password: enablePassword.value || null,
      timeout: 30,
    })
  } catch (e) {
    testResult.value = { success: false, host: firstSeed.value, error: e.message }
  } finally {
    testRunning.value = false
  }
}

// ---------------------------------------------------------------------------
// Navigation
// ---------------------------------------------------------------------------
function goNext() {
  const idx = currentStepIndex.value
  if (idx < stepDefs.length - 1) {
    step.value = stepDefs[idx + 1].key
  }
}

function goBack() {
  const idx = currentStepIndex.value
  if (idx > 0) {
    step.value = stepDefs[idx - 1].key
    // Reset test state if going back from test step
    if (step.value !== 'test') {
      testResult.value = null
    }
  }
}

// Auto-focus inputs when step changes
watch(step, async (s) => {
  await nextTick()
  if (s === 'seeds') seedInput.value?.focus()
  if (s === 'credentials') usernameInput.value?.focus()
})

// ---------------------------------------------------------------------------
// Actions
// ---------------------------------------------------------------------------
function buildPayload() {
  return {
    seeds: seeds.value.split('\n').map(s => s.trim()).filter(Boolean),
    scope: scope.value.trim() || null,
    credential_sets: [{
      username: username.value,
      password: password.value,
      enable_password: enablePassword.value || null,
      label: null,
    }],
    username: username.value,
    password: password.value,
    enable_password: enablePassword.value || null,
    max_hops: 2,
    max_concurrency: 10,
    timeout: 30,
    discovery_protocol: 'cdp_prefer',
    collection_profile: profile.value,
    custom_groups: [],
  }
}

function handleDiscover() {
  emit('discover', buildPayload())
}

async function handleDemo() {
  try {
    const result = await loadDemo()
    emit('demo-loaded', result)
  } catch {
    // ignore — demo not available
  }
}

function handleSkip() {
  emit('skip')
}

function handleFinish() {
  emit('finish')
}

/** Called by parent after discovery completes to advance to success step */
function showSuccess() {
  step.value = 'success'
}

defineExpose({ showSuccess })
</script>

<style scoped>
.wizard-fade-enter-active,
.wizard-fade-leave-active {
  transition: opacity 0.3s ease;
}
.wizard-fade-enter-from,
.wizard-fade-leave-to {
  opacity: 0;
}
</style>
