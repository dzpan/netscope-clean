<template>
  <div class="relative shrink-0" ref="dropdownRef">
    <button
      class="btn-secondary btn-sm flex items-center gap-1"
      :disabled="!sessionId"
      @click="open = !open"
      title="Export topology data"
      aria-haspopup="true"
      :aria-expanded="open"
    >
      <span class="text-xs">Export ▾</span>
    </button>
    <div
      v-if="open"
      class="absolute right-0 top-full mt-1 bg-gray-850 border border-gray-700 rounded shadow-lg z-50 min-w-[160px] py-1"
      role="menu"
    >
      <button
        v-for="item in formats"
        :key="item.format"
        class="block w-full text-left px-3 py-1.5 text-xs text-gray-300 hover:bg-gray-700 hover:text-gray-100 transition-colors"
        role="menuitem"
        @click="handleExport(item.format)"
      >
        {{ item.label }}
      </button>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount } from 'vue'
import { downloadExport } from '../api.js'

const props = defineProps({ sessionId: { type: String, default: null } })
const emit = defineEmits(['export-png'])

const open = ref(false)
const dropdownRef = ref(null)

const formats = [
  { format: 'drawio', label: 'DrawIO Diagram' },
  { format: 'excel', label: 'Excel Workbook' },
  { format: 'csv', label: 'CSV Archive' },
  { format: 'json', label: 'JSON Data' },
  { format: 'dot', label: 'Graphviz DOT' },
  { format: 'svg', label: 'SVG Diagram' },
  { format: 'png', label: 'PNG Screenshot' },
]

function handleExport(format) {
  open.value = false
  if (!props.sessionId) return
  if (format === 'png') {
    emit('export-png')
  } else {
    downloadExport(props.sessionId, format)
  }
}

function onClickOutside(e) {
  if (dropdownRef.value && !dropdownRef.value.contains(e.target)) {
    open.value = false
  }
}

onMounted(() => document.addEventListener('click', onClickOutside))
onBeforeUnmount(() => document.removeEventListener('click', onClickOutside))
</script>
