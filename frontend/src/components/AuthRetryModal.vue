<template>
  <Teleport to="body">
    <div class="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm" role="dialog" aria-modal="true" aria-labelledby="auth-retry-title">
      <div class="card w-[480px] max-w-[90vw] flex flex-col shadow-2xl border-amber-800/40">

        <!-- Header -->
        <div class="flex items-center justify-between px-5 py-4 border-b border-gray-700">
          <div>
            <h2 id="auth-retry-title" class="font-semibold text-orange-400 flex items-center gap-2">
              <span aria-hidden="true">⚠</span> Authentication Required
            </h2>
            <p class="text-xs text-gray-500 mt-0.5">
              Device {{ currentIdx + 1 }} of {{ queue.length }}
            </p>
          </div>
          <!-- Progress dots -->
          <div class="flex gap-1.5">
            <span
              v-for="(_, i) in queue"
              :key="i"
              class="w-2 h-2 rounded-full transition-colors"
              :class="i < currentIdx ? 'bg-orange-500'
                    : i === currentIdx ? 'bg-orange-400'
                    : 'bg-gray-600'"
            />
          </div>
        </div>

        <!-- Body -->
        <div class="p-5 flex flex-col gap-4">

          <!-- Current device -->
          <div class="bg-gray-900/60 rounded-lg px-4 py-3 border border-gray-700">
            <div class="text-base text-gray-100 font-mono">{{ current.target }}</div>
            <div class="text-xs text-amber-600 mt-0.5">{{ current.detail }}</div>
            <div class="text-xs text-gray-600 mt-1.5 flex items-center gap-1">
              <span class="px-1.5 py-0.5 rounded bg-gray-800 font-mono">
                {{ authTypeLabel }}
              </span>
            </div>
          </div>

          <!-- Enable password — shown when failure is enable-related -->
          <div v-if="needsEnable">
            <label class="label">Enable Password</label>
            <input
              ref="enableInput"
              v-model="form.enable_password"
              type="password"
              class="input"
              placeholder="••••••••"
              autocomplete="off"
              @keyup.enter="handleRetry"
            />
          </div>

          <!-- SSH credentials — shown when failure is login-related -->
          <template v-if="needsSsh">
            <div>
              <label class="label">Username</label>
              <input
                ref="usernameInput"
                v-model="form.username"
                type="text"
                class="input"
                autocomplete="username"
                @keyup.enter="handleRetry"
              />
            </div>
            <div>
              <label class="label">Password</label>
              <input
                v-model="form.password"
                type="password"
                class="input"
                autocomplete="current-password"
                @keyup.enter="handleRetry"
              />
            </div>
          </template>

          <!-- When type is SSH, still allow specifying enable if needed -->
          <div v-if="needsSsh">
            <button
              class="text-xs text-gray-600 hover:text-orange-400 text-left flex items-center gap-1 w-fit"
              @click="showEnableOverride = !showEnableOverride"
            >
              <span class="font-mono">{{ showEnableOverride ? '▼' : '▶' }}</span>
              Also set enable password
            </button>
            <div v-if="showEnableOverride" class="mt-2">
              <input
                v-model="form.enable_password"
                type="password"
                class="input"
                placeholder="enable password (optional)"
                autocomplete="off"
              />
            </div>
          </div>

          <!-- When type is enable, still allow overriding SSH creds if needed -->
          <div v-if="needsEnable">
            <button
              class="text-xs text-gray-600 hover:text-orange-400 text-left flex items-center gap-1 w-fit"
              @click="showSshOverride = !showSshOverride"
            >
              <span class="font-mono">{{ showSshOverride ? '▼' : '▶' }}</span>
              Also override username / password
            </button>
            <template v-if="showSshOverride">
              <div class="mt-2">
                <label class="label">Username</label>
                <input v-model="form.username" type="text" class="input" autocomplete="username" />
              </div>
              <div class="mt-2">
                <label class="label">Password</label>
                <input v-model="form.password" type="password" class="input" autocomplete="current-password" />
              </div>
            </template>
          </div>

          <!-- Retry error -->
          <div v-if="retryError" class="text-xs text-red-400 bg-red-900/20 border border-red-800 rounded p-2.5 flex items-start gap-2">
            <span class="shrink-0 mt-0.5">✕</span>
            <span>{{ retryError }}</span>
          </div>

          <!-- Success flash -->
          <div v-if="lastSuccess" class="text-xs text-orange-400 bg-orange-900/20 border border-orange-800 rounded p-2.5 flex items-center gap-2">
            <span>✓</span>
            <span>{{ lastSuccess }}</span>
          </div>
        </div>

        <!-- Apply-to-all result -->
        <div v-if="applyAllResult" class="px-5 pb-3">
          <div class="text-xs rounded p-2.5 flex items-start gap-2"
            :class="applyAllResult.failed > 0
              ? 'text-orange-400 bg-amber-900/20 border border-amber-800'
              : 'text-orange-400 bg-orange-900/20 border border-orange-800'"
          >
            <span>{{ applyAllResult.failed > 0 ? '⚠' : '✓' }}</span>
            <span>{{ applyAllResult.succeeded }} succeeded, {{ applyAllResult.failed }} failed</span>
          </div>
        </div>

        <!-- Footer -->
        <div class="px-5 py-3 border-t border-gray-700 flex items-center gap-2">
          <button class="btn-ghost text-gray-500 mr-auto text-sm" @click="emit('close', 'user')">
            Close
          </button>
          <button class="btn-ghost text-sm" :disabled="retrying" @click="skip">
            Skip
          </button>
          <button
            v-if="remaining > 1"
            class="btn-secondary flex items-center gap-2 text-sm"
            :disabled="retrying"
            @click="handleApplyToAll"
          >
            <svg v-if="retrying && applyingAll" class="animate-spin h-3.5 w-3.5" viewBox="0 0 24 24" fill="none">
              <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"/>
              <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z"/>
            </svg>
            <span v-if="retrying && applyingAll">Trying all…</span>
            <span v-else>Apply to all ({{ remaining }})</span>
          </button>
          <button
            class="btn-primary flex items-center gap-2"
            :disabled="retrying"
            @click="handleRetry"
          >
            <svg v-if="retrying && !applyingAll" class="animate-spin h-3.5 w-3.5" viewBox="0 0 24 24" fill="none">
              <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"/>
              <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z"/>
            </svg>
            <span v-if="retrying && !applyingAll">Trying…</span>
            <span v-else>Try credentials</span>
          </button>
        </div>

      </div>
    </div>
  </Teleport>
</template>

<script setup>
import { ref, computed, nextTick } from 'vue'
import { retryAuth } from '../api.js'

const props = defineProps({
  failures: { type: Array, default: () => [] },
  sessionId: { type: String, required: true },
  initialUsername: { type: String, default: '' },
  initialPassword: { type: String, default: '' },
})

const emit = defineEmits(['session-update', 'device-succeeded', 'close'])

// Build queue once on mount
const queue = ref(props.failures.map(f => ({ ...f })))
const currentIdx = ref(0)
const retrying = ref(false)
const retryError = ref(null)
const lastSuccess = ref(null)
const enableInput = ref(null)
const usernameInput = ref(null)
const showEnableOverride = ref(false)
const showSshOverride = ref(false)

const form = ref({
  enable_password: '',
  username: props.initialUsername,
  password: props.initialPassword,
})

const current = computed(() => queue.value[currentIdx.value])
const remaining = computed(() => queue.value.length - currentIdx.value)
const applyingAll = ref(false)
const applyAllResult = ref(null)

// Detect what type of auth failed from the error detail
function detectAuthType(detail) {
  const d = (detail || '').toLowerCase()
  if (d.includes('enable') || d.includes('privilege') || d.includes('authorized')) return 'enable'
  if (d.includes('permission denied') || d.includes('authentication failed') ||
      d.includes('incorrect') || d.includes('no matching host key') || d.includes('banner')) return 'ssh'
  return 'ssh'   // default to SSH credentials — the most common case
}

const authType = computed(() => detectAuthType(current.value?.detail))

const needsEnable = computed(() => authType.value === 'enable')
const needsSsh    = computed(() => authType.value === 'ssh')

const authTypeLabel = computed(() => ({
  enable: 'SSH login OK — needs enable password',
  ssh:    'SSH login failed — needs username / password',
}[authType.value] ?? 'Needs credentials'))

function resetOverrides() {
  showEnableOverride.value = false
  showSshOverride.value = false
}

function advance() {
  retryError.value = null
  lastSuccess.value = null
  resetOverrides()
  if (currentIdx.value < queue.value.length - 1) {
    currentIdx.value++
    nextTick(() => (usernameInput.value || enableInput.value)?.focus())
  } else {
    emit('close', 'done')
  }
}

function skip() {
  advance()
}

async function handleRetry() {
  retrying.value = true
  retryError.value = null
  lastSuccess.value = null
  try {
    const result = await retryAuth({
      session_id: props.sessionId,
      targets: [current.value.target],
      username: form.value.username,
      password: form.value.password,
      enable_password: form.value.enable_password || null,
      max_hops: 2,
    })

    emit('session-update', result)

    const stillFailed = result.failures.find(
      f => f.target === current.value.target && f.reason === 'auth_failed'
    )
    if (stillFailed) {
      retryError.value = stillFailed.detail || 'Authentication still failed'
    } else {
      lastSuccess.value = `${current.value.target} authenticated successfully`
      emit('device-succeeded', current.value.target)
      setTimeout(advance, 800)
    }
  } catch (e) {
    retryError.value = e.message || 'Retry failed'
  } finally {
    retrying.value = false
  }
}

async function handleApplyToAll() {
  retrying.value = true
  applyingAll.value = true
  retryError.value = null
  lastSuccess.value = null
  applyAllResult.value = null

  const targets = queue.value.slice(currentIdx.value).map(f => f.target)

  try {
    const result = await retryAuth({
      session_id: props.sessionId,
      targets,
      username: form.value.username,
      password: form.value.password,
      enable_password: form.value.enable_password || null,
      max_hops: 2,
    })

    emit('session-update', result)

    // Count successes vs remaining failures
    const stillFailedSet = new Set(
      result.failures.filter(f => f.reason === 'auth_failed').map(f => f.target)
    )
    let succeeded = 0
    for (const t of targets) {
      if (!stillFailedSet.has(t)) {
        succeeded++
        emit('device-succeeded', t)
      }
    }
    const failed = targets.length - succeeded

    applyAllResult.value = { succeeded, failed }

    // Auto-close after a short delay if all succeeded
    if (failed === 0) {
      setTimeout(() => emit('close', 'done'), 1200)
    }
  } catch (e) {
    retryError.value = e.message || 'Batch retry failed'
  } finally {
    retrying.value = false
    applyingAll.value = false
  }
}
</script>
