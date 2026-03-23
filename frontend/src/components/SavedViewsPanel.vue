<template>
  <div class="flex flex-col h-full">
    <!-- Panel header -->
    <div class="panel-header flex items-center justify-between">
      <div class="flex items-center gap-2">
        <svg class="w-4 h-4 text-orange-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
            d="M5 5a2 2 0 012-2h10a2 2 0 012 2v16l-7-3.5L5 21V5z"/>
        </svg>
        <span class="font-display font-semibold text-gray-100">Saved Views</span>
        <span class="badge bg-gray-800 text-gray-400 text-xs">{{ views.length }}</span>
      </div>
      <button class="text-gray-500 hover:text-gray-300" @click="$emit('close')">✕</button>
    </div>

    <div class="panel-body flex-1 overflow-y-auto p-3 space-y-3">
      <!-- Save current view -->
      <div class="card p-3">
        <div class="text-xs text-gray-500 uppercase tracking-wider mb-2 font-semibold">Save Current View</div>
        <div class="flex gap-2">
          <input
            v-model="newViewName"
            type="text"
            placeholder="View name…"
            class="input input-sm flex-1"
            @keydown.enter="saveCurrentView"
          />
          <button
            class="btn-primary btn-sm whitespace-nowrap"
            :disabled="!newViewName.trim() || saving"
            @click="saveCurrentView"
          >
            {{ saving ? 'Saving…' : '+ Save' }}
          </button>
        </div>
        <label class="flex items-center gap-2 mt-2 text-xs text-gray-400 cursor-pointer">
          <input v-model="newViewDefault" type="checkbox" class="rounded border-gray-600 bg-gray-800 text-orange-500 focus:ring-orange-500" />
          Set as default view
        </label>
      </div>

      <!-- Loading state -->
      <div v-if="loadingViews" class="flex items-center justify-center py-8">
        <svg class="animate-spin w-5 h-5 text-orange-500" viewBox="0 0 24 24" fill="none">
          <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"/>
          <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z"/>
        </svg>
      </div>

      <!-- Empty state -->
      <div v-else-if="views.length === 0" class="empty-state py-8">
        <svg class="w-10 h-10 mx-auto mb-3 text-gray-700" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1"
            d="M5 5a2 2 0 012-2h10a2 2 0 012 2v16l-7-3.5L5 21V5z"/>
        </svg>
        <p class="text-gray-500 text-sm">No saved views yet</p>
        <p class="text-gray-600 text-xs mt-1">Save the current topology layout to quickly recall it later</p>
      </div>

      <!-- Saved views list -->
      <div v-else class="space-y-2">
        <div
          v-for="view in views"
          :key="view.view_id"
          class="card p-3 group transition-colors"
          :class="activeViewId === view.view_id ? 'border-orange-500/50 bg-orange-500/5' : 'hover:border-gray-600'"
        >
          <div class="flex items-start justify-between gap-2">
            <div class="flex-1 min-w-0">
              <!-- Editable name -->
              <div v-if="renamingId === view.view_id" class="flex gap-1 items-center">
                <input
                  ref="renameInput"
                  v-model="renameValue"
                  type="text"
                  class="input input-sm flex-1 text-sm"
                  @keydown.enter="confirmRename(view.view_id)"
                  @keydown.escape="renamingId = null"
                  @blur="confirmRename(view.view_id)"
                />
              </div>
              <div v-else class="flex items-center gap-2">
                <span class="text-sm font-semibold text-gray-100 truncate font-display">{{ view.name }}</span>
                <span v-if="view.is_default" class="badge bg-orange-900/30 text-orange-400 text-[10px]">default</span>
              </div>

              <!-- Metadata -->
              <div class="flex items-center gap-3 mt-1 text-[11px] text-gray-500">
                <span class="font-mono">{{ view.session_id.slice(0, 8) }}</span>
                <span>{{ view.node_positions.length }} nodes</span>
                <span v-if="view.annotations.length">{{ view.annotations.length }} annotation{{ view.annotations.length !== 1 ? 's' : '' }}</span>
                <span v-if="view.protocol_filter !== 'all'" class="text-purple-400">{{ view.protocol_filter.toUpperCase() }}</span>
              </div>

              <!-- Description -->
              <p v-if="view.description" class="text-xs text-gray-500 mt-1 line-clamp-2">{{ view.description }}</p>

              <!-- Timestamp -->
              <div class="text-[10px] text-gray-600 mt-1">
                {{ formatTime(view.updated_at) }}
              </div>
            </div>

            <!-- Actions -->
            <div class="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity shrink-0">
              <button
                class="btn-ghost p-1 text-xs"
                title="Load this view"
                @click="$emit('load-view', view)"
              >
                <svg class="w-3.5 h-3.5 text-orange-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"/>
                </svg>
              </button>
              <button
                class="btn-ghost p-1 text-xs"
                title="Rename"
                @click="startRename(view)"
              >
                <svg class="w-3.5 h-3.5 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"/>
                </svg>
              </button>
              <button
                v-if="!view.is_default"
                class="btn-ghost p-1 text-xs"
                title="Set as default"
                @click="handleSetDefault(view.view_id)"
              >
                <svg class="w-3.5 h-3.5 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11.049 2.927c.3-.921 1.603-.921 1.902 0l1.519 4.674a1 1 0 00.95.69h4.915c.969 0 1.371 1.24.588 1.81l-3.976 2.888a1 1 0 00-.363 1.118l1.518 4.674c.3.922-.755 1.688-1.538 1.118l-3.976-2.888a1 1 0 00-1.176 0l-3.976 2.888c-.783.57-1.838-.197-1.538-1.118l1.518-4.674a1 1 0 00-.363-1.118l-3.976-2.888c-.784-.57-.38-1.81.588-1.81h4.914a1 1 0 00.951-.69l1.519-4.674z"/>
                </svg>
              </button>
              <button
                class="btn-ghost p-1 text-xs"
                title="Update with current layout"
                @click="$emit('update-view', view)"
              >
                <svg class="w-3.5 h-3.5 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/>
                </svg>
              </button>
              <button
                class="btn-ghost p-1 text-xs"
                title="Delete view"
                @click="handleDelete(view.view_id)"
              >
                <svg class="w-3.5 h-3.5 text-red-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"/>
                </svg>
              </button>
            </div>
          </div>

          <!-- Annotation preview -->
          <div v-if="view.annotations.length" class="mt-2 pt-2 border-t border-gray-700/50 space-y-1">
            <div class="text-[10px] text-gray-500 uppercase tracking-wider font-semibold">Annotations</div>
            <div
              v-for="ann in view.annotations.slice(0, 3)"
              :key="ann.annotation_id"
              class="flex items-start gap-2 text-xs"
            >
              <span
                class="w-2 h-2 rounded-full mt-1 shrink-0"
                :style="{ backgroundColor: ann.color }"
              />
              <span class="text-gray-400 truncate">
                <span v-if="ann.target_id" class="font-mono text-gray-500">{{ ann.target_id.slice(0, 20) }}</span>
                {{ ann.text }}
              </span>
            </div>
            <div v-if="view.annotations.length > 3" class="text-[10px] text-gray-600">
              +{{ view.annotations.length - 3 }} more
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, nextTick } from 'vue'
import { listViews, deleteView, renameView, setDefaultView } from '../api.js'

const props = defineProps({
  sessionId: { type: String, default: null },
  activeViewId: { type: String, default: null },
})

const emit = defineEmits(['close', 'load-view', 'update-view', 'save-view'])

const views = ref([])
const loadingViews = ref(false)
const saving = ref(false)
const newViewName = ref('')
const newViewDefault = ref(false)
const renamingId = ref(null)
const renameValue = ref('')
const renameInput = ref(null)

async function fetchViews() {
  loadingViews.value = true
  try {
    views.value = await listViews(props.sessionId)
  } catch {
    views.value = []
  } finally {
    loadingViews.value = false
  }
}

async function saveCurrentView() {
  if (!newViewName.value.trim()) return
  saving.value = true
  try {
    emit('save-view', {
      name: newViewName.value.trim(),
      is_default: newViewDefault.value,
    })
    newViewName.value = ''
    newViewDefault.value = false
    // Refresh after a short delay to allow parent to complete save
    setTimeout(fetchViews, 500)
  } finally {
    saving.value = false
  }
}

function startRename(view) {
  renamingId.value = view.view_id
  renameValue.value = view.name
  nextTick(() => {
    renameInput.value?.[0]?.focus()
  })
}

async function confirmRename(viewId) {
  if (!renameValue.value.trim()) {
    renamingId.value = null
    return
  }
  try {
    await renameView(viewId, renameValue.value.trim())
    await fetchViews()
  } catch { /* ignore */ }
  renamingId.value = null
}

async function handleSetDefault(viewId) {
  try {
    await setDefaultView(viewId)
    await fetchViews()
  } catch { /* ignore */ }
}

async function handleDelete(viewId) {
  try {
    await deleteView(viewId)
    views.value = views.value.filter(v => v.view_id !== viewId)
  } catch { /* ignore */ }
}

function formatTime(isoStr) {
  if (!isoStr) return ''
  const d = new Date(isoStr)
  return d.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

onMounted(fetchViews)

defineExpose({ fetchViews })
</script>
