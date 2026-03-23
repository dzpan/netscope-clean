<template>
  <Teleport to="body">
    <div class="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm" role="dialog" aria-modal="true" aria-label="Discovery failures">
      <div class="card w-[640px] max-w-[90vw] max-h-[80vh] flex flex-col shadow-2xl border-red-800/40">

        <!-- Header -->
        <div class="flex items-center justify-between px-5 py-4 border-b border-gray-700">
          <div>
            <h2 class="font-semibold text-red-400 flex items-center gap-2">
              <span>&#9888;</span> Discovery Failures
            </h2>
            <p class="text-xs text-gray-500 mt-0.5">
              {{ failures.length }} device{{ failures.length !== 1 ? 's' : '' }} failed during discovery
            </p>
          </div>
          <div class="flex items-center gap-2">
            <!-- Reason filter pills -->
            <button
              v-for="r in reasonCounts"
              :key="r.reason"
              class="text-xs px-2 py-0.5 rounded-full border transition-colors"
              :class="activeFilter === r.reason
                ? 'border-orange-500 bg-orange-500/20 text-orange-400'
                : 'border-gray-600 text-gray-500 hover:text-gray-300'"
              @click="activeFilter = activeFilter === r.reason ? null : r.reason"
            >
              {{ r.reason }} ({{ r.count }})
            </button>
          </div>
        </div>

        <!-- Failures list -->
        <div class="flex-1 overflow-y-auto">
          <table class="w-full text-xs">
            <thead class="sticky top-0 bg-gray-900 z-10">
              <tr class="text-gray-500 border-b border-gray-700">
                <th class="text-left px-4 py-2">Target</th>
                <th class="text-left px-4 py-2">Reason</th>
                <th class="text-left px-4 py-2">Detail</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="(f, i) in filtered"
                :key="i"
                class="border-b border-gray-800 hover:bg-gray-800/50"
              >
                <td class="px-4 py-2 font-mono text-gray-300">{{ f.target }}</td>
                <td class="px-4 py-2">
                  <span :class="reasonBadge(f.reason)" class="badge">{{ f.reason }}</span>
                </td>
                <td class="px-4 py-2 text-gray-500 truncate max-w-xs" :title="f.detail">
                  {{ f.detail || '—' }}
                </td>
              </tr>
              <tr v-if="!filtered.length">
                <td colspan="3" class="px-4 py-6 text-center text-gray-600">No failures match filter</td>
              </tr>
            </tbody>
          </table>
        </div>

        <!-- Retry result banner -->
        <div v-if="retryResult" class="px-5 py-2">
          <div
            class="text-xs rounded p-2.5 flex items-start gap-2"
            :class="retryResult.stillFailed > 0
              ? 'text-orange-400 bg-amber-900/20 border border-amber-800'
              : 'text-green-400 bg-green-900/20 border border-green-800'"
          >
            <span>{{ retryResult.stillFailed > 0 ? '&#9888;' : '&#10003;' }}</span>
            <span>{{ retryResult.recovered }} recovered, {{ retryResult.stillFailed }} still failed</span>
          </div>
        </div>

        <!-- Error -->
        <div v-if="retryError" class="px-5 py-2">
          <div class="text-xs text-red-400 bg-red-900/20 border border-red-800 rounded p-2.5">
            {{ retryError }}
          </div>
        </div>

        <!-- Footer -->
        <div class="px-5 py-3 border-t border-gray-700 flex items-center gap-2">
          <button class="btn-ghost text-gray-500 mr-auto text-sm" @click="emit('close')">
            Close
          </button>
          <button
            class="btn-primary flex items-center gap-2"
            :disabled="retrying || !filtered.length"
            @click="handleRetryAll"
          >
            <svg v-if="retrying" class="animate-spin h-3.5 w-3.5" viewBox="0 0 24 24" fill="none">
              <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"/>
              <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z"/>
            </svg>
            <span v-if="retrying">Retrying {{ filtered.length }} device{{ filtered.length !== 1 ? 's' : '' }}…</span>
            <span v-else>Retry Failed ({{ filtered.length }})</span>
          </button>
        </div>

      </div>
    </div>
  </Teleport>
</template>

<script setup>
import { ref, computed } from 'vue'
import { retryFailed } from '../api.js'

const props = defineProps({
  failures: { type: Array, default: () => [] },
  sessionId: { type: String, required: true },
  credentialSets: { type: Array, default: () => [] },
  username: { type: String, default: '' },
  password: { type: String, default: '' },
  enablePassword: { type: String, default: '' },
})

const emit = defineEmits(['session-update', 'close'])

const activeFilter = ref(null)
const retrying = ref(false)
const retryError = ref(null)
const retryResult = ref(null)

const reasonCounts = computed(() => {
  const counts = {}
  for (const f of props.failures) {
    counts[f.reason] = (counts[f.reason] || 0) + 1
  }
  return Object.entries(counts)
    .map(([reason, count]) => ({ reason, count }))
    .sort((a, b) => b.count - a.count)
})

const filtered = computed(() => {
  if (!activeFilter.value) return props.failures
  return props.failures.filter(f => f.reason === activeFilter.value)
})

function reasonBadge(reason) {
  const map = {
    unreachable: 'bg-red-900/50 text-red-400',
    auth_failed: 'bg-orange-900/50 text-orange-400',
    timeout: 'bg-amber-900/50 text-amber-400',
    no_cdp_lldp: 'bg-purple-900/50 text-purple-400',
    unknown: 'bg-gray-700 text-gray-400',
  }
  return map[reason] || 'bg-gray-700 text-gray-400'
}

async function handleRetryAll() {
  retrying.value = true
  retryError.value = null
  retryResult.value = null

  const reasonFilter = activeFilter.value ? [activeFilter.value] : []

  try {
    const result = await retryFailed({
      session_id: props.sessionId,
      credential_sets: props.credentialSets,
      username: props.username,
      password: props.password,
      enable_password: props.enablePassword,
      reason_filter: reasonFilter,
    })

    const originalCount = filtered.value.length
    const stillFailed = result.failures.length
    const recovered = originalCount - stillFailed

    retryResult.value = { recovered: Math.max(0, recovered), stillFailed }
    emit('session-update', result)

    if (stillFailed === 0) {
      setTimeout(() => emit('close'), 1200)
    }
  } catch (e) {
    retryError.value = e.message || 'Retry failed'
  } finally {
    retrying.value = false
  }
}
</script>
