<template>
  <Teleport to="body">
    <Transition name="fade">
      <div v-if="show && record" class="fixed inset-0 z-50 flex items-center justify-center" role="dialog" aria-modal="true" aria-label="Change detail">
        <div class="absolute inset-0 bg-black/60 backdrop-blur-sm" @click="$emit('close')" />
        <div class="relative bg-gray-900 border border-gray-700 rounded-lg shadow-xl w-full max-w-xl mx-4 overflow-hidden max-h-[85vh] flex flex-col">

          <!-- Header -->
          <div class="px-5 pt-5 pb-3 border-b border-gray-700/50 shrink-0">
            <div class="flex items-center justify-between">
              <div>
                <h3 class="text-base font-semibold text-gray-100 font-display">Change Detail</h3>
                <p class="text-xs text-gray-500 font-mono mt-0.5">{{ record.id }}</p>
              </div>
              <span :class="statusBadge(record.status)" class="badge">{{ record.status }}</span>
            </div>
          </div>

          <!-- Body -->
          <div class="px-5 py-4 overflow-y-auto flex-1 flex flex-col gap-4">
            <!-- Metadata -->
            <dl class="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 text-sm">
              <dt class="text-gray-500">Device</dt>
              <dd class="text-gray-200 font-mono">{{ record.device_id }} ({{ record.device_ip }})</dd>
              <dt class="text-gray-500">Platform</dt>
              <dd class="text-gray-300">{{ record.platform || '—' }}</dd>
              <dt class="text-gray-500">Time</dt>
              <dd class="text-gray-300">{{ formatTimestamp(record.timestamp) }}</dd>
              <dt class="text-gray-500">Operation</dt>
              <dd class="text-gray-300">{{ record.operation }}</dd>
              <template v-if="record.rolled_back_at">
                <dt class="text-gray-500">Rolled back</dt>
                <dd class="text-orange-400 text-xs">
                  {{ formatTimestamp(record.rolled_back_at) }}
                  <span v-if="record.rolled_back_by" class="text-gray-500 font-mono ml-1">by {{ record.rolled_back_by }}</span>
                </dd>
              </template>
            </dl>

            <!-- Port changes -->
            <div v-if="record.changes?.length">
              <p class="text-xs text-gray-500 mb-1.5">Port Changes</p>
              <div class="space-y-1">
                <div
                  v-for="c in record.changes"
                  :key="c.interface"
                  class="flex items-center gap-2 text-sm bg-gray-800/40 rounded px-3 py-1.5"
                >
                  <span class="font-mono text-gray-300 shrink-0">{{ c.interface }}</span>
                  <span class="text-gray-500">{{ c.field }}:</span>
                  <span class="font-mono text-red-400/70">{{ c.old_value }}</span>
                  <span class="text-gray-600">-></span>
                  <span class="font-mono text-green-400/80">{{ c.new_value }}</span>
                  <svg v-if="c.verified" class="w-3.5 h-3.5 text-green-400 ml-auto shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"/>
                  </svg>
                </div>
              </div>
            </div>

            <!-- Commands sent -->
            <div v-if="record.commands_sent?.length">
              <p class="text-xs text-gray-500 mb-1.5">Commands Sent</p>
              <pre class="bg-gray-950 border border-gray-700 rounded p-3 text-xs font-mono text-orange-300 overflow-x-auto whitespace-pre max-h-40">{{ record.commands_sent.join('\n') }}</pre>
            </div>

            <!-- Rollback commands -->
            <div v-if="record.rollback_commands?.length && record.rollback_available">
              <p class="text-xs text-gray-500 mb-1.5">Rollback Commands</p>
              <pre class="bg-gray-950 border border-gray-700 rounded p-3 text-xs font-mono text-gray-400 overflow-x-auto whitespace-pre max-h-32">{{ record.rollback_commands.join('\n') }}</pre>
            </div>

            <!-- Pre/Post state diff -->
            <div v-if="record.pre_state || record.post_state" class="grid grid-cols-2 gap-3">
              <div v-if="record.pre_state">
                <p class="text-xs text-gray-500 mb-1.5">Pre-State</p>
                <pre class="bg-gray-950 border border-gray-700 rounded p-2 text-xs font-mono text-gray-400 overflow-x-auto whitespace-pre max-h-32">{{ formatState(record.pre_state) }}</pre>
              </div>
              <div v-if="record.post_state">
                <p class="text-xs text-gray-500 mb-1.5">Post-State</p>
                <pre class="bg-gray-950 border border-gray-700 rounded p-2 text-xs font-mono text-gray-400 overflow-x-auto whitespace-pre max-h-32">{{ formatState(record.post_state) }}</pre>
              </div>
            </div>

            <!-- Notes -->
            <p v-if="record.notes" class="text-xs text-gray-400 italic">{{ record.notes }}</p>
          </div>

          <!-- Footer -->
          <div class="flex items-center justify-end gap-2 px-5 py-4 border-t border-gray-700/50 shrink-0">
            <button
              v-if="record.status === 'success' && record.rollback_available"
              class="btn-secondary px-3 py-1.5 text-sm"
              @click="$emit('undo', record)"
            >
              Undo Change
            </button>
            <button
              class="btn-ghost px-3 py-1.5 text-sm"
              @click="$emit('close')"
            >
              Close
            </button>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup>
defineProps({
  show: { type: Boolean, default: false },
  record: { type: Object, default: null },
})

defineEmits(['close', 'undo'])

function statusBadge(status) {
  const map = {
    success: 'bg-green-900/50 text-green-400',
    failed: 'bg-red-900/50 text-red-400',
    rolled_back: 'bg-orange-900/50 text-orange-400',
  }
  return map[status] || 'bg-gray-700 text-gray-400'
}

function formatTimestamp(ts) {
  if (!ts) return '—'
  return new Date(ts).toLocaleString()
}

function formatState(state) {
  if (typeof state === 'string') return state
  return JSON.stringify(state, null, 2)
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
