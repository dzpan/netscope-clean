<template>
  <div class="flex flex-col h-full overflow-hidden">
    <!-- Header -->
    <div class="flex items-center justify-between px-4 py-3 border-b border-gray-700 shrink-0">
      <div>
        <h2 class="font-semibold text-gray-100 font-display text-sm">Playbooks</h2>
        <p class="text-xs text-gray-500">{{ filteredPlaybooks.length }} playbook{{ filteredPlaybooks.length !== 1 ? 's' : '' }}</p>
      </div>
      <div class="flex items-center gap-2">
        <button
          class="btn-primary btn-sm text-xs"
          title="Create new playbook"
          @click="$emit('create')"
        >+ New</button>
        <button
          class="btn-ghost btn-sm text-xs text-gray-400"
          title="Import from YAML"
          @click="$emit('import')"
        >Import</button>
        <button class="btn-ghost p-1 text-gray-500 hover:text-gray-200" @click="$emit('close')">&#x2715;</button>
      </div>
    </div>

    <!-- Search + filter -->
    <div class="flex items-center gap-2 px-4 py-2 border-b border-gray-700/50 shrink-0">
      <input
        v-model="search"
        type="text"
        placeholder="Search playbooks…"
        class="input input-sm flex-1"
        aria-label="Search playbooks"
      />
      <select
        v-model="filterCategory"
        class="select text-xs bg-gray-800 border-gray-600 py-1"
        aria-label="Filter by category"
      >
        <option value="">All categories</option>
        <option v-for="cat in categories" :key="cat" :value="cat">{{ cat }}</option>
      </select>
      <select
        v-model="filterPlatform"
        class="select text-xs bg-gray-800 border-gray-600 py-1"
        aria-label="Filter by platform"
      >
        <option value="">All platforms</option>
        <option value="iosxe">IOS-XE</option>
        <option value="nxos">NX-OS</option>
        <option value="cbs">CBS</option>
      </select>
    </div>

    <!-- Playbook list -->
    <div class="flex-1 overflow-y-auto">
      <div v-if="loadingList" class="flex items-center justify-center py-12 text-gray-500">
        <svg class="animate-spin w-5 h-5 mr-2" viewBox="0 0 24 24" fill="none">
          <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"/>
          <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z"/>
        </svg>
        Loading…
      </div>

      <div v-else-if="filteredPlaybooks.length === 0" class="flex flex-col items-center justify-center h-full text-gray-600 gap-2 py-12">
        <svg class="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5"
            d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10"/>
        </svg>
        <p class="text-xs">No playbooks{{ search || filterCategory || filterPlatform ? ' matching filters' : '' }}</p>
        <button
          v-if="!search && !filterCategory && !filterPlatform"
          class="btn-primary btn-sm text-xs mt-2"
          @click="$emit('create')"
        >Create your first playbook</button>
      </div>

      <template v-else>
        <div
          v-for="pb in filteredPlaybooks"
          :key="pb.id"
          class="border-b border-gray-800 hover:bg-gray-800/50 cursor-pointer transition-colors"
          @click="$emit('select', pb)"
        >
          <div class="px-4 py-3">
            <div class="flex items-start justify-between gap-2">
              <div class="min-w-0 flex-1">
                <h3 class="text-sm font-medium text-gray-100 truncate">{{ pb.title }}</h3>
                <p v-if="pb.description" class="text-xs text-gray-500 mt-0.5 line-clamp-2">{{ pb.description }}</p>
              </div>
              <div class="flex items-center gap-1 shrink-0">
                <button
                  class="btn-ghost p-1 text-gray-500 hover:text-orange-400"
                  title="Run playbook"
                  @click.stop="$emit('execute', pb)"
                >
                  <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z"/>
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/>
                  </svg>
                </button>
                <button
                  class="btn-ghost p-1 text-gray-500 hover:text-gray-200"
                  title="Edit playbook"
                  @click.stop="$emit('edit', pb)"
                >
                  <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                      d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z"/>
                  </svg>
                </button>
              </div>
            </div>
            <div class="flex items-center gap-2 mt-2">
              <span class="badge bg-gray-800 text-gray-400 text-xs">{{ pb.category || 'uncategorized' }}</span>
              <span
                v-for="plat in (pb.platform || [])"
                :key="plat"
                class="badge text-xs"
                :class="platformBadge(plat)"
              >{{ plat }}</span>
              <span class="text-xs text-gray-600 ml-auto font-mono">{{ pb.steps?.length || 0 }} steps</span>
            </div>
          </div>
        </div>
      </template>
    </div>

    <!-- Footer: Run History link -->
    <div class="flex items-center justify-between px-4 py-2 border-t border-gray-700 shrink-0 bg-gray-900">
      <button
        class="text-xs text-gray-500 hover:text-gray-300 transition-colors"
        @click="$emit('show-history')"
      >View Run History</button>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { listPlaybooks } from '../api.js'

defineProps({})
/* eslint-disable no-unused-vars */
const emit = defineEmits(['close', 'create', 'edit', 'select', 'execute', 'import', 'show-history'])
/* eslint-enable no-unused-vars */

const search = ref('')
const filterCategory = ref('')
const filterPlatform = ref('')
const playbooks = ref([])
const loadingList = ref(false)

const categories = computed(() => {
  const set = new Set(playbooks.value.map(p => p.category).filter(Boolean))
  return [...set].sort()
})

const filteredPlaybooks = computed(() => {
  let list = playbooks.value
  const q = search.value.toLowerCase()
  if (q) {
    list = list.filter(p =>
      (p.title || '').toLowerCase().includes(q) ||
      (p.description || '').toLowerCase().includes(q)
    )
  }
  if (filterCategory.value) {
    list = list.filter(p => p.category === filterCategory.value)
  }
  if (filterPlatform.value) {
    list = list.filter(p => (p.platform || []).includes(filterPlatform.value))
  }
  return list
})

function platformBadge(plat) {
  const map = {
    iosxe: 'bg-green-900/40 text-green-400',
    nxos: 'bg-purple-900/40 text-purple-300',
    cbs: 'bg-orange-900/40 text-orange-400',
  }
  return map[plat] || 'bg-gray-700 text-gray-400'
}

async function fetchPlaybooks() {
  loadingList.value = true
  try {
    const resp = await listPlaybooks()
    playbooks.value = resp.playbooks || resp || []
  } catch {
    playbooks.value = []
  } finally {
    loadingList.value = false
  }
}

// Expose refresh for parent
defineExpose({ refresh: fetchPlaybooks })

onMounted(fetchPlaybooks)
</script>
