<template>
  <!-- Advanced Mode toggle — always visible -->
  <div class="flex items-center gap-2">
    <button
      class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded text-xs font-medium whitespace-nowrap shrink-0 transition-all duration-150"
      :class="active
        ? 'bg-orange-500/20 text-orange-400 border border-orange-500/40 shadow-[0_0_8px_rgba(249,115,22,0.15)]'
        : 'bg-gray-800 text-gray-400 border border-gray-600 hover:text-gray-200 hover:border-gray-500'"
      :title="active ? 'Advanced Mode is ON — click to disable' : 'Enable Advanced Mode for write operations'"
      @click="handleToggle"
    >
      <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
          d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4.5c-.77-.833-2.694-.833-3.464 0L3.34 16.5c-.77.833.192 2.5 1.732 2.5z"/>
      </svg>
      Advanced
      <span
        class="inline-block w-1.5 h-1.5 rounded-full"
        :class="active ? 'bg-orange-400' : 'bg-gray-600'"
      />
    </button>

    <!-- Warning modal on enable -->
    <Teleport to="body">
      <Transition name="fade">
        <div v-if="showWarning" class="fixed inset-0 z-50 flex items-center justify-center" role="alertdialog" aria-modal="true" aria-label="Advanced mode warning">
          <div class="absolute inset-0 bg-black/60 backdrop-blur-sm" @click="cancelEnable" />
          <div class="relative bg-gray-900 border border-gray-700 rounded-lg shadow-xl w-full max-w-md mx-4 overflow-hidden">
            <!-- Header -->
            <div class="flex items-center gap-3 px-5 pt-5 pb-3">
              <div class="flex items-center justify-center w-10 h-10 rounded-full bg-orange-500/15">
                <svg class="w-5 h-5 text-orange-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                    d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4.5c-.77-.833-2.694-.833-3.464 0L3.34 16.5c-.77.833.192 2.5 1.732 2.5z"/>
                </svg>
              </div>
              <div>
                <h3 class="text-base font-semibold text-gray-100 font-display">Enable Advanced Mode?</h3>
                <p class="text-xs text-gray-500">Configuration changes will be possible</p>
              </div>
            </div>

            <!-- Body -->
            <div class="px-5 py-3">
              <p class="text-sm text-gray-300 mb-3">
                Advanced Mode allows <span class="text-orange-400 font-medium">configuration changes</span>
                on discovered devices. Changes include:
              </p>
              <ul class="text-sm text-gray-400 space-y-1.5 mb-4">
                <li class="flex items-start gap-2">
                  <span class="text-orange-500 mt-0.5">*</span>
                  <span>VLAN assignment on switch ports</span>
                </li>
                <li class="flex items-start gap-2">
                  <span class="text-gray-600 mt-0.5">*</span>
                  <span class="text-gray-500">More operations in future releases</span>
                </li>
              </ul>

              <!-- Password field -->
              <div v-if="passwordRequired" class="mb-4">
                <label class="block text-xs font-medium text-gray-400 mb-1.5">Password</label>
                <input
                  ref="passwordInput"
                  v-model="password"
                  type="password"
                  class="w-full bg-gray-800 border border-gray-600 rounded px-3 py-2 text-sm text-gray-200 placeholder-gray-500 focus:outline-none focus:border-orange-500/50 focus:ring-1 focus:ring-orange-500/30"
                  placeholder="Enter Advanced Mode password"
                  @keydown.enter="confirmEnable"
                />
                <p v-if="authError" class="mt-1.5 text-xs text-red-400">{{ authError }}</p>
              </div>

              <div class="bg-gray-800/60 border border-gray-700 rounded px-3 py-2.5 text-xs text-gray-400 space-y-1">
                <p>All changes are <span class="text-gray-200">logged</span> and <span class="text-gray-200">reversible</span>.</p>
                <p>Changes require <span class="text-gray-200">explicit confirmation</span> before execution.</p>
              </div>
            </div>

            <!-- Footer -->
            <div class="flex items-center justify-end gap-2 px-5 py-4 border-t border-gray-700/50">
              <button
                class="btn-ghost px-3 py-1.5 text-sm"
                @click="cancelEnable"
              >
                Cancel
              </button>
              <button
                class="btn-primary px-4 py-1.5 text-sm font-medium"
                :disabled="authenticating"
                @click="confirmEnable"
              >
                {{ authenticating ? 'Verifying...' : 'Enable Advanced Mode' }}
              </button>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, nextTick } from 'vue'
import { getAdvancedStatus, authenticateAdvanced } from '../api.js'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
})
const emit = defineEmits(['update:modelValue'])

const active = computed(() => props.modelValue)
const showWarning = ref(false)
const passwordRequired = ref(false)
const password = ref('')
const authError = ref('')
const authenticating = ref(false)
const passwordInput = ref(null)

onMounted(async () => {
  try {
    const resp = await getAdvancedStatus()
    passwordRequired.value = resp.password_required === true
  } catch {
    // Default: no password required
  }
})

function handleToggle() {
  if (active.value) {
    emit('update:modelValue', false)
  } else {
    showWarning.value = true
    password.value = ''
    authError.value = ''
    if (passwordRequired.value) {
      nextTick(() => passwordInput.value?.focus())
    }
  }
}

async function confirmEnable() {
  if (passwordRequired.value) {
    if (!password.value) {
      authError.value = 'Password is required'
      return
    }
    authenticating.value = true
    authError.value = ''
    try {
      await authenticateAdvanced(password.value)
    } catch {
      authError.value = 'Invalid password'
      authenticating.value = false
      return
    }
    authenticating.value = false
  }
  showWarning.value = false
  emit('update:modelValue', true)
}

function cancelEnable() {
  showWarning.value = false
  password.value = ''
  authError.value = ''
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
