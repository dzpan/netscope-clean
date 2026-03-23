<template>
  <div class="flex items-center gap-2 mb-2">
    <div class="relative flex-1">
      <input
        v-model="model"
        type="text"
        :placeholder="`Filter ${label}…`"
        :aria-label="`Filter ${label}`"
        class="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1 text-xs text-gray-200 placeholder-gray-600 focus:border-orange-500 focus:ring-1 focus:ring-orange-500 outline-none"
      />
      <button
        v-if="model"
        class="absolute right-1.5 top-1/2 -translate-y-1/2 text-gray-500 hover:text-gray-300 text-xs"
        @click="model = ''"
        aria-label="Clear filter"
      >✕</button>
    </div>
    <button
      class="btn-ghost px-1.5 py-1 text-xs text-gray-500 hover:text-gray-200 shrink-0"
      title="Copy table to clipboard"
      @click="$emit('copy')"
    >
      {{ copyStatus || '⧉ Copy' }}
    </button>
    <button
      class="btn-ghost px-1.5 py-1 text-xs text-gray-500 hover:text-gray-200 shrink-0"
      title="Export as CSV"
      @click="$emit('export')"
    >
      ↓ CSV
    </button>
    <span v-if="count != null" class="text-[10px] text-gray-600 shrink-0">{{ count }} rows</span>
  </div>
</template>

<script setup>
const model = defineModel({ type: String, default: '' })
defineProps({
  label: { type: String, required: true },
  copyStatus: { type: String, default: '' },
  count: { type: Number, default: null },
})
defineEmits(['copy', 'export'])
</script>
