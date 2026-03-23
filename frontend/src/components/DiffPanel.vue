<template>
  <div class="flex flex-col h-full overflow-hidden">
    <!-- Header -->
    <div class="flex items-center justify-between px-4 py-3 border-b border-gray-700 shrink-0">
      <div>
        <h2 class="font-semibold text-gray-100">Topology Diff</h2>
        <p class="text-xs text-gray-400 font-mono mt-0.5">
          {{ currentId.slice(0, 8) }} vs {{ previousId.slice(0, 8) }}
        </p>
      </div>
      <button class="btn-ghost p-1 text-gray-500 hover:text-gray-200" @click="$emit('close')">✕</button>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="flex-1 flex items-center justify-center text-gray-500 text-sm">
      Computing diff…
    </div>

    <!-- Error -->
    <div v-else-if="error" class="flex-1 flex items-center justify-center text-red-400 text-sm px-4 text-center">
      {{ error }}
    </div>

    <!-- Content -->
    <div v-else-if="diff" class="flex-1 overflow-y-auto p-4 flex flex-col gap-4">

      <!-- Summary banner -->
      <div class="rounded-lg bg-gray-800 border border-gray-700 px-4 py-3 flex items-center gap-4 text-sm">
        <span class="text-gray-400">Total changes:</span>
        <span
          class="font-bold text-lg"
          :class="diff.total_changes > 0 ? 'text-orange-400' : 'text-green-400'"
        >{{ diff.total_changes }}</span>
        <span class="text-gray-600 text-xs ml-auto">
          {{ formatDate(diff.computed_at) }}
        </span>
      </div>

      <!-- Devices Added -->
      <section v-if="diff.devices_added.length > 0">
        <h3 class="text-xs font-semibold text-green-400 uppercase tracking-wider mb-2 flex items-center gap-1.5">
          <span class="w-2 h-2 rounded-full bg-green-400 inline-block"></span>
          Devices Added ({{ diff.devices_added.length }})
        </h3>
        <ul class="space-y-1">
          <li
            v-for="id in diff.devices_added"
            :key="id"
            class="flex items-center gap-2 px-3 py-2 rounded bg-green-900/20 border border-green-800/40 text-sm text-green-300 font-mono"
          >
            + {{ id }}
          </li>
        </ul>
      </section>

      <!-- Devices Removed -->
      <section v-if="diff.devices_removed.length > 0">
        <h3 class="text-xs font-semibold text-red-400 uppercase tracking-wider mb-2 flex items-center gap-1.5">
          <span class="w-2 h-2 rounded-full bg-red-400 inline-block"></span>
          Devices Removed ({{ diff.devices_removed.length }})
        </h3>
        <ul class="space-y-1">
          <li
            v-for="id in diff.devices_removed"
            :key="id"
            class="flex items-center gap-2 px-3 py-2 rounded bg-red-900/20 border border-red-800/40 text-sm text-red-300 font-mono"
          >
            − {{ id }}
          </li>
        </ul>
      </section>

      <!-- Devices Changed -->
      <section v-if="diff.devices_changed.length > 0">
        <h3 class="text-xs font-semibold text-orange-400 uppercase tracking-wider mb-2 flex items-center gap-1.5">
          <span class="w-2 h-2 rounded-full bg-orange-400 inline-block"></span>
          Devices Changed ({{ diff.devices_changed.length }})
        </h3>
        <div
          v-for="dev in diff.devices_changed"
          :key="dev.device_id"
          class="mb-2 rounded border border-amber-800/40 bg-amber-900/10"
        >
          <div class="px-3 py-2 text-sm text-amber-300 font-medium border-b border-amber-800/30">
            {{ dev.hostname || dev.device_id }}
          </div>
          <table class="w-full text-xs">
            <tbody>
              <tr
                v-for="chg in dev.changes"
                :key="chg.field"
                class="border-b border-gray-800 last:border-0"
              >
                <td class="px-3 py-1.5 text-gray-400 w-28 shrink-0 font-mono">{{ chg.field }}</td>
                <td class="px-2 py-1.5 text-red-400 font-mono line-through">{{ chg.before ?? '—' }}</td>
                <td class="px-1 py-1.5 text-gray-600">→</td>
                <td class="px-2 py-1.5 text-green-400 font-mono">{{ chg.after ?? '—' }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <!-- Links Added -->
      <section v-if="diff.links_added.length > 0">
        <h3 class="text-xs font-semibold text-green-400 uppercase tracking-wider mb-2 flex items-center gap-1.5">
          <span class="w-2 h-2 rounded-full bg-green-400 inline-block"></span>
          Links Added ({{ diff.links_added.length }})
        </h3>
        <ul class="space-y-1">
          <li
            v-for="(lnk, i) in diff.links_added"
            :key="i"
            class="px-3 py-2 rounded bg-green-900/20 border border-green-800/40 text-xs text-green-300 font-mono"
          >
            + {{ lnk.source }}:{{ lnk.source_intf }} ↔ {{ lnk.target }}{{ lnk.target_intf ? ':' + lnk.target_intf : '' }}
          </li>
        </ul>
      </section>

      <!-- Links Removed -->
      <section v-if="diff.links_removed.length > 0">
        <h3 class="text-xs font-semibold text-red-400 uppercase tracking-wider mb-2 flex items-center gap-1.5">
          <span class="w-2 h-2 rounded-full bg-red-400 inline-block"></span>
          Links Removed ({{ diff.links_removed.length }})
        </h3>
        <ul class="space-y-1">
          <li
            v-for="(lnk, i) in diff.links_removed"
            :key="i"
            class="px-3 py-2 rounded bg-red-900/20 border border-red-800/40 text-xs text-red-300 font-mono"
          >
            − {{ lnk.source }}:{{ lnk.source_intf }} ↔ {{ lnk.target }}{{ lnk.target_intf ? ':' + lnk.target_intf : '' }}
          </li>
        </ul>
      </section>

      <!-- No changes -->
      <div
        v-if="diff.total_changes === 0"
        class="flex flex-col items-center justify-center py-10 text-gray-600 text-sm"
      >
        <span class="text-2xl mb-2">✓</span>
        No changes detected between snapshots
      </div>

    </div>
  </div>
</template>

<script setup>
import { ref, watch, onMounted } from 'vue'
import { getDiff } from '../api.js'

const props = defineProps({
  currentId: { type: String, required: true },
  previousId: { type: String, required: true },
})

defineEmits(['close'])

const diff = ref(null)
const loading = ref(false)
const error = ref(null)

function formatDate(iso) {
  if (!iso) return ''
  return new Date(iso).toLocaleString()
}

async function fetchDiff() {
  loading.value = true
  error.value = null
  diff.value = null
  try {
    diff.value = await getDiff(props.currentId, props.previousId)
  } catch (e) {
    error.value = e.message || 'Failed to load diff'
  } finally {
    loading.value = false
  }
}

onMounted(fetchDiff)
watch(() => [props.currentId, props.previousId], fetchDiff)
</script>
