<template>
  <div
    v-if="visible"
    class="fixed inset-0 z-50 flex items-center justify-center bg-black/60"
    role="dialog"
    aria-modal="true"
    aria-label="Discovery Summary"
    @click.self="$emit('close')"
    @keydown.escape="$emit('close')"
  >
    <div class="bg-gray-900 border border-gray-700 rounded-lg shadow-xl w-full max-w-3xl max-h-[85vh] overflow-y-auto">
      <!-- Header -->
      <div class="flex items-center justify-between px-5 py-3 border-b border-gray-700">
        <h2 class="text-lg font-semibold text-gray-100">Discovery Summary</h2>
        <button
          class="text-gray-500 hover:text-gray-300 text-xl leading-none"
          aria-label="Close"
          @click="$emit('close')"
        >&times;</button>
      </div>

      <!-- Loading state -->
      <div v-if="loading" class="p-8 text-center text-gray-500">
        Loading summary...
      </div>

      <!-- Error state -->
      <div v-else-if="error" class="p-6 text-center text-red-400">
        {{ error }}
      </div>

      <!-- Summary content -->
      <div v-else-if="summary" class="p-5 space-y-5">
        <!-- Top-level stats grid -->
        <div class="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <StatCard label="Devices" :value="summary.ok_devices" sublabel="discovered" color="green" />
          <StatCard label="Placeholders" :value="summary.placeholder_devices" sublabel="unresolved" color="orange" />
          <StatCard label="Failures" :value="summary.total_failures" sublabel="devices" color="red" />
          <StatCard label="Links" :value="summary.total_links" sublabel="connections" color="blue" />
        </div>

        <!-- Second row -->
        <div class="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <StatCard label="VLANs" :value="summary.total_vlans" color="purple" />
          <StatCard label="STP Roots" :value="summary.stp_root_bridges" color="teal" />
          <StatCard
            label="VLAN Mismatches"
            :value="summary.native_vlan_mismatches"
            :color="summary.native_vlan_mismatches > 0 ? 'red' : 'green'"
          />
          <StatCard label="Port-Channels" :value="summary.port_channel_links" color="blue" />
        </div>

        <!-- Interface health bar -->
        <div v-if="summary.total_interfaces > 0" class="bg-gray-800 rounded-lg p-4">
          <div class="flex items-center justify-between mb-2">
            <span class="text-sm font-medium text-gray-300">Interface Health</span>
            <span class="text-xs text-gray-500">
              {{ summary.total_interfaces }} total
            </span>
          </div>
          <div class="flex h-3 rounded-full overflow-hidden bg-gray-700">
            <div
              class="bg-green-500"
              :style="{ width: pctUp + '%' }"
              :title="`${summary.up_interfaces} up`"
            />
            <div
              class="bg-red-500"
              :style="{ width: pctDown + '%' }"
              :title="`${summary.down_interfaces} down`"
            />
            <div
              class="bg-gray-600"
              :style="{ width: pctOther + '%' }"
              :title="`${otherInterfaces} other`"
            />
          </div>
          <div class="flex justify-between mt-1 text-xs text-gray-500">
            <span class="text-green-400">{{ summary.up_interfaces }} up</span>
            <span class="text-red-400">{{ summary.down_interfaces }} down</span>
            <span v-if="otherInterfaces > 0">{{ otherInterfaces }} other</span>
          </div>
        </div>

        <!-- Breakdowns side-by-side -->
        <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <!-- Platform breakdown -->
          <div v-if="summary.platform_breakdown.length > 0" class="bg-gray-800 rounded-lg p-4">
            <h3 class="text-sm font-medium text-gray-300 mb-2">Platforms</h3>
            <div class="space-y-1.5">
              <div
                v-for="p in summary.platform_breakdown"
                :key="p.platform"
                class="flex items-center justify-between"
              >
                <span class="text-xs text-gray-400 truncate mr-2">{{ p.platform }}</span>
                <span class="text-xs font-mono text-gray-300 shrink-0">{{ p.count }}</span>
              </div>
            </div>
          </div>

          <!-- Failure breakdown -->
          <div v-if="summary.failure_breakdown.length > 0" class="bg-gray-800 rounded-lg p-4">
            <h3 class="text-sm font-medium text-gray-300 mb-2">Failure Reasons</h3>
            <div class="space-y-1.5">
              <div
                v-for="f in summary.failure_breakdown"
                :key="f.reason"
                class="flex items-center justify-between"
              >
                <span class="text-xs text-gray-400">
                  <span
                    class="inline-block w-2 h-2 rounded-full mr-1.5"
                    :class="failureColor(f.reason)"
                  />
                  {{ f.reason.replace('_', ' ') }}
                </span>
                <span class="text-xs font-mono text-gray-300">{{ f.count }}</span>
              </div>
            </div>
          </div>

          <!-- Protocol breakdown -->
          <div v-if="summary.protocol_breakdown.length > 0" class="bg-gray-800 rounded-lg p-4">
            <h3 class="text-sm font-medium text-gray-300 mb-2">Link Protocols</h3>
            <div class="space-y-1.5">
              <div
                v-for="p in summary.protocol_breakdown"
                :key="p.protocol"
                class="flex items-center justify-between"
              >
                <span class="text-xs text-gray-400">{{ p.protocol }}</span>
                <span class="text-xs font-mono text-gray-300">{{ p.count }}</span>
              </div>
            </div>
          </div>
        </div>

        <!-- Placeholder devices section -->
        <div v-if="placeholderDevices.length > 0" class="bg-gray-800 rounded-lg p-4">
          <div class="flex items-center justify-between mb-3">
            <h3 class="text-sm font-medium text-orange-400">Unresolved Placeholder Devices</h3>
            <span class="text-xs text-gray-500">{{ placeholderDevices.length }} devices</span>
          </div>
          <div class="space-y-2 max-h-48 overflow-y-auto">
            <div
              v-for="d in placeholderDevices"
              :key="d.id"
              class="flex items-center justify-between bg-gray-850 rounded px-3 py-2 border border-gray-700/50"
            >
              <div class="min-w-0 flex-1">
                <div class="text-sm text-gray-200 font-mono truncate">{{ d.id }}</div>
                <div class="text-xs text-gray-500">
                  IP: {{ d.mgmt_ip }} · Platform: {{ d.platform || 'Unknown' }}
                </div>
              </div>
              <div class="flex items-center gap-2 shrink-0 ml-3">
                <input
                  v-if="resolvingId === d.id"
                  v-model="resolveIp"
                  type="text"
                  placeholder="New IP"
                  class="w-32 bg-gray-700 border border-gray-600 rounded px-2 py-1 text-xs text-gray-100 placeholder-gray-500"
                  @keydown.enter="submitResolve(d.id)"
                  @keydown.escape="cancelResolve"
                />
                <button
                  v-if="resolvingId === d.id"
                  class="text-xs px-2 py-1 rounded bg-orange-600 hover:bg-orange-500 text-white"
                  :disabled="!resolveIp.trim()"
                  @click="submitResolve(d.id)"
                >
                  Apply
                </button>
                <button
                  v-if="resolvingId === d.id"
                  class="text-xs px-2 py-1 rounded text-gray-400 hover:text-gray-200"
                  @click="cancelResolve"
                >
                  Cancel
                </button>
                <button
                  v-else
                  class="text-xs px-2 py-1 rounded border border-orange-500/30 text-orange-400 hover:bg-orange-500/10"
                  @click="startResolve(d.id, d.mgmt_ip)"
                >
                  Resolve
                </button>
              </div>
            </div>
          </div>
          <div v-if="resolveError" class="mt-2 text-xs text-red-400">{{ resolveError }}</div>
        </div>

        <!-- Timestamp -->
        <div class="text-xs text-gray-600 text-right">
          Discovered {{ new Date(summary.discovered_at).toLocaleString() }}
          · Session {{ summary.session_id.slice(0, 8) }}
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { getSessionSummary, resolvePlaceholder } from '../api.js'

const props = defineProps({
  visible: { type: Boolean, default: false },
  sessionId: { type: String, default: null },
  devices: { type: Array, default: () => [] },
})

const emit = defineEmits(['close', 'session-updated'])

const summary = ref(null)
const loading = ref(false)
const error = ref(null)

// Placeholder resolution state
const resolvingId = ref(null)
const resolveIp = ref('')
const resolveError = ref(null)

const placeholderDevices = computed(() =>
  props.devices.filter(d => d.status === 'placeholder')
)

const pctUp = computed(() => {
  if (!summary.value || !summary.value.total_interfaces) return 0
  return Math.round((summary.value.up_interfaces / summary.value.total_interfaces) * 100)
})

const pctDown = computed(() => {
  if (!summary.value || !summary.value.total_interfaces) return 0
  return Math.round((summary.value.down_interfaces / summary.value.total_interfaces) * 100)
})

const otherInterfaces = computed(() => {
  if (!summary.value) return 0
  return summary.value.total_interfaces - summary.value.up_interfaces - summary.value.down_interfaces
})

const pctOther = computed(() => {
  if (!summary.value || !summary.value.total_interfaces) return 0
  return 100 - pctUp.value - pctDown.value
})

function failureColor(reason) {
  const colors = {
    auth_failed: 'bg-yellow-500',
    timeout: 'bg-orange-500',
    unreachable: 'bg-red-500',
    no_cdp_lldp: 'bg-purple-500',
    unknown: 'bg-gray-500',
  }
  return colors[reason] || 'bg-gray-500'
}

function startResolve(deviceId, currentIp) {
  resolvingId.value = deviceId
  resolveIp.value = currentIp === 'unknown' ? '' : currentIp
  resolveError.value = null
}

function cancelResolve() {
  resolvingId.value = null
  resolveIp.value = ''
  resolveError.value = null
}

async function submitResolve(deviceId) {
  if (!resolveIp.value.trim() || !props.sessionId) return
  resolveError.value = null
  try {
    const updated = await resolvePlaceholder(props.sessionId, {
      placeholder_device_id: deviceId,
      mgmt_ip: resolveIp.value.trim(),
    })
    emit('session-updated', updated)
    cancelResolve()
    // Refresh summary
    await fetchSummary()
  } catch (e) {
    resolveError.value = e.message || 'Failed to resolve placeholder'
  }
}

async function fetchSummary() {
  if (!props.sessionId) return
  loading.value = true
  error.value = null
  try {
    summary.value = await getSessionSummary(props.sessionId)
  } catch (e) {
    error.value = e.message || 'Failed to load summary'
  } finally {
    loading.value = false
  }
}

watch(
  () => [props.visible, props.sessionId],
  ([vis, sid]) => {
    if (vis && sid) fetchSummary()
  },
  { immediate: true }
)

// --- StatCard sub-component (inline) ---
</script>

<script>
// Inline StatCard component to avoid extra file
const StatCard = {
  props: {
    label: String,
    value: { type: Number, default: 0 },
    sublabel: { type: String, default: '' },
    color: { type: String, default: 'gray' },
  },
  template: `
    <div class="bg-gray-800 rounded-lg p-3 text-center">
      <div class="text-2xl font-bold font-mono" :class="textColor">{{ value }}</div>
      <div class="text-xs text-gray-400 mt-0.5">{{ label }}</div>
      <div v-if="sublabel" class="text-xs text-gray-600">{{ sublabel }}</div>
    </div>
  `,
  computed: {
    textColor() {
      const map = {
        green: 'text-green-400',
        orange: 'text-orange-400',
        red: 'text-red-400',
        blue: 'text-blue-400',
        purple: 'text-purple-400',
        teal: 'text-teal-400',
        gray: 'text-gray-300',
      }
      return map[this.color] || 'text-gray-300'
    },
  },
}
export default { components: { StatCard } }
</script>
