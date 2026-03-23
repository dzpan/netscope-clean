<template>
  <div class="flex rounded-md overflow-hidden border border-gray-700 text-xs font-mono uppercase tracking-wider" role="radiogroup" aria-label="Protocol filter">
    <button
      v-for="opt in options"
      :key="opt.value"
      role="radio"
      :aria-checked="modelValue === opt.value"
      class="px-3 py-1.5 transition-colors font-medium focus-visible:ring-2 focus-visible:ring-orange-500 focus-visible:outline-none"
      :class="modelValue === opt.value
        ? 'bg-orange-500 text-gray-950'
        : 'bg-gray-800 text-gray-400 hover:text-gray-200 hover:bg-gray-700'"
      @click="$emit('update:modelValue', opt.value)"
    >
      {{ opt.label }}
    </button>
  </div>
</template>

<script setup>
defineProps({
  modelValue: { type: String, default: 'all' },
})
defineEmits(['update:modelValue'])

const options = [
  { label: 'All', value: 'all' },
  { label: 'CDP only', value: 'cdp' },
  { label: 'LLDP only', value: 'lldp' },
]
</script>
