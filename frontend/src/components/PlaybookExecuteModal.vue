<template>
  <Teleport to="body">
    <Transition name="fade">
      <div v-if="show" class="fixed inset-0 z-50 flex items-center justify-center" role="dialog" aria-modal="true" aria-label="Execute playbook">
        <div class="absolute inset-0 bg-black/60 backdrop-blur-sm" @click="canClose && $emit('close')" />
        <div class="relative bg-gray-900 border border-gray-700 rounded-lg shadow-xl w-full max-w-xl mx-4 overflow-hidden max-h-[90vh] flex flex-col">

          <!-- Header -->
          <div class="px-5 pt-5 pb-3 border-b border-gray-700/50 shrink-0">
            <h3 class="text-base font-semibold text-gray-100 font-display">Run Playbook</h3>
            <p class="text-xs text-gray-500 mt-0.5 font-mono">{{ playbook.title }}</p>
          </div>

          <!-- Step indicator -->
          <div class="flex items-center gap-0 px-5 py-3 border-b border-gray-700/50 shrink-0">
            <template v-for="(s, idx) in stepLabels" :key="idx">
              <div class="flex items-center gap-1.5">
                <div
                  class="w-6 h-6 rounded-full flex items-center justify-center text-xs font-medium transition-colors"
                  :class="stepCircleClass(idx)"
                >
                  <template v-if="currentStep > idx && currentStep < 4">&#x2713;</template>
                  <template v-else-if="currentStep === 4 && executionResult?.status === 'success'">&#x2713;</template>
                  <template v-else-if="currentStep === 4 && executionResult?.status === 'failed' && idx === 3">&#x2717;</template>
                  <template v-else-if="currentStep === idx && executing">
                    <svg class="animate-spin w-3 h-3" viewBox="0 0 24 24" fill="none">
                      <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"/>
                      <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z"/>
                    </svg>
                  </template>
                  <template v-else>{{ idx + 1 }}</template>
                </div>
                <span class="text-xs" :class="currentStep >= idx ? 'text-gray-200' : 'text-gray-600'">{{ s }}</span>
              </div>
              <div v-if="idx < stepLabels.length - 1" class="flex-1 h-px mx-2" :class="currentStep > idx ? 'bg-orange-500' : 'bg-gray-700'" />
            </template>
          </div>

          <!-- Body -->
          <div class="px-5 py-4 overflow-y-auto flex-1">

            <!-- Step 0: Select devices -->
            <template v-if="currentStep === 0">
              <div class="flex flex-col gap-4">
                <div>
                  <label class="label">Target Devices</label>
                  <p class="text-xs text-gray-500 mb-2">Select devices to execute this playbook on.</p>
                  <div v-if="devices.length === 0" class="text-xs text-gray-600 py-4 text-center">
                    No devices discovered. Run a discovery first.
                  </div>
                  <div v-else class="max-h-48 overflow-y-auto border border-gray-700 rounded bg-gray-800/50">
                    <div
                      v-for="dev in compatibleDevices"
                      :key="dev.id"
                      class="flex items-center gap-2 px-3 py-1.5 text-sm cursor-pointer transition-colors"
                      :class="selectedDeviceIds.has(dev.id)
                        ? 'bg-orange-500/15 text-orange-300'
                        : 'text-gray-300 hover:bg-gray-700/50'"
                      @click="toggleDevice(dev.id)"
                    >
                      <input
                        type="checkbox"
                        :checked="selectedDeviceIds.has(dev.id)"
                        class="accent-orange-500"
                        @click.stop
                        @change="toggleDevice(dev.id)"
                      />
                      <span class="font-mono text-sm">{{ dev.hostname || dev.id }}</span>
                      <span class="text-xs text-gray-500 font-mono ml-auto">{{ dev.mgmt_ip }}</span>
                      <span v-if="dev.platform" class="badge text-xs bg-gray-700 text-gray-400">{{ dev.platform }}</span>
                    </div>
                  </div>
                  <p v-if="selectedDeviceIds.size > 0" class="text-xs text-gray-500 mt-1">
                    {{ selectedDeviceIds.size }} device{{ selectedDeviceIds.size !== 1 ? 's' : '' }} selected
                  </p>
                </div>

                <!-- Pre-selected device (from context menu) -->
                <div v-if="preSelectedDevice" class="bg-gray-800/50 border border-gray-700 rounded px-3 py-2">
                  <p class="text-xs text-gray-500">Pre-selected device:</p>
                  <p class="font-mono text-sm text-gray-200">{{ preSelectedDevice.hostname || preSelectedDevice.id }}</p>
                </div>
              </div>
            </template>

            <!-- Step 1: Fill variables -->
            <template v-if="currentStep === 1">
              <div class="flex flex-col gap-4">
                <div v-if="playbook.variables?.length === 0" class="text-xs text-gray-500 py-4 text-center">
                  This playbook has no variables. Proceed to preview.
                </div>
                <div v-for="v in playbook.variables" :key="v.name">
                  <label class="label">
                    {{ v.description || v.name }}
                    <span v-if="v.required" class="text-red-400 ml-0.5">*</span>
                  </label>
                  <p class="text-xs text-gray-600 mb-1 font-mono" v-text="'{{' + v.name + '}}'"></p>
                  <select
                    v-if="v.type === 'choice'"
                    v-model="variableValues[v.name]"
                    class="select"
                  >
                    <option value="">Select…</option>
                    <option v-for="ch in (v.choices || [])" :key="ch" :value="ch">{{ ch }}</option>
                  </select>
                  <input
                    v-else-if="v.type === 'int'"
                    v-model.number="variableValues[v.name]"
                    type="number"
                    class="input"
                    :placeholder="v.default || ''"
                  />
                  <input
                    v-else
                    v-model="variableValues[v.name]"
                    type="text"
                    class="input font-mono"
                    :placeholder="v.default || ''"
                  />
                </div>
              </div>
            </template>

            <!-- Step 2: Dry-run preview -->
            <template v-if="currentStep === 2">
              <div class="flex flex-col gap-4">
                <div v-if="dryRunLoading" class="flex items-center justify-center py-8 text-gray-500">
                  <svg class="animate-spin w-5 h-5 mr-2" viewBox="0 0 24 24" fill="none">
                    <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"/>
                    <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z"/>
                  </svg>
                  Generating preview…
                </div>
                <template v-else>
                  <div>
                    <p class="text-xs text-gray-500 mb-1.5">Devices ({{ selectedDeviceIds.size }}):</p>
                    <div class="flex flex-wrap gap-1">
                      <span
                        v-for="id in [...selectedDeviceIds]"
                        :key="id"
                        class="badge bg-gray-800 text-gray-300 font-mono text-xs"
                      >{{ deviceName(id) }}</span>
                    </div>
                  </div>
                  <!-- Dry-run validation errors -->
                  <div v-if="dryRunErrors.length" class="bg-red-900/20 border border-red-800/40 rounded px-3 py-2.5 text-xs">
                    <p class="font-medium text-red-400 mb-1">Validation Errors</p>
                    <ul class="list-disc list-inside text-red-300/80 space-y-0.5">
                      <li v-for="(err, i) in dryRunErrors" :key="i">{{ err }}</li>
                    </ul>
                  </div>
                  <div>
                    <p class="text-xs text-gray-500 mb-1.5">Commands to execute:</p>
                    <pre class="bg-gray-950 border border-gray-700 rounded p-3 text-xs font-mono text-orange-300 overflow-x-auto whitespace-pre">{{ dryRunPreview || interpolatedCommands }}</pre>
                  </div>
                  <div v-if="playbook.pre_checks?.length">
                    <p class="text-xs text-gray-500 mb-1.5">Pre-checks:</p>
                    <pre class="bg-gray-950 border border-gray-700 rounded p-3 text-xs font-mono text-green-300 overflow-x-auto whitespace-pre">{{ interpolateLines(playbook.pre_checks).join('\n') }}</pre>
                  </div>
                  <div v-if="playbook.post_checks?.length">
                    <p class="text-xs text-gray-500 mb-1.5">Post-checks:</p>
                    <pre class="bg-gray-950 border border-gray-700 rounded p-3 text-xs font-mono text-green-300 overflow-x-auto whitespace-pre">{{ interpolateLines(playbook.post_checks).join('\n') }}</pre>
                  </div>
                  <!-- Config diff preview from pre-check outputs -->
                  <div v-if="Object.keys(dryRunPreCheckOutputs).length > 0">
                    <p class="text-xs text-gray-500 mb-1.5">Current Device Config (pre-check snapshot):</p>
                    <div class="flex flex-col gap-2">
                      <div
                        v-for="(output, cmd) in dryRunPreCheckOutputs"
                        :key="cmd"
                        class="bg-gray-950 border border-gray-700 rounded overflow-hidden"
                      >
                        <div class="px-3 py-1.5 bg-gray-800/50 border-b border-gray-700">
                          <code class="text-xs font-mono text-green-400">{{ cmd }}</code>
                        </div>
                        <pre class="px-3 py-2 text-xs font-mono text-gray-400 overflow-x-auto whitespace-pre max-h-40 overflow-y-auto">{{ output }}</pre>
                      </div>
                    </div>
                  </div>
                  <!-- Config diff error -->
                  <div v-if="dryRunConfigDiffError" class="bg-gray-800/50 border border-gray-700 rounded px-3 py-2 text-xs text-gray-500">
                    <span class="text-gray-400">Config preview unavailable:</span> {{ dryRunConfigDiffError }}
                  </div>
                  <!-- Warning -->
                  <div class="bg-orange-900/15 border border-orange-800/40 rounded px-3 py-2.5 text-xs text-orange-300/80">
                    <p class="font-medium text-orange-300 mb-1">Configuration Change</p>
                    <p>This will modify the running configuration on {{ selectedDeviceIds.size }} device{{ selectedDeviceIds.size !== 1 ? 's' : '' }}. Changes are applied sequentially.</p>
                  </div>
                </template>
              </div>
            </template>

            <!-- Step 3: Executing -->
            <template v-if="currentStep === 3 || currentStep === 4">
              <div class="flex flex-col gap-4">
                <div v-if="executing" class="flex flex-col items-center justify-center py-8 gap-4">
                  <svg class="animate-spin h-10 w-10 text-orange-500" viewBox="0 0 24 24" fill="none">
                    <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"/>
                    <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z"/>
                  </svg>
                  <p class="text-orange-400 font-medium font-display">Executing playbook…</p>
                  <p class="text-gray-500 text-xs">{{ executionStatusMsg }}</p>
                </div>

                <!-- Result -->
                <div v-if="executionResult" class="flex flex-col gap-3">
                  <!-- Success -->
                  <div v-if="executionResult.status === 'success'" class="bg-green-900/20 border border-green-800/40 rounded px-4 py-3">
                    <div class="flex items-center gap-2 mb-2">
                      <span class="text-green-400 text-lg">&#x2713;</span>
                      <span class="text-green-300 font-medium font-display">Playbook executed successfully</span>
                    </div>
                    <p v-if="executionResult.summary" class="text-xs text-green-300/80">{{ executionResult.summary }}</p>
                  </div>
                  <!-- Failed -->
                  <div v-else class="bg-red-900/20 border border-red-800/40 rounded px-4 py-3">
                    <div class="flex items-center gap-2 mb-2">
                      <span class="text-red-400 text-lg">&#x2717;</span>
                      <span class="text-red-300 font-medium font-display">Execution failed</span>
                    </div>
                    <p class="text-xs text-red-300/80">{{ executionResult.error || 'Unknown error' }}</p>
                  </div>

                  <!-- Device results -->
                  <div v-if="executionResult.device_results?.length" class="border border-gray-700 rounded overflow-hidden">
                    <div
                      v-for="dr in executionResult.device_results"
                      :key="dr.device_id"
                      class="border-b border-gray-800 last:border-0 px-3 py-2"
                    >
                      <div class="flex items-center gap-2">
                        <span :class="dr.status === 'success' ? 'text-green-400' : 'text-red-400'">
                          {{ dr.status === 'success' ? '&#x2713;' : '&#x2717;' }}
                        </span>
                        <span class="font-mono text-sm text-gray-200">{{ dr.device_id }}</span>
                        <span :class="dr.status === 'success' ? 'badge-up' : 'badge-down'" class="badge text-xs ml-auto">{{ dr.status }}</span>
                      </div>
                      <pre v-if="dr.output" class="mt-1 text-xs font-mono text-gray-400 overflow-x-auto whitespace-pre">{{ dr.output }}</pre>
                    </div>
                  </div>
                </div>
              </div>
            </template>
          </div>

          <!-- Footer -->
          <div class="flex items-center justify-end gap-2 px-5 py-4 border-t border-gray-700/50 shrink-0">
            <template v-if="currentStep < 3">
              <button class="btn-ghost px-3 py-1.5 text-sm" @click="$emit('close')">Cancel</button>
              <button
                v-if="currentStep > 0"
                class="btn-ghost px-3 py-1.5 text-sm"
                @click="currentStep--"
              >Back</button>
              <button
                v-if="currentStep < 2"
                class="btn-primary px-4 py-1.5 text-sm font-medium"
                :disabled="!canAdvance"
                @click="advanceStep"
              >Next</button>
              <button
                v-if="currentStep === 2"
                class="inline-flex items-center gap-1.5 px-4 py-1.5 text-sm font-medium rounded bg-orange-600 hover:bg-orange-500 active:bg-orange-700 text-white transition-colors"
                :disabled="dryRunLoading"
                @click="executeNow"
              >
                <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z"/>
                </svg>
                Execute
              </button>
            </template>
            <template v-else>
              <button class="btn-ghost px-3 py-1.5 text-sm" @click="$emit('close')">
                {{ executionResult ? 'Close' : 'Cancel' }}
              </button>
              <button
                v-if="executionResult"
                class="btn-secondary px-3 py-1.5 text-sm"
                @click="$emit('view-history')"
              >View History</button>
            </template>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { playbookDryRun, executePlaybook } from '../api.js'

const props = defineProps({
  show: { type: Boolean, default: false },
  playbook: { type: Object, required: true },
  devices: { type: Array, default: () => [] },
  preSelectedDevice: { type: Object, default: null },
  credentials: { type: Object, default: () => ({}) },
})

const emit = defineEmits(['close', 'done', 'view-history'])

const stepLabels = ['Devices', 'Variables', 'Preview', 'Execute']
const currentStep = ref(0)
const selectedDeviceIds = ref(new Set())
const variableValues = ref({})
const dryRunPreview = ref('')
const dryRunErrors = ref([])
const dryRunPreCheckOutputs = ref({})
const dryRunConfigDiffError = ref('')
const dryRunLoading = ref(false)
const executing = ref(false)
const executionResult = ref(null)
const executionStatusMsg = ref('')

const canClose = computed(() => !executing.value)

// Filter devices by platform compatibility
const compatibleDevices = computed(() => {
  const platforms = props.playbook.platform || []
  if (platforms.length === 0) return props.devices
  return props.devices.filter(d => {
    if (!d.platform) return true
    const p = d.platform.toLowerCase()
    return platforms.some(plat => p.includes(plat))
  })
})

const canAdvance = computed(() => {
  if (currentStep.value === 0) return selectedDeviceIds.value.size > 0
  if (currentStep.value === 1) return variablesValid.value
  return true
})

const variablesValid = computed(() => {
  for (const v of (props.playbook.variables || [])) {
    if (v.required && !variableValues.value[v.name] && variableValues.value[v.name] !== 0) {
      return false
    }
  }
  return true
})

function toggleDevice(id) {
  const newSet = new Set(selectedDeviceIds.value)
  if (newSet.has(id)) {
    newSet.delete(id)
  } else {
    newSet.add(id)
  }
  selectedDeviceIds.value = newSet
}

function deviceName(id) {
  const dev = props.devices.find(d => d.id === id)
  return dev?.hostname || id
}

function interpolate(text) {
  let result = text
  for (const [key, val] of Object.entries(variableValues.value)) {
    result = result.replaceAll(`{{${key}}}`, val ?? '')
  }
  return result
}

function interpolateLines(lines) {
  return (lines || []).map(interpolate)
}

const interpolatedCommands = computed(() => {
  return interpolateLines(props.playbook.steps || []).join('\n')
})

// Step indicator styling
function stepCircleClass(idx) {
  if (currentStep.value > idx || (currentStep.value === 4 && executionResult.value?.status === 'success')) {
    return 'bg-orange-500 text-white'
  }
  if (currentStep.value === 4 && executionResult.value?.status === 'failed' && idx === 3) {
    return 'bg-red-500 text-white'
  }
  if (currentStep.value === idx) {
    return 'bg-orange-500/20 text-orange-400 border border-orange-500'
  }
  return 'bg-gray-800 text-gray-600 border border-gray-700'
}

async function advanceStep() {
  if (currentStep.value === 1) {
    // Moving to preview — trigger dry-run
    currentStep.value = 2
    dryRunLoading.value = true
    dryRunErrors.value = []
    dryRunPreCheckOutputs.value = {}
    dryRunConfigDiffError.value = ''
    try {
      // Pick first selected device for config diff preview
      const firstDevId = [...selectedDeviceIds.value][0]
      const firstDev = props.devices.find(d => d.id === firstDevId)
      const payload = {
        variables: variableValues.value,
      }
      // Include device + credentials for config diff capture
      if (firstDev && props.credentials?.username) {
        payload.device_ip = firstDev.mgmt_ip || firstDev.ip || ''
        payload.device_platform = firstDev.platform || null
        payload.username = props.credentials.username
        payload.password = props.credentials.password
        payload.enable_password = props.credentials.enable_password || null
      }
      const resp = await playbookDryRun(props.playbook.id, payload)
      dryRunPreview.value = resp.steps?.join('\n') || ''
      dryRunErrors.value = resp.errors || []
      dryRunPreCheckOutputs.value = resp.pre_check_outputs || {}
      dryRunConfigDiffError.value = resp.config_diff_error || ''
    } catch {
      dryRunPreview.value = ''
    } finally {
      dryRunLoading.value = false
    }
    return
  }
  currentStep.value++
}

async function executeNow() {
  currentStep.value = 3
  executing.value = true
  executionResult.value = null
  executionStatusMsg.value = 'Connecting to devices…'

  try {
    const statusMessages = [
      'Connecting to devices…',
      'Running pre-checks…',
      'Applying configuration…',
      'Running post-checks…',
    ]
    let msgIdx = 0
    const msgTimer = setInterval(() => {
      msgIdx = Math.min(msgIdx + 1, statusMessages.length - 1)
      executionStatusMsg.value = statusMessages[msgIdx]
    }, 2000)

    // Build device_ips and device_platforms maps from selected devices
    const deviceIps = {}
    const devicePlatforms = {}
    for (const id of selectedDeviceIds.value) {
      const dev = props.devices.find(d => d.id === id)
      if (dev) {
        deviceIps[id] = dev.mgmt_ip || dev.ip || ''
        if (dev.platform) devicePlatforms[id] = dev.platform
      }
    }

    const result = await executePlaybook(props.playbook.id, {
      device_ids: [...selectedDeviceIds.value],
      device_ips: deviceIps,
      device_platforms: devicePlatforms,
      variables: variableValues.value,
      username: props.credentials.username || '',
      password: props.credentials.password || '',
      enable_password: props.credentials.enable_password || null,
    })

    clearInterval(msgTimer)
    currentStep.value = 4
    executionResult.value = result
    emit('done', result)
  } catch (e) {
    currentStep.value = 4
    executionResult.value = {
      status: 'failed',
      error: e.message || 'Execution failed',
    }
  } finally {
    executing.value = false
  }
}

// Reset state when modal opens
watch(() => props.show, (v) => {
  if (v) {
    currentStep.value = 0
    executionResult.value = null
    executing.value = false
    dryRunPreview.value = ''
    // Initialize variable defaults
    const vals = {}
    for (const v of (props.playbook.variables || [])) {
      vals[v.name] = v.default || ''
    }
    variableValues.value = vals
    // Pre-select device if provided
    if (props.preSelectedDevice) {
      selectedDeviceIds.value = new Set([props.preSelectedDevice.id])
    } else {
      selectedDeviceIds.value = new Set()
    }
  }
})
</script>

<style scoped>
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.15s ease;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
