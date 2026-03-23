<template>
  <Teleport to="body">
    <Transition name="fade">
      <div v-if="show" class="fixed inset-0 z-50 flex items-center justify-center" role="dialog" aria-modal="true" aria-label="Change progress">
        <div class="absolute inset-0 bg-black/60 backdrop-blur-sm" />
        <div class="relative bg-gray-900 border border-gray-700 rounded-lg shadow-xl w-full max-w-md mx-4 overflow-hidden">

          <!-- Header -->
          <div class="px-5 pt-5 pb-3">
            <h3 v-if="!result" class="text-base font-semibold text-gray-100 font-display">
              Applying changes to {{ deviceName }}...
            </h3>
            <h3 v-else-if="result.status === 'success'" class="text-base font-semibold text-green-400 font-display flex items-center gap-2">
              <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"/>
              </svg>
              Changes Applied Successfully
            </h3>
            <h3 v-else class="text-base font-semibold text-red-400 font-display flex items-center gap-2">
              <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
              </svg>
              Change Failed
            </h3>
          </div>

          <!-- Progress steps -->
          <div class="px-5 py-3 space-y-3">
            <div
              v-for="(s, i) in steps"
              :key="s.label"
              class="flex items-center gap-3"
            >
              <!-- Step icon -->
              <div class="shrink-0">
                <svg v-if="s.state === 'done'" class="w-5 h-5 text-green-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"/>
                </svg>
                <svg v-else-if="s.state === 'active'" class="w-5 h-5 text-orange-400 animate-spin" viewBox="0 0 24 24" fill="none">
                  <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"/>
                  <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z"/>
                </svg>
                <svg v-else-if="s.state === 'failed'" class="w-5 h-5 text-red-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
                </svg>
                <div v-else class="w-5 h-5 rounded-full border-2 border-gray-700" />
              </div>
              <!-- Step text -->
              <div class="flex-1 min-w-0">
                <p
                  class="text-sm"
                  :class="{
                    'text-green-400': s.state === 'done',
                    'text-orange-300': s.state === 'active',
                    'text-red-400': s.state === 'failed',
                    'text-gray-600': s.state === 'pending',
                  }"
                >
                  Step {{ i + 1 }}/4: {{ s.label }}
                </p>
                <p v-if="s.detail" class="text-xs text-gray-500 truncate">{{ s.detail }}</p>
              </div>
            </div>
          </div>

          <!-- Result details (when done) -->
          <div v-if="result" class="px-5 py-3 border-t border-gray-700/50">
            <!-- Success: verification results -->
            <template v-if="result.status === 'success' && result.changes?.length">
              <p class="text-xs text-gray-500 mb-2">Verification:</p>
              <div class="space-y-1">
                <div
                  v-for="c in result.changes"
                  :key="c.interface"
                  class="flex items-center gap-2 text-sm"
                >
                  <svg v-if="c.verified" class="w-4 h-4 text-green-400 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"/>
                  </svg>
                  <svg v-else class="w-4 h-4 text-amber-400 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01"/>
                  </svg>
                  <span class="font-mono text-gray-300">{{ c.interface }}</span>
                  <span class="text-gray-500">VLAN {{ c.old_value }} -> {{ c.new_value }}</span>
                  <span v-if="c.verified" class="text-green-500 text-xs">(confirmed)</span>
                </div>
              </div>
              <p v-if="result.write_memory" class="text-xs text-gray-500 mt-2">Configuration saved (write memory)</p>
              <p v-if="result.id" class="text-xs text-gray-600 mt-1 font-mono">Change ID: {{ result.id }}</p>
            </template>

            <!-- Failure: error message -->
            <template v-else-if="result.status === 'failed'">
              <div class="bg-red-900/20 border border-red-800/40 rounded px-3 py-2 text-sm text-red-300">
                {{ result.error || 'Change failed — automatic rollback attempted.' }}
              </div>
            </template>
          </div>

          <!-- Footer -->
          <div v-if="result" class="flex items-center justify-end gap-2 px-5 py-4 border-t border-gray-700/50">
            <button
              v-if="result.status === 'success'"
              class="btn-secondary px-3 py-1.5 text-sm"
              @click="$emit('view-audit')"
            >
              View Audit Log
            </button>
            <button
              class="btn-primary px-4 py-1.5 text-sm font-medium"
              @click="$emit('close')"
            >
              Done
            </button>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  show: { type: Boolean, default: false },
  deviceName: { type: String, default: '' },
  /** Current step index (0-3) — controlled by parent during execution */
  currentStep: { type: Number, default: 0 },
  /** Result object from backend when execution completes */
  result: { type: Object, default: null },
  /** Error string if a step fails before result */
  errorAtStep: { type: Number, default: -1 },
})

defineEmits(['close', 'view-audit'])

const STEP_LABELS = [
  { label: 'Connected to device', detail: 'SSH session established' },
  { label: 'Pre-check \u2014 captured current state', detail: 'Saved interface configuration for rollback' },
  { label: 'Applying configuration...', detail: 'Sending commands via SSH' },
  { label: 'Post-check \u2014 verifying changes', detail: 'Confirming VLAN assignment applied' },
]

const steps = computed(() =>
  STEP_LABELS.map((s, i) => {
    let state = 'pending'
    if (props.errorAtStep === i) state = 'failed'
    else if (props.result && props.result.status === 'failed' && i >= props.currentStep) state = 'failed'
    else if (props.result && i < 4) state = i < props.currentStep ? 'done' : (props.result.status === 'success' ? 'done' : 'pending')
    else if (i < props.currentStep) state = 'done'
    else if (i === props.currentStep && !props.result) state = 'active'
    return { ...s, state }
  })
)
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
