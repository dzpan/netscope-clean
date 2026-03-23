<template>
  <div class="flex flex-col h-full overflow-hidden">
    <!-- Header -->
    <div class="panel-header">
      <div class="flex items-center gap-2">
        <svg class="w-4 h-4 text-orange-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
            d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" />
        </svg>
        <h3 class="panel-title">Alerts &amp; Notifications</h3>
        <span v-if="unackedCount > 0"
          class="text-xs px-1.5 py-0.5 rounded-full bg-orange-900/40 text-orange-400 font-medium"
        >{{ unackedCount }}</span>
      </div>
      <button class="btn-ghost p-1" @click="$emit('close')" title="Close">
        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
        </svg>
      </button>
    </div>

    <!-- Tab bar -->
    <div class="tab-bar">
      <button
        v-for="tab in tabs"
        :key="tab.key"
        class="tab-item"
        :class="{ active: activeTab === tab.key }"
        @click="activeTab = tab.key"
      >
        {{ tab.label }}
      </button>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="flex-1 flex items-center justify-center">
      <svg class="animate-spin h-5 w-5 text-orange-500" viewBox="0 0 24 24" fill="none">
        <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"/>
        <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z"/>
      </svg>
    </div>

    <!-- Error -->
    <div v-else-if="error" class="m-4 px-3 py-2 rounded bg-red-900/30 border border-red-800 text-red-300 text-xs">
      {{ error }}
      <button class="ml-2 text-red-500 hover:text-red-300 underline" @click="error = null">dismiss</button>
    </div>

    <!-- ================================================================
         HISTORY TAB — alert log with filtering
         ================================================================ -->
    <div v-if="!loading && activeTab === 'history'" class="flex-1 overflow-y-auto flex flex-col">
      <!-- Filters -->
      <div class="flex items-center gap-2 px-4 py-2 border-b border-gray-800 shrink-0 flex-wrap">
        <select v-model="historyFilter.severity" class="input text-xs py-1 w-auto">
          <option value="">All severities</option>
          <option value="info">Info</option>
          <option value="warning">Warning</option>
          <option value="critical">Critical</option>
        </select>
        <select v-model="historyFilter.trigger" class="input text-xs py-1 w-auto">
          <option value="">All triggers</option>
          <option v-for="t in triggerOptions" :key="t.value" :value="t.value">{{ t.label }}</option>
        </select>
        <select v-model="historyFilter.acked" class="input text-xs py-1 w-auto">
          <option value="">All</option>
          <option value="unacked">Unacknowledged</option>
          <option value="acked">Acknowledged</option>
        </select>
        <span class="text-xs text-gray-600 ml-auto">{{ filteredAlerts.length }} alert{{ filteredAlerts.length !== 1 ? 's' : '' }}</span>
      </div>

      <!-- Alert list -->
      <div class="flex-1 overflow-y-auto">
        <div v-if="filteredAlerts.length === 0" class="flex flex-col items-center justify-center py-12 text-gray-600 text-sm gap-2">
          <svg class="w-8 h-8 text-gray-700" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          <p>No alerts match filters</p>
        </div>
        <div
          v-for="alert in filteredAlerts"
          :key="alert.alert_id"
          class="flex items-start gap-3 px-4 py-3 border-b border-gray-800/50 transition-colors"
          :class="alert.acknowledged_at ? 'opacity-50' : 'hover:bg-gray-800/30'"
        >
          <!-- Severity dot -->
          <div
            class="shrink-0 w-2 h-2 rounded-full mt-1.5"
            :class="severityDot(alert.severity)"
            :title="alert.severity"
          ></div>

          <!-- Content -->
          <div class="flex-1 min-w-0">
            <div class="flex items-center gap-2 flex-wrap">
              <span
                class="text-xs font-mono px-1.5 py-0.5 rounded"
                :class="triggerBadge(alert.trigger)"
              >{{ formatTrigger(alert.trigger) }}</span>
              <span class="text-xs text-gray-500">{{ alert.rule_name }}</span>
              <span
                class="text-xs px-1.5 py-0.5 rounded"
                :class="severityBadge(alert.severity)"
              >{{ alert.severity }}</span>
            </div>
            <p class="text-xs text-gray-300 mt-1 leading-relaxed">{{ alert.detail }}</p>
            <div class="flex items-center gap-3 mt-1.5 text-xs text-gray-600">
              <span class="font-mono">{{ formatDate(alert.triggered_at) }}</span>
              <span v-if="alert.acknowledged_at" class="text-green-600/80 flex items-center gap-1">
                <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" /></svg>
                acked {{ formatDate(alert.acknowledged_at) }}
              </span>
              <span class="font-mono text-gray-700" title="Session">{{ alert.current_session_id?.slice(0, 8) }}</span>
            </div>
          </div>

          <!-- Ack / Unack button -->
          <button
            v-if="!alert.acknowledged_at"
            class="shrink-0 text-xs px-2 py-1 rounded text-gray-500 hover:text-orange-400 hover:bg-orange-900/20 transition-colors"
            title="Acknowledge"
            @click="handleAck(alert.alert_id, true)"
          >
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" /></svg>
          </button>
          <button
            v-else
            class="shrink-0 text-xs px-2 py-1 rounded text-gray-600 hover:text-gray-400 hover:bg-gray-800/40 transition-colors"
            title="Un-acknowledge"
            @click="handleAck(alert.alert_id, false)"
          >
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" /></svg>
          </button>
        </div>
      </div>
    </div>

    <!-- ================================================================
         RULES TAB — create / edit / delete alert rules
         ================================================================ -->
    <div v-if="!loading && activeTab === 'rules'" class="flex-1 overflow-y-auto flex flex-col">
      <!-- Add / Edit rule form -->
      <div class="p-4 border-b border-gray-700 shrink-0">
        <p class="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-3">
          {{ editingRule ? 'Edit Rule' : 'New Rule' }}
        </p>
        <div class="flex flex-col gap-2">
          <input
            v-model="ruleForm.name"
            class="input text-xs py-1"
            placeholder="Rule name (e.g. Device removed)"
            aria-label="Alert rule name"
          />
          <div class="flex flex-wrap gap-1.5">
            <label
              v-for="t in triggerOptions"
              :key="t.value"
              class="flex items-center gap-1 text-xs cursor-pointer px-2 py-0.5 rounded border transition-colors"
              :class="ruleForm.triggers.includes(t.value)
                ? 'border-orange-500 bg-orange-900/30 text-orange-300'
                : 'border-gray-700 text-gray-500 hover:border-gray-500'"
            >
              <input
                type="checkbox"
                class="hidden"
                :value="t.value"
                v-model="ruleForm.triggers"
              />
              {{ t.label }}
            </label>
          </div>
          <div class="flex items-center gap-2">
            <select v-model="ruleForm.severity" class="input text-xs py-1 flex-1" aria-label="Alert severity">
              <option value="info">Info</option>
              <option value="warning">Warning</option>
              <option value="critical">Critical</option>
            </select>
          </div>
          <input
            v-model="ruleForm.webhook_url"
            class="input text-xs py-1 font-mono"
            placeholder="Webhook URL (optional)"
            aria-label="Webhook URL"
          />
          <div class="flex items-center gap-2 mt-1">
            <button
              class="btn-primary text-xs py-1.5 flex-1"
              :disabled="!ruleForm.name.trim() || ruleForm.triggers.length === 0 || saving"
              @click="saveRule"
            >
              {{ saving ? 'Saving…' : editingRule ? 'Update Rule' : '+ Create Rule' }}
            </button>
            <button
              v-if="editingRule"
              class="btn-secondary text-xs py-1.5"
              @click="cancelEdit"
            >Cancel</button>
          </div>
        </div>
      </div>

      <!-- Rule list -->
      <div class="flex-1 overflow-y-auto">
        <div v-if="rules.length === 0" class="flex flex-col items-center justify-center py-12 text-gray-600 text-sm gap-2">
          <svg class="w-8 h-8 text-gray-700" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5"
              d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
          </svg>
          <p>No rules configured</p>
          <p class="text-xs text-gray-700">Create a rule above to start receiving alerts</p>
        </div>
        <div
          v-for="rule in rules"
          :key="rule.rule_id"
          class="flex items-start gap-3 px-4 py-3 border-b border-gray-800/50 group hover:bg-gray-800/20 transition-colors"
          :class="editingRule === rule.rule_id ? 'bg-orange-900/10 border-l-2 border-l-orange-500' : ''"
        >
          <div class="flex-1 min-w-0">
            <div class="flex items-center gap-2">
              <span class="text-sm text-gray-200 font-medium">{{ rule.name }}</span>
              <span
                class="text-xs px-1.5 py-0.5 rounded"
                :class="severityBadge(rule.severity)"
              >{{ rule.severity }}</span>
            </div>
            <div class="flex flex-wrap gap-1 mt-1">
              <span
                v-for="t in rule.triggers"
                :key="t"
                class="text-xs font-mono px-1.5 py-0.5 rounded"
                :class="triggerBadge(t)"
              >{{ formatTrigger(t) }}</span>
            </div>
            <p v-if="rule.webhook_url" class="text-xs text-gray-600 font-mono mt-1 truncate">{{ rule.webhook_url }}</p>
            <p class="text-xs text-gray-700 mt-1">Created {{ formatDate(rule.created_at) }}</p>
          </div>
          <div class="shrink-0 flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
            <button
              class="text-xs text-gray-600 hover:text-orange-400 transition-colors p-1"
              title="Edit rule"
              @click="startEdit(rule)"
            >
              <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                  d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
              </svg>
            </button>
            <button
              class="text-xs text-gray-600 hover:text-red-400 transition-colors p-1"
              title="Delete rule"
              @click="deleteRule(rule.rule_id)"
            >
              <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                  d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
              </svg>
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- ================================================================
         WEBHOOKS TAB — manage and test webhook endpoints
         ================================================================ -->
    <div v-if="!loading && activeTab === 'webhooks'" class="flex-1 overflow-y-auto flex flex-col">
      <!-- Test webhook -->
      <div class="p-4 border-b border-gray-700 shrink-0">
        <p class="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-3">Test Webhook</p>
        <div class="flex flex-col gap-2">
          <input
            v-model="webhookTest.url"
            class="input text-xs py-1 font-mono"
            placeholder="https://example.com/webhook"
            aria-label="Test webhook URL"
          />
          <input
            v-model="webhookTest.secret"
            class="input text-xs py-1 font-mono"
            placeholder="Shared secret (optional)"
            type="password"
            aria-label="Webhook shared secret"
          />
          <button
            class="btn-primary text-xs py-1.5"
            :disabled="!webhookTest.url.trim() || webhookTesting"
            @click="sendTestWebhook"
          >
            {{ webhookTesting ? 'Sending…' : 'Send Test Payload' }}
          </button>
        </div>
        <!-- Test result -->
        <div v-if="webhookTestResult" class="mt-3 p-2 rounded text-xs border"
          :class="webhookTestResult.success
            ? 'bg-green-900/20 border-green-800 text-green-300'
            : 'bg-red-900/20 border-red-800 text-red-300'"
        >
          <p class="font-medium">{{ webhookTestResult.success ? 'Delivered successfully' : 'Delivery failed' }}</p>
          <p v-if="webhookTestResult.status_code" class="text-gray-400 mt-1">
            Status: <span class="font-mono">{{ webhookTestResult.status_code }}</span>
          </p>
          <p v-if="webhookTestResult.error" class="mt-1">{{ webhookTestResult.error }}</p>
          <p v-if="webhookTestResult.body" class="mt-1 font-mono text-gray-500 truncate" :title="webhookTestResult.body">
            {{ webhookTestResult.body }}
          </p>
        </div>
      </div>

      <!-- Webhooks from rules -->
      <div class="flex-1 overflow-y-auto">
        <div class="px-4 py-2 border-b border-gray-800 shrink-0">
          <p class="text-xs text-gray-500">
            Webhook endpoints are configured per rule. Rules with webhook URLs are listed below.
          </p>
        </div>
        <div v-if="rulesWithWebhooks.length === 0" class="flex flex-col items-center justify-center py-12 text-gray-600 text-sm gap-2">
          <svg class="w-8 h-8 text-gray-700" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5"
              d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1" />
          </svg>
          <p>No webhook endpoints configured</p>
          <p class="text-xs text-gray-700">Add a webhook URL to a rule in the Rules tab</p>
        </div>
        <div
          v-for="rule in rulesWithWebhooks"
          :key="rule.rule_id"
          class="flex items-start gap-3 px-4 py-3 border-b border-gray-800/50"
        >
          <div class="shrink-0 w-2 h-2 rounded-full mt-1.5 bg-green-500" title="Active webhook"></div>
          <div class="flex-1 min-w-0">
            <p class="text-sm text-gray-200 font-medium">{{ rule.name }}</p>
            <p class="text-xs text-gray-400 font-mono mt-1 truncate">{{ rule.webhook_url }}</p>
            <div class="flex flex-wrap gap-1 mt-1.5">
              <span
                v-for="t in rule.triggers"
                :key="t"
                class="text-xs font-mono px-1.5 py-0.5 rounded"
                :class="triggerBadge(t)"
              >{{ formatTrigger(t) }}</span>
            </div>
          </div>
          <button
            class="shrink-0 text-xs px-2 py-1 rounded text-gray-600 hover:text-orange-400 hover:bg-orange-900/20 transition-colors"
            title="Test this webhook"
            @click="webhookTest.url = rule.webhook_url; sendTestWebhook()"
          >
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                d="M13 10V3L4 14h7v7l9-11h-7z" />
            </svg>
          </button>
        </div>
      </div>
    </div>

    <!-- ================================================================
         PREFERENCES TAB — notification settings
         ================================================================ -->
    <div v-if="!loading && activeTab === 'preferences'" class="flex-1 overflow-y-auto">
      <div class="p-4 flex flex-col gap-5">
        <p class="text-xs text-gray-500">Configure which events generate notifications and how they are delivered.</p>

        <!-- Event toggles -->
        <div>
          <p class="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-3">Event Notifications</p>
          <div class="flex flex-col gap-2">
            <label
              v-for="t in triggerOptions"
              :key="t.value"
              class="flex items-center justify-between px-3 py-2 rounded border transition-colors cursor-pointer"
              :class="preferences.enabledTriggers.includes(t.value)
                ? 'border-orange-500/40 bg-orange-900/10'
                : 'border-gray-700 hover:border-gray-600'"
            >
              <div class="flex items-center gap-2">
                <span
                  class="text-xs font-mono px-1.5 py-0.5 rounded"
                  :class="triggerBadge(t.value)"
                >{{ formatTrigger(t.value) }}</span>
                <span class="text-xs text-gray-300">{{ t.label }}</span>
              </div>
              <input
                type="checkbox"
                class="accent-orange-500"
                :value="t.value"
                v-model="preferences.enabledTriggers"
              />
            </label>
          </div>
        </div>

        <!-- Severity threshold -->
        <div>
          <p class="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">Minimum Severity</p>
          <p class="text-xs text-gray-600 mb-2">Only notify for alerts at or above this severity level.</p>
          <div class="flex gap-2">
            <button
              v-for="sev in ['info', 'warning', 'critical']"
              :key="sev"
              class="flex-1 text-xs py-2 rounded border transition-colors capitalize"
              :class="preferences.minSeverity === sev
                ? severityButtonActive(sev)
                : 'border-gray-700 text-gray-500 hover:border-gray-600'"
              @click="preferences.minSeverity = sev"
            >{{ sev }}</button>
          </div>
        </div>

        <!-- Delivery channels -->
        <div>
          <p class="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">Delivery Channels</p>
          <div class="flex flex-col gap-2">
            <label
              v-for="ch in channels"
              :key="ch.value"
              class="flex items-center justify-between px-3 py-2 rounded border transition-colors"
              :class="preferences.channels.includes(ch.value)
                ? 'border-orange-500/40 bg-orange-900/10'
                : 'border-gray-700'"
            >
              <div class="flex items-center gap-2">
                <span class="text-gray-400" v-html="ch.icon"></span>
                <span class="text-xs text-gray-300">{{ ch.label }}</span>
                <span v-if="ch.note" class="text-xs text-gray-600">{{ ch.note }}</span>
              </div>
              <input
                type="checkbox"
                class="accent-orange-500"
                :value="ch.value"
                v-model="preferences.channels"
              />
            </label>
          </div>
        </div>

        <!-- Save preferences -->
        <div class="flex items-center gap-2">
          <button
            class="btn-primary text-xs py-1.5 flex-1"
            :disabled="savingPrefs"
            @click="savePreferences"
          >
            {{ savingPrefs ? 'Saving…' : 'Save Preferences' }}
          </button>
          <span v-if="prefsSaved" class="text-xs text-green-500 transition-opacity">Saved</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import {
  listAlerts,
  ackAlert as apiAckAlert,
  listAlertRules,
  createAlertRule,
  updateAlertRule,
  deleteAlertRule as apiDeleteAlertRule,
  testWebhook as apiTestWebhook,
  getSettings,
  updateSettings,
} from '../api.js'

defineEmits(['close'])

// ---------------------------------------------------------------------------
// Tabs
// ---------------------------------------------------------------------------
const tabs = [
  { key: 'history', label: 'History' },
  { key: 'rules', label: 'Rules' },
  { key: 'webhooks', label: 'Webhooks' },
  { key: 'preferences', label: 'Preferences' },
]
const activeTab = ref('history')

// ---------------------------------------------------------------------------
// Core state
// ---------------------------------------------------------------------------
const alerts = ref([])
const rules = ref([])
const loading = ref(false)
const error = ref(null)
const saving = ref(false)

// ---------------------------------------------------------------------------
// Trigger options
// ---------------------------------------------------------------------------
const triggerOptions = [
  { value: 'device_added', label: 'Device added' },
  { value: 'device_removed', label: 'Device removed' },
  { value: 'link_added', label: 'Link added' },
  { value: 'link_removed', label: 'Link removed' },
  { value: 'device_status_change', label: 'Status change' },
]

// ---------------------------------------------------------------------------
// History tab — filtering
// ---------------------------------------------------------------------------
const historyFilter = ref({
  severity: '',
  trigger: '',
  acked: '',
})

const unackedCount = computed(() => alerts.value.filter((a) => !a.acknowledged_at).length)

const filteredAlerts = computed(() => {
  let result = alerts.value
  if (historyFilter.value.severity) {
    result = result.filter((a) => a.severity === historyFilter.value.severity)
  }
  if (historyFilter.value.trigger) {
    result = result.filter((a) => a.trigger === historyFilter.value.trigger)
  }
  if (historyFilter.value.acked === 'acked') {
    result = result.filter((a) => a.acknowledged_at)
  } else if (historyFilter.value.acked === 'unacked') {
    result = result.filter((a) => !a.acknowledged_at)
  }
  return result
})

// ---------------------------------------------------------------------------
// Rules tab — create / edit
// ---------------------------------------------------------------------------
const editingRule = ref(null) // rule_id or null
const emptyRuleForm = () => ({ name: '', triggers: [], severity: 'warning', webhook_url: '' })
const ruleForm = ref(emptyRuleForm())

function startEdit(rule) {
  editingRule.value = rule.rule_id
  ruleForm.value = {
    name: rule.name,
    triggers: [...rule.triggers],
    severity: rule.severity,
    webhook_url: rule.webhook_url || '',
  }
}

function cancelEdit() {
  editingRule.value = null
  ruleForm.value = emptyRuleForm()
}

async function saveRule() {
  if (!ruleForm.value.name.trim() || ruleForm.value.triggers.length === 0) return
  saving.value = true
  try {
    const payload = {
      name: ruleForm.value.name.trim(),
      triggers: ruleForm.value.triggers,
      severity: ruleForm.value.severity,
      webhook_url: ruleForm.value.webhook_url.trim() || null,
    }
    if (editingRule.value) {
      const updated = await updateAlertRule(editingRule.value, payload)
      rules.value = rules.value.map((r) => (r.rule_id === editingRule.value ? updated : r))
      editingRule.value = null
    } else {
      const rule = await createAlertRule(payload)
      rules.value = [rule, ...rules.value]
    }
    ruleForm.value = emptyRuleForm()
  } catch (e) {
    error.value = e.message || 'Failed to save rule'
  } finally {
    saving.value = false
  }
}

async function deleteRule(ruleId) {
  try {
    await apiDeleteAlertRule(ruleId)
    rules.value = rules.value.filter((r) => r.rule_id !== ruleId)
    if (editingRule.value === ruleId) cancelEdit()
  } catch (e) {
    error.value = e.message || 'Failed to delete rule'
  }
}

// ---------------------------------------------------------------------------
// Webhooks tab
// ---------------------------------------------------------------------------
const rulesWithWebhooks = computed(() => rules.value.filter((r) => r.webhook_url))

const webhookTest = ref({ url: '', secret: '' })
const webhookTesting = ref(false)
const webhookTestResult = ref(null)

async function sendTestWebhook() {
  if (!webhookTest.value.url.trim()) return
  webhookTesting.value = true
  webhookTestResult.value = null
  try {
    const result = await apiTestWebhook({
      url: webhookTest.value.url.trim(),
      secret: webhookTest.value.secret.trim() || null,
    })
    webhookTestResult.value = result
  } catch (e) {
    webhookTestResult.value = { success: false, error: e.message }
  } finally {
    webhookTesting.value = false
  }
}

// ---------------------------------------------------------------------------
// Preferences tab
// ---------------------------------------------------------------------------
const preferences = ref({
  enabledTriggers: ['device_added', 'device_removed', 'link_added', 'link_removed', 'device_status_change'],
  minSeverity: 'info',
  channels: ['in_app'],
})
const savingPrefs = ref(false)
const prefsSaved = ref(false)

const channels = [
  { value: 'in_app', label: 'In-app alerts', icon: '&#x1F514;', note: null },
  { value: 'webhook', label: 'Webhooks', icon: '&#x1F517;', note: '(configure in Rules)' },
]

function severityButtonActive(sev) {
  return {
    info: 'border-gray-500 bg-gray-800/60 text-gray-200',
    warning: 'border-orange-500 bg-orange-900/30 text-orange-300',
    critical: 'border-red-500 bg-red-900/30 text-red-300',
  }[sev] || ''
}

async function loadPreferences() {
  try {
    const settings = await getSettings()
    if (settings.notifications) {
      const n = settings.notifications
      if (n.enabled_triggers) preferences.value.enabledTriggers = n.enabled_triggers
      if (n.min_severity) preferences.value.minSeverity = n.min_severity
      if (n.channels) preferences.value.channels = n.channels
    }
  } catch {
    // Settings may not have notifications section yet — use defaults
  }
}

async function savePreferences() {
  savingPrefs.value = true
  prefsSaved.value = false
  try {
    await updateSettings({
      notifications: {
        enabled_triggers: preferences.value.enabledTriggers,
        min_severity: preferences.value.minSeverity,
        channels: preferences.value.channels,
      },
    })
    prefsSaved.value = true
    setTimeout(() => { prefsSaved.value = false }, 2000)
  } catch (e) {
    error.value = e.message || 'Failed to save preferences'
  } finally {
    savingPrefs.value = false
  }
}

// ---------------------------------------------------------------------------
// Shared helpers
// ---------------------------------------------------------------------------
function formatDate(iso) {
  if (!iso) return ''
  return new Date(iso).toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function formatTrigger(t) {
  const map = {
    device_added: '+device',
    device_removed: '−device',
    link_added: '+link',
    link_removed: '−link',
    device_status_change: 'status\u2191',
    stp_change: 'stp',
  }
  return map[t] || t
}

function triggerBadge(t) {
  if (t === 'device_added' || t === 'link_added') return 'bg-green-900/40 text-green-400'
  if (t === 'device_removed' || t === 'link_removed') return 'bg-red-900/40 text-red-400'
  if (t === 'device_status_change') return 'bg-amber-900/40 text-orange-400'
  return 'bg-gray-700 text-gray-400'
}

function severityDot(s) {
  return { info: 'bg-gray-300', warning: 'bg-orange-400', critical: 'bg-red-500' }[s] || 'bg-gray-500'
}

function severityBadge(s) {
  return {
    info: 'bg-gray-800/40 text-gray-300',
    warning: 'bg-amber-900/40 text-orange-400',
    critical: 'bg-red-900/40 text-red-400',
  }[s] || 'bg-gray-700 text-gray-400'
}

async function handleAck(alertId, acked) {
  try {
    const updated = await apiAckAlert(alertId, acked)
    const idx = alerts.value.findIndex((a) => a.alert_id === alertId)
    if (idx >= 0) alerts.value = [...alerts.value.slice(0, idx), updated, ...alerts.value.slice(idx + 1)]
  } catch (e) {
    error.value = e.message || 'Failed to update alert'
  }
}

// ---------------------------------------------------------------------------
// Init
// ---------------------------------------------------------------------------
async function fetchAll() {
  loading.value = true
  error.value = null
  try {
    const [a, r] = await Promise.all([listAlerts(), listAlertRules()])
    alerts.value = a
    rules.value = r
  } catch (e) {
    error.value = e.message || 'Failed to load'
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  fetchAll()
  loadPreferences()
})
</script>
