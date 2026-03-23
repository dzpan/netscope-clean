<template>
  <div class="flex flex-col h-full bg-gray-900">
    <!-- Header -->
    <div class="flex items-center justify-between px-4 py-3 border-b border-gray-700 shrink-0">
      <span class="text-sm font-semibold text-gray-200">Path Trace</span>
      <button class="text-gray-500 hover:text-gray-300 text-lg leading-none" @click="$emit('close')">✕</button>
    </div>

    <!-- Form -->
    <div class="px-4 py-3 border-b border-gray-700 shrink-0 space-y-2">
      <div>
        <label class="block text-xs text-gray-400 mb-1">Source (IP or hostname)</label>
        <input
          v-model="source"
          type="text"
          placeholder="e.g. 10.0.0.1 or CORE-SW-01"
          class="w-full bg-gray-800 border border-gray-600 rounded px-2 py-1 text-sm text-gray-200 placeholder-gray-500 focus:outline-none focus:border-orange-500 focus:ring-1 focus:ring-orange-500"
          @keydown.enter="runTrace"
        />
      </div>
      <div>
        <label class="block text-xs text-gray-400 mb-1">Destination (IP or hostname)</label>
        <input
          v-model="dest"
          type="text"
          placeholder="e.g. 10.0.1.5 or ACCESS-SW-03"
          class="w-full bg-gray-800 border border-gray-600 rounded px-2 py-1 text-sm text-gray-200 placeholder-gray-500 focus:outline-none focus:border-orange-500 focus:ring-1 focus:ring-orange-500"
          @keydown.enter="runTrace"
        />
      </div>
      <div class="flex gap-2 pt-1">
        <button
          class="flex-1 btn-primary text-xs py-1.5"
          :class="{ 'opacity-50 cursor-not-allowed': loading || !source || !dest }"
          :disabled="loading || !source || !dest"
          @click="runTrace"
        >
          {{ loading ? 'Tracing…' : '⟶ Trace Path' }}
        </button>
        <button
          v-if="result"
          class="btn-secondary text-xs py-1.5 px-3"
          title="Clear results"
          @click="clearResult"
        >
          Clear
        </button>
      </div>
    </div>

    <!-- Results -->
    <div class="flex-1 overflow-y-auto">
      <!-- Error -->
      <div v-if="error" class="m-3 px-3 py-2 bg-red-900/30 border border-red-800 rounded text-xs text-red-300">
        {{ error }}
      </div>

      <!-- Success/failure result -->
      <div v-if="result" class="p-3 space-y-3">
        <!-- Status badge -->
        <div class="flex items-center gap-2">
          <span
            class="inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full font-medium"
            :class="result.success ? 'bg-green-900/50 text-green-300 border border-green-700' : 'bg-red-900/50 text-red-300 border border-red-700'"
          >
            <span>{{ result.success ? '✓' : '✗' }}</span>
            <span>{{ result.success ? 'Path found' : 'Path broken' }}</span>
          </span>
          <span class="text-xs text-gray-500">{{ result.hops.length }} hop{{ result.hops.length !== 1 ? 's' : '' }}</span>
        </div>

        <!-- Break reason -->
        <div v-if="!result.success && result.error" class="text-xs text-amber-300 bg-amber-900/20 border border-amber-800/50 rounded px-2 py-1.5">
          {{ result.error }}
        </div>

        <!-- Hop table -->
        <div v-if="result.hops.length" class="space-y-1">
          <div class="text-xs font-medium text-gray-400 uppercase tracking-wider mb-2">Hops</div>
          <div
            v-for="hop in result.hops"
            :key="hop.hop_number"
            class="flex items-start gap-2 text-xs p-2 rounded"
            :class="hop.hop_number === result.hops.length && result.success ? 'bg-green-900/20 border border-green-800/40' : 'bg-gray-800/50'"
          >
            <!-- Hop number -->
            <span class="shrink-0 w-5 h-5 rounded-full bg-gray-700 text-gray-300 flex items-center justify-center text-xs font-mono font-bold">
              {{ hop.hop_number }}
            </span>
            <div class="min-w-0 flex-1">
              <!-- Device -->
              <div class="flex items-center gap-1.5 flex-wrap">
                <button
                  class="font-medium text-orange-400 hover:text-orange-300 hover:underline"
                  @click="$emit('device-selected', hop.device_id)"
                >
                  {{ hop.hostname || hop.device_id }}
                </button>
                <span class="text-gray-500 font-mono">{{ hop.mgmt_ip }}</span>
              </div>
              <!-- Interface + next-hop -->
              <div v-if="hop.out_interface || hop.next_hop_ip" class="mt-0.5 text-gray-500 font-mono">
                <span v-if="hop.out_interface">out: {{ hop.out_interface }}</span>
                <span v-if="hop.out_interface && hop.next_hop_ip"> → </span>
                <span v-if="hop.next_hop_ip">via {{ hop.next_hop_ip }}</span>
              </div>
            </div>
            <!-- Final hop indicator -->
            <span v-if="hop.hop_number === result.hops.length && result.success" class="shrink-0 text-green-400 text-base">⬛</span>
          </div>
        </div>

        <!-- Path summary -->
        <div v-if="result.hops.length > 1" class="text-xs text-gray-500 font-mono bg-gray-800/30 rounded px-2 py-1.5 leading-relaxed">
          {{ result.hops.map(h => h.hostname || h.device_id).join(' → ') }}
        </div>
      </div>

      <!-- Empty state -->
      <div v-if="!result && !error && !loading" class="flex flex-col items-center justify-center h-40 text-gray-600 text-xs text-center px-4">
        <svg class="w-8 h-8 mb-2 opacity-40" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5"
            d="M13 10V3L4 14h7v7l9-11h-7z"/>
        </svg>
        Enter source and destination to trace the L3 path through the topology
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { pathTrace } from '../api.js'

const props = defineProps({
  sessionId: { type: String, required: true },
})

const emit = defineEmits(['close', 'device-selected', 'path-result'])

const source = ref('')
const dest = ref('')
const loading = ref(false)
const error = ref(null)
const result = ref(null)

async function runTrace() {
  if (!source.value || !dest.value || loading.value) return
  loading.value = true
  error.value = null
  result.value = null
  try {
    const res = await pathTrace(props.sessionId, { source: source.value, dest: dest.value })
    result.value = res
    emit('path-result', res)
  } catch (e) {
    error.value = e.message || 'Path trace failed'
    emit('path-result', null)
  } finally {
    loading.value = false
  }
}

function clearResult() {
  result.value = null
  error.value = null
  emit('path-result', null)
}
</script>
