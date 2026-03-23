<template>
  <Teleport to="body">
    <Transition name="fade">
      <div v-if="show" class="fixed inset-0 z-50 flex items-center justify-center" role="dialog" aria-modal="true" aria-label="Playbook editor">
        <div class="absolute inset-0 bg-black/60 backdrop-blur-sm" @click="$emit('close')" />
        <div class="relative bg-gray-900 border border-gray-700 rounded-lg shadow-xl w-full max-w-2xl mx-4 overflow-hidden max-h-[90vh] flex flex-col">

          <!-- Header -->
          <div class="px-5 pt-5 pb-3 border-b border-gray-700/50 shrink-0">
            <h3 class="text-base font-semibold text-gray-100 font-display">
              {{ isEditing ? 'Edit Playbook' : 'Create Playbook' }}
            </h3>
            <p class="text-xs text-gray-500 mt-0.5">Define a reusable configuration sequence</p>
          </div>

          <!-- Tabs -->
          <div class="flex items-center gap-0 border-b border-gray-700/50 shrink-0 px-5">
            <button
              v-for="tab in tabs"
              :key="tab.id"
              class="px-3 py-2 text-xs font-medium transition-colors border-b-2 -mb-px"
              :class="activeTab === tab.id
                ? 'text-orange-400 border-orange-500'
                : 'text-gray-500 border-transparent hover:text-gray-300'"
              @click="activeTab = tab.id"
            >{{ tab.label }}</button>
          </div>

          <!-- Body -->
          <div class="px-5 py-4 overflow-y-auto flex-1">

            <!-- General tab -->
            <div v-if="activeTab === 'general'" class="flex flex-col gap-4">
              <div>
                <label class="label">Title</label>
                <input v-model="form.title" type="text" class="input" placeholder="e.g. Configure Access Port" />
              </div>
              <div>
                <label class="label">Description</label>
                <textarea v-model="form.description" class="input" rows="2" placeholder="What this playbook does…" />
              </div>
              <div class="grid grid-cols-2 gap-3">
                <div>
                  <label class="label">Category</label>
                  <select v-model="form.category" class="select">
                    <option value="">Select category</option>
                    <option value="vlan">VLAN</option>
                    <option value="security">Security</option>
                    <option value="qos">QoS</option>
                    <option value="access-control">Access Control</option>
                    <option value="monitoring">Monitoring</option>
                    <option value="system">System</option>
                    <option value="other">Other</option>
                  </select>
                </div>
                <div>
                  <label class="label">Platform</label>
                  <div class="flex items-center gap-3 mt-1">
                    <label v-for="plat in ['iosxe', 'nxos', 'cbs']" :key="plat" class="flex items-center gap-1.5 text-xs text-gray-300 cursor-pointer">
                      <input
                        type="checkbox"
                        :checked="form.platform.includes(plat)"
                        class="accent-orange-500"
                        @change="togglePlatform(plat)"
                      />
                      {{ plat }}
                    </label>
                  </div>
                </div>
              </div>
            </div>

            <!-- Variables tab -->
            <div v-if="activeTab === 'variables'" class="flex flex-col gap-3">
              <p class="text-xs text-gray-500">Define variables that will be filled at execution time. Use <code class="font-mono text-orange-400" v-pre>{{name}}</code> in commands.</p>
              <div
                v-for="(v, idx) in form.variables"
                :key="idx"
                class="border border-gray-700 rounded p-3 bg-gray-800/30"
              >
                <div class="flex items-start gap-2">
                  <div class="flex-1 grid grid-cols-3 gap-2">
                    <div>
                      <label class="label text-xs">Name</label>
                      <input v-model="v.name" type="text" class="input input-sm font-mono" placeholder="vlan_id" />
                    </div>
                    <div>
                      <label class="label text-xs">Type</label>
                      <select v-model="v.type" class="select text-xs py-1">
                        <option value="string">String</option>
                        <option value="int">Integer</option>
                        <option value="choice">Choice</option>
                        <option value="interface">Interface</option>
                      </select>
                    </div>
                    <div>
                      <label class="label text-xs">Default</label>
                      <input v-model="v.default" type="text" class="input input-sm" placeholder="optional" />
                    </div>
                  </div>
                  <button
                    class="btn-ghost p-1 text-gray-500 hover:text-red-400 mt-4"
                    @click="form.variables.splice(idx, 1)"
                  >&#x2715;</button>
                </div>
                <div class="grid grid-cols-2 gap-2 mt-2">
                  <div>
                    <label class="label text-xs">Description</label>
                    <input v-model="v.description" type="text" class="input input-sm" placeholder="Human-readable label" />
                  </div>
                  <div class="flex items-end gap-3">
                    <label class="flex items-center gap-1.5 text-xs text-gray-300 cursor-pointer">
                      <input v-model="v.required" type="checkbox" class="accent-orange-500" />
                      Required
                    </label>
                    <div v-if="v.type === 'choice'" class="flex-1">
                      <label class="label text-xs">Choices (comma-separated)</label>
                      <input v-model="v.choices_str" type="text" class="input input-sm" placeholder="10,20,30" />
                    </div>
                  </div>
                </div>
              </div>
              <button
                class="btn-secondary btn-sm text-xs self-start"
                @click="addVariable"
              >+ Add Variable</button>
            </div>

            <!-- Commands tab -->
            <div v-if="activeTab === 'commands'" class="flex flex-col gap-4">
              <div>
                <label class="label">Configuration Steps</label>
                <p class="text-xs text-gray-500 mb-2">One command per line. Use <code class="font-mono text-orange-400" v-pre>{{var}}</code> for variable substitution.</p>
                <textarea
                  v-model="form.steps_text"
                  class="w-full bg-gray-950 border border-gray-700 rounded p-3 text-xs font-mono text-orange-300 focus:outline-none focus:border-orange-500 focus:ring-1 focus:ring-orange-500"
                  rows="8"
                  placeholder="interface {{interface}}
switchport mode access
switchport access vlan {{vlan_id}}
no shutdown"
                  spellcheck="false"
                />
              </div>
              <div>
                <label class="label">Pre-Check Commands</label>
                <p class="text-xs text-gray-500 mb-2">Show commands to capture state before applying.</p>
                <textarea
                  v-model="form.pre_checks_text"
                  class="w-full bg-gray-950 border border-gray-700 rounded p-3 text-xs font-mono text-green-300 focus:outline-none focus:border-orange-500 focus:ring-1 focus:ring-orange-500"
                  rows="3"
                  placeholder="show running-config interface {{interface}}
show interfaces {{interface}} status"
                  spellcheck="false"
                />
              </div>
              <div>
                <label class="label">Post-Check Commands</label>
                <p class="text-xs text-gray-500 mb-2">Show commands to verify success after applying.</p>
                <textarea
                  v-model="form.post_checks_text"
                  class="w-full bg-gray-950 border border-gray-700 rounded p-3 text-xs font-mono text-green-300 focus:outline-none focus:border-orange-500 focus:ring-1 focus:ring-orange-500"
                  rows="3"
                  placeholder="show interfaces {{interface}} status
show running-config interface {{interface}}"
                  spellcheck="false"
                />
              </div>
              <div>
                <label class="label">Rollback Commands</label>
                <p class="text-xs text-gray-500 mb-2">Undo sequence. Use "auto" for automatic rollback from pre-state.</p>
                <textarea
                  v-model="form.rollback_text"
                  class="w-full bg-gray-950 border border-gray-700 rounded p-3 text-xs font-mono text-red-300 focus:outline-none focus:border-orange-500 focus:ring-1 focus:ring-orange-500"
                  rows="3"
                  placeholder="auto"
                  spellcheck="false"
                />
              </div>
            </div>

            <!-- YAML tab -->
            <div v-if="activeTab === 'yaml'" class="flex flex-col gap-3">
              <p class="text-xs text-gray-500">Edit playbook as YAML or paste an imported playbook definition.</p>
              <textarea
                v-model="yamlText"
                class="w-full bg-gray-950 border border-gray-700 rounded p-3 text-xs font-mono text-gray-300 focus:outline-none focus:border-orange-500 focus:ring-1 focus:ring-orange-500"
                rows="20"
                spellcheck="false"
                placeholder="name: Configure Access Port
description: Set interface to access mode
platform: [iosxe]
category: vlan
variables:
  - name: interface
    type: interface
    required: true
steps:
  - interface {{interface}}
  - switchport mode access"
              />
              <div v-if="yamlError" class="bg-red-900/40 border border-red-700/50 rounded px-3 py-2 text-xs text-red-300">
                {{ yamlError }}
              </div>
              <div class="flex items-center gap-2">
                <button class="btn-secondary btn-sm text-xs" @click="applyYaml">Apply YAML to form</button>
                <button class="btn-secondary btn-sm text-xs" @click="generateYaml">Generate YAML from form</button>
              </div>
            </div>
          </div>

          <!-- Footer -->
          <div class="flex items-center justify-between px-5 py-4 border-t border-gray-700/50 shrink-0">
            <div>
              <button
                v-if="isEditing"
                class="btn-ghost text-xs text-red-400 hover:text-red-300 px-3 py-1.5"
                @click="$emit('delete', playbook)"
              >Delete</button>
            </div>
            <div class="flex items-center gap-2">
              <button class="btn-ghost px-3 py-1.5 text-sm" @click="$emit('close')">Cancel</button>
              <button
                class="btn-primary px-4 py-1.5 text-sm font-medium"
                :disabled="!form.title || !form.steps_text.trim()"
                @click="handleSave"
              >{{ isEditing ? 'Save Changes' : 'Create Playbook' }}</button>
            </div>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup>
import { ref, computed, watch } from 'vue'

const props = defineProps({
  show: { type: Boolean, default: false },
  playbook: { type: Object, default: null },
})

const emit = defineEmits(['close', 'save', 'delete'])

const isEditing = computed(() => !!props.playbook?.id)

const tabs = [
  { id: 'general', label: 'General' },
  { id: 'variables', label: 'Variables' },
  { id: 'commands', label: 'Commands' },
  { id: 'yaml', label: 'YAML' },
]
const activeTab = ref('general')

const form = ref(emptyForm())
const yamlText = ref('')
const yamlError = ref('')

function emptyForm() {
  return {
    title: '',
    description: '',
    category: '',
    platform: [],
    variables: [],
    steps_text: '',
    pre_checks_text: '',
    post_checks_text: '',
    rollback_text: 'auto',
  }
}

function loadPlaybook(pb) {
  if (!pb) {
    form.value = emptyForm()
    activeTab.value = 'general'
    return
  }
  form.value = {
    title: pb.title || '',
    description: pb.description || '',
    category: pb.category || '',
    platform: [...(pb.platform || [])],
    variables: (pb.variables || []).map(v => ({
      ...v,
      choices_str: (v.choices || []).join(', '),
    })),
    steps_text: (pb.steps || []).join('\n'),
    pre_checks_text: (pb.pre_checks || []).join('\n'),
    post_checks_text: (pb.post_checks || []).join('\n'),
    rollback_text: Array.isArray(pb.rollback) ? pb.rollback.join('\n') : (pb.rollback || 'auto'),
  }
}

watch(() => props.playbook, loadPlaybook, { immediate: true })
watch(() => props.show, (v) => { if (v) loadPlaybook(props.playbook) })
watch(yamlText, () => { yamlError.value = '' })

function togglePlatform(plat) {
  const idx = form.value.platform.indexOf(plat)
  if (idx >= 0) {
    form.value.platform.splice(idx, 1)
  } else {
    form.value.platform.push(plat)
  }
}

function addVariable() {
  form.value.variables.push({
    name: '',
    type: 'string',
    default: '',
    description: '',
    required: true,
    choices_str: '',
  })
}

function textToLines(text) {
  return text.split('\n').map(l => l.trim()).filter(Boolean)
}

function buildPayload() {
  const f = form.value
  return {
    title: f.title,
    description: f.description,
    category: f.category || null,
    platform: f.platform,
    variables: f.variables.map(v => ({
      name: v.name,
      type: v.type,
      default: v.default || null,
      description: v.description || null,
      required: v.required,
      choices: v.type === 'choice' ? (v.choices_str || '').split(',').map(s => s.trim()).filter(Boolean) : undefined,
    })),
    steps: textToLines(f.steps_text),
    pre_checks: textToLines(f.pre_checks_text),
    post_checks: textToLines(f.post_checks_text),
    rollback: f.rollback_text.trim() === 'auto' ? ['auto'] : textToLines(f.rollback_text),
  }
}

function handleSave() {
  emit('save', {
    id: props.playbook?.id || null,
    ...buildPayload(),
  })
}

function generateYaml() {
  const p = buildPayload()
  const lines = []
  lines.push(`name: ${p.title}`)
  if (p.description) lines.push(`description: ${p.description}`)
  if (p.platform.length) lines.push(`platform: [${p.platform.join(', ')}]`)
  if (p.category) lines.push(`category: ${p.category}`)
  if (p.variables.length) {
    lines.push('variables:')
    for (const v of p.variables) {
      lines.push(`  - name: ${v.name}`)
      lines.push(`    type: ${v.type}`)
      lines.push(`    required: ${v.required}`)
      if (v.description) lines.push(`    description: ${v.description}`)
      if (v.default) lines.push(`    default: "${v.default}"`)
      if (v.choices?.length) lines.push(`    choices: [${v.choices.join(', ')}]`)
    }
  }
  if (p.pre_checks.length) {
    lines.push('pre_checks:')
    for (const c of p.pre_checks) lines.push(`  - ${c}`)
  }
  lines.push('steps:')
  for (const s of p.steps) lines.push(`  - ${s}`)
  if (p.post_checks.length) {
    lines.push('post_checks:')
    for (const c of p.post_checks) lines.push(`  - ${c}`)
  }
  if (p.rollback.length) {
    lines.push('rollback:')
    for (const r of p.rollback) lines.push(`  - ${r}`)
  }
  yamlText.value = lines.join('\n')
}

function applyYaml() {
  // Simple YAML parser for playbook format — not full YAML
  yamlError.value = ''
  try {
    const text = yamlText.value
    if (!text.trim()) {
      yamlError.value = 'YAML content is empty'
      return
    }
    const getVal = (key) => {
      const m = text.match(new RegExp(`^${key}:\\s*(.+)$`, 'm'))
      return m ? m[1].trim() : ''
    }
    const getList = (key) => {
      const m = text.match(new RegExp(`^${key}:\\s*\\[([^\\]]+)\\]`, 'm'))
      if (m) return m[1].split(',').map(s => s.trim()).filter(Boolean)
      // Multi-line list
      const lines = []
      const regex = new RegExp(`^${key}:\\s*$`, 'm')
      const idx = text.search(regex)
      if (idx < 0) return []
      const after = text.slice(idx).split('\n').slice(1)
      for (const line of after) {
        const itemMatch = line.match(/^\s+-\s+(.+)$/)
        if (itemMatch) lines.push(itemMatch[1])
        else if (line.match(/^\S/)) break
      }
      return lines
    }

    const title = getVal('name')
    const steps = getList('steps')
    if (!title && !steps.length) {
      yamlError.value = 'Could not parse YAML: missing required "name" and "steps" fields'
      return
    }

    form.value.title = title || form.value.title
    form.value.description = getVal('description') || form.value.description
    form.value.category = getVal('category') || form.value.category
    form.value.platform = getList('platform')
    form.value.steps_text = steps.join('\n')
    form.value.pre_checks_text = getList('pre_checks').join('\n')
    form.value.post_checks_text = getList('post_checks').join('\n')
    form.value.rollback_text = getList('rollback').join('\n') || 'auto'

    // Warn about missing fields but keep partial data
    const warnings = []
    if (!title) warnings.push('"name"')
    if (!steps.length) warnings.push('"steps"')
    if (warnings.length) {
      yamlError.value = `Applied partial data — missing required field(s): ${warnings.join(' and ')}`
      return
    }

    activeTab.value = 'general'
  } catch (e) {
    yamlError.value = e.message || 'Failed to parse YAML content'
  }
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
