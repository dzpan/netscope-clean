<template>
  <Teleport to="body">
    <Transition name="fade">
      <div v-if="show" class="fixed inset-0 z-50 flex items-center justify-center" role="dialog" aria-modal="true" aria-label="Change VLAN assignment">
        <div class="absolute inset-0 bg-black/60 backdrop-blur-sm" @click="$emit('close')" />
        <div class="relative bg-gray-900 border border-gray-700 rounded-lg shadow-xl w-full max-w-lg mx-4 overflow-hidden max-h-[85vh] flex flex-col">

          <!-- Step 1: Choose VLAN -->
          <template v-if="step === 'pick'">
            <div class="px-5 pt-5 pb-3 border-b border-gray-700/50 shrink-0">
              <h3 class="text-base font-semibold text-gray-100 font-display">Change VLAN Assignment</h3>
              <p class="text-xs text-gray-500 mt-0.5">{{ device.hostname || device.id }} &middot; {{ device.mgmt_ip }}</p>
            </div>

            <div class="px-5 py-4 overflow-y-auto flex-1 flex flex-col gap-4">
              <!-- Selected ports summary -->
              <div>
                <p class="text-xs text-gray-500 mb-1.5">Selected Ports ({{ ports.length }})</p>
                <div class="flex flex-wrap gap-1">
                  <span
                    v-for="p in ports"
                    :key="p.name"
                    class="badge bg-gray-800 text-gray-300 font-mono text-xs"
                  >
                    {{ p.name }}
                    <span class="text-gray-600 ml-0.5">VLAN {{ p.vlan }}</span>
                  </span>
                </div>
              </div>

              <!-- VLAN picker -->
              <div>
                <label class="label">New VLAN</label>
                <input
                  v-model="vlanSearch"
                  type="text"
                  placeholder="Search VLANs..."
                  class="input input-sm mb-2"
                  aria-label="Search VLANs"
                />
                <div class="max-h-40 overflow-y-auto border border-gray-700 rounded bg-gray-800/50">
                  <div
                    v-for="vlan in filteredVlans"
                    :key="vlan.vlan_id"
                    class="flex items-center gap-2 px-3 py-1.5 text-sm cursor-pointer transition-colors"
                    :class="vlan.vlan_id === selectedVlan
                      ? 'bg-orange-500/15 text-orange-300'
                      : isCurrent(vlan.vlan_id)
                        ? 'text-gray-600 cursor-not-allowed'
                        : 'text-gray-300 hover:bg-gray-700/50'"
                    @click="!isCurrent(vlan.vlan_id) && (selectedVlan = vlan.vlan_id)"
                  >
                    <span class="font-mono w-10 text-right shrink-0">{{ vlan.vlan_id }}</span>
                    <span class="truncate">{{ vlan.name || '' }}</span>
                    <span v-if="isCurrent(vlan.vlan_id)" class="ml-auto text-xs text-gray-600">(current)</span>
                    <span v-else-if="vlan.vlan_id === selectedVlan" class="ml-auto text-xs text-orange-500">selected</span>
                  </div>
                  <p v-if="filteredVlans.length === 0" class="px-3 py-2 text-xs text-gray-600">No matching VLANs</p>
                </div>
              </div>

              <!-- Optional description -->
              <div>
                <label class="flex items-center gap-2 text-xs text-gray-400 cursor-pointer select-none">
                  <input v-model="setDescription" type="checkbox" class="accent-orange-500" />
                  Set port description (optional)
                </label>
                <input
                  v-if="setDescription"
                  v-model="newDescription"
                  type="text"
                  placeholder="e.g. Floor 2 — Data"
                  class="input input-sm mt-1.5"
                  aria-label="Port description"
                />
              </div>

              <!-- Write memory toggle -->
              <label class="flex items-center gap-2 text-sm text-gray-300 cursor-pointer select-none">
                <input v-model="writeMem" type="checkbox" class="accent-orange-500" />
                Save configuration (write memory)
              </label>
            </div>

            <div class="flex items-center justify-end gap-2 px-5 py-4 border-t border-gray-700/50 shrink-0">
              <button class="btn-ghost px-3 py-1.5 text-sm" @click="$emit('close')">Cancel</button>
              <button
                class="btn-primary px-4 py-1.5 text-sm font-medium"
                :disabled="!selectedVlan"
                @click="step = 'review'"
              >
                Review Changes
              </button>
            </div>
          </template>

          <!-- Step 2: Review & Confirm -->
          <template v-if="step === 'review'">
            <div class="px-5 pt-5 pb-3 border-b border-gray-700/50 shrink-0">
              <div class="flex items-center gap-2">
                <svg class="w-5 h-5 text-orange-400 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                    d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4.5c-.77-.833-2.694-.833-3.464 0L3.34 16.5c-.77.833.192 2.5 1.732 2.5z"/>
                </svg>
                <h3 class="text-base font-semibold text-gray-100 font-display">Review Configuration Changes</h3>
              </div>
            </div>

            <div class="px-5 py-4 overflow-y-auto flex-1 flex flex-col gap-4">
              <!-- Device info -->
              <dl class="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-sm">
                <dt class="text-gray-500">Device</dt>
                <dd class="text-gray-200 font-mono">{{ device.hostname || device.id }} ({{ device.mgmt_ip }})</dd>
                <dt class="text-gray-500">Platform</dt>
                <dd class="text-gray-300">{{ device.platform || 'Unknown' }}</dd>
              </dl>

              <!-- Commands preview -->
              <div>
                <p class="text-xs text-gray-500 mb-1.5">Commands to execute:</p>
                <pre class="bg-gray-950 border border-gray-700 rounded p-3 text-xs font-mono text-orange-300 overflow-x-auto whitespace-pre">{{ commandPreview }}</pre>
              </div>

              <!-- Summary -->
              <div class="text-sm text-gray-300 space-y-1">
                <p>
                  * {{ ports.length }} port{{ ports.length > 1 ? 's' : '' }} changing from
                  <span class="font-mono">{{ currentVlanSummary }}</span> to
                  <span class="font-mono text-orange-400">VLAN {{ selectedVlan }}</span>
                  <span v-if="selectedVlanName" class="text-gray-500">({{ selectedVlanName }})</span>
                </p>
                <p v-if="writeMem">* Configuration will be saved (write memory)</p>
                <p v-else class="text-gray-500">* Running-config only (not saved to startup)</p>
              </div>

              <!-- Warning -->
              <div class="bg-orange-900/15 border border-orange-800/40 rounded px-3 py-2.5 text-xs text-orange-300/80">
                <p class="font-medium text-orange-300 mb-1">Traffic Impact</p>
                <p>This will affect live network traffic on {{ ports.length > 1 ? 'these ports' : 'this port' }}. Connected devices will experience a brief link interruption.</p>
              </div>

              <p class="text-xs text-gray-500">Rollback: Available via Audit Log</p>
            </div>

            <div class="flex items-center justify-end gap-2 px-5 py-4 border-t border-gray-700/50 shrink-0">
              <button class="btn-ghost px-3 py-1.5 text-sm" @click="step = 'pick'">Back</button>
              <button class="btn-ghost px-3 py-1.5 text-sm" @click="$emit('close')">Cancel</button>
              <button
                class="inline-flex items-center gap-1.5 px-4 py-1.5 text-sm font-medium rounded bg-orange-600 hover:bg-orange-500 active:bg-orange-700 text-white transition-colors"
                @click="applyChanges"
              >
                <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                    d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4.5c-.77-.833-2.694-.833-3.464 0L3.34 16.5c-.77.833.192 2.5 1.732 2.5z"/>
                </svg>
                Apply Changes
              </button>
            </div>
          </template>

        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup>
import { ref, computed } from 'vue'

const props = defineProps({
  show: { type: Boolean, default: false },
  device: { type: Object, required: true },
  ports: { type: Array, required: true },    // selected interface objects
  vlans: { type: Array, default: () => [] }, // device vlans from device.vlans
  credentials: { type: Object, default: () => ({}) },
})

const emit = defineEmits(['close', 'apply'])

const step = ref('pick')
const vlanSearch = ref('')
const selectedVlan = ref(null)
const setDescription = ref(false)
const newDescription = ref('')
const writeMem = ref(true)

// Current VLANs on selected ports
const currentVlans = computed(() => {
  const set = new Set(props.ports.map(p => p.vlan).filter(Boolean))
  return [...set]
})

const currentVlanSummary = computed(() => {
  if (currentVlans.value.length === 1) {
    const v = currentVlans.value[0]
    const vlan = props.vlans.find(vl => String(vl.vlan_id) === String(v))
    return `VLAN ${v}${vlan?.name ? ' (' + vlan.name + ')' : ''}`
  }
  return `VLANs ${currentVlans.value.join(', ')}`
})

function isCurrent(vlanId) {
  return currentVlans.value.length === 1 && String(currentVlans.value[0]) === String(vlanId)
}

const filteredVlans = computed(() => {
  const q = vlanSearch.value.toLowerCase()
  if (!q) return props.vlans
  return props.vlans.filter(v =>
    String(v.vlan_id).includes(q) ||
    (v.name && v.name.toLowerCase().includes(q))
  )
})

const selectedVlanName = computed(() => {
  const v = props.vlans.find(vl => vl.vlan_id === selectedVlan.value)
  return v?.name || null
})

const commandPreview = computed(() => {
  const lines = ['configure terminal']
  for (const p of props.ports) {
    lines.push(`  interface ${p.name}`)
    lines.push(`    switchport access vlan ${selectedVlan.value}`)
    if (setDescription.value && newDescription.value) {
      lines.push(`    description ${newDescription.value}`)
    }
    lines.push('  exit')
  }
  lines.push('end')
  if (writeMem.value) lines.push('write memory')
  return lines.join('\n')
})

function applyChanges() {
  emit('apply', {
    device_id: props.device.id,
    device_ip: props.device.mgmt_ip,
    platform: props.device.platform || null,
    interfaces: props.ports.map(p => p.name),
    target_vlan: selectedVlan.value,
    description: setDescription.value ? newDescription.value : null,
    write_memory: writeMem.value,
    username: props.credentials.username || '',
    password: props.credentials.password || '',
    enable_password: props.credentials.enable_password || null,
  })
}
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
