<template>
  <div class="flex flex-col h-full overflow-hidden">
    <!-- Header -->
    <div class="flex items-center justify-between px-4 py-3 border-b border-gray-700 shrink-0">
      <div>
        <h2 class="font-semibold text-gray-100">Snapshot History</h2>
        <p class="text-xs text-gray-400 mt-0.5">{{ snapshots.length }} snapshot{{ snapshots.length !== 1 ? 's' : '' }} stored</p>
      </div>
      <button class="btn-ghost p-1 text-gray-500 hover:text-gray-200" @click="$emit('close')">✕</button>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="flex-1 flex items-center justify-center text-gray-500 text-sm">
      Loading snapshots…
    </div>

    <!-- Error -->
    <div v-else-if="error" class="flex-1 flex items-center justify-center text-red-400 text-sm px-4 text-center">
      {{ error }}
    </div>

    <!-- Empty state -->
    <div v-else-if="snapshots.length === 0" class="flex-1 flex flex-col items-center justify-center text-gray-600 text-sm gap-2">
      <span class="text-3xl">📂</span>
      <p>No snapshots yet.</p>
      <p class="text-xs">Run a discovery to create the first snapshot.</p>
    </div>

    <!-- Snapshot list (timeline) -->
    <div v-else class="flex-1 overflow-y-auto">
      <!-- Compare bar: shown when 2 snapshots are selected -->
      <div
        v-if="compareSelected.length === 2"
        class="sticky top-0 z-10 flex items-center gap-2 px-3 py-2 bg-amber-900/30 border-b border-amber-700/50"
      >
        <span class="text-xs text-amber-300 flex-1">
          Comparing <span class="font-mono">{{ compareSelected[0].slice(0, 8) }}</span>
          vs <span class="font-mono">{{ compareSelected[1].slice(0, 8) }}</span>
        </span>
        <button
          class="text-xs px-2 py-1 rounded bg-amber-700 hover:bg-amber-600 text-white font-medium"
          @click="openCompare"
        >
          Δ Compare
        </button>
        <button
          class="text-xs text-amber-500 hover:text-amber-300"
          @click="compareSelected = []"
        >
          Clear
        </button>
      </div>
      <div v-else-if="compareSelected.length === 1" class="sticky top-0 z-10 px-3 py-2 bg-gray-800/80 border-b border-gray-700 text-xs text-gray-400">
        Select one more snapshot to compare
      </div>

      <!-- Timeline rows -->
      <div class="relative">
        <!-- Vertical timeline line -->
        <div class="absolute left-[22px] top-0 bottom-0 w-px bg-gray-700/50"></div>

        <div
          v-for="snap in snapshots"
          :key="snap.session_id"
          class="relative flex items-start gap-3 px-4 py-3 border-b border-gray-800/50 transition-colors"
          :class="[
            activeId === snap.session_id ? 'bg-orange-900/20' : 'hover:bg-gray-800/40',
            compareSelected.includes(snap.session_id) ? 'bg-amber-900/15' : '',
          ]"
        >
          <!-- Timeline dot -->
          <div
            class="shrink-0 w-3 h-3 rounded-full border-2 mt-1 z-10"
            :class="activeId === snap.session_id
              ? 'border-orange-400 bg-orange-400'
              : compareSelected.includes(snap.session_id)
                ? 'border-orange-400 bg-orange-400'
                : 'border-gray-600 bg-gray-800'"
          ></div>

          <!-- Content -->
          <div class="flex-1 min-w-0">
            <div class="flex items-center gap-2">
              <span class="text-xs text-gray-300 font-medium">{{ formatDate(snap.discovered_at) }}</span>
              <span v-if="activeId === snap.session_id" class="text-xs text-orange-400 font-medium">• current</span>
            </div>
            <div class="flex items-center gap-3 mt-0.5 text-xs text-gray-500">
              <span>{{ snap.device_count }} device{{ snap.device_count !== 1 ? 's' : '' }}</span>
              <span>{{ snap.link_count }} link{{ snap.link_count !== 1 ? 's' : '' }}</span>
              <span v-if="snap.failure_count > 0" class="text-red-500/70">{{ snap.failure_count }} failure{{ snap.failure_count !== 1 ? 's' : '' }}</span>
            </div>
            <div class="text-xs text-gray-700 font-mono mt-0.5">{{ snap.session_id.slice(0, 8) }}…</div>
          </div>

          <!-- Actions -->
          <div class="flex items-center gap-1.5 shrink-0">
            <!-- Compare checkbox -->
            <button
              class="text-xs px-1.5 py-0.5 rounded transition-colors"
              :class="compareSelected.includes(snap.session_id)
                ? 'bg-amber-800/50 text-amber-300'
                : 'text-gray-600 hover:text-orange-400 hover:bg-amber-900/20'"
              :title="compareSelected.includes(snap.session_id) ? 'Remove from comparison' : 'Add to comparison'"
              :disabled="compareSelected.length === 2 && !compareSelected.includes(snap.session_id)"
              @click.stop="toggleCompare(snap.session_id)"
            >
              Δ
            </button>
            <!-- Load button -->
            <button
              class="text-xs px-2 py-0.5 rounded transition-colors"
              :class="activeId === snap.session_id
                ? 'text-gray-600 cursor-default'
                : 'text-orange-500 hover:text-orange-300 hover:bg-orange-900/20'"
              :disabled="activeId === snap.session_id"
              @click.stop="loadSnapshot(snap.session_id)"
            >
              {{ activeId === snap.session_id ? 'loaded' : 'Load' }}
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { listSnapshots } from '../api.js'

defineProps({
  activeId: { type: String, default: null },
})

const emit = defineEmits(['close', 'snapshot-loaded', 'compare'])

const snapshots = ref([])
const loading = ref(false)
const error = ref(null)
const compareSelected = ref([])

function formatDate(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  return d.toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}

async function fetchSnapshots() {
  loading.value = true
  error.value = null
  try {
    snapshots.value = await listSnapshots()
  } catch (e) {
    error.value = e.message || 'Failed to load snapshots'
  } finally {
    loading.value = false
  }
}

function toggleCompare(id) {
  const idx = compareSelected.value.indexOf(id)
  if (idx >= 0) {
    compareSelected.value = compareSelected.value.filter((x) => x !== id)
  } else if (compareSelected.value.length < 2) {
    compareSelected.value = [...compareSelected.value, id]
  }
}

function loadSnapshot(id) {
  emit('snapshot-loaded', id)
}

function openCompare() {
  if (compareSelected.value.length !== 2) return
  // Emit (current=newer, previous=older) — order by position in list (top = newest)
  const [a, b] = compareSelected.value
  const idxA = snapshots.value.findIndex((s) => s.session_id === a)
  const idxB = snapshots.value.findIndex((s) => s.session_id === b)
  const [current, previous] = idxA <= idxB ? [a, b] : [b, a]
  emit('compare', { current, previous })
}

onMounted(fetchSnapshots)
</script>
