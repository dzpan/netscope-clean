/**
 * NetScope API client — typed fetch wrappers.
 */

const BASE = '/api/v1'  // versioned API prefix; proxied by Vite in dev

const DEFAULT_TIMEOUT = 120_000  // 2 minutes
const LONG_TIMEOUT = 300_000     // 5 minutes for discovery/config-dump

/** Normalize FastAPI error detail (string | array of validation objects | object) into a readable message. */
function normalizeErrorDetail(detail, fallback) {
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail))
    return detail.map(e => (typeof e === 'object' ? (e.msg || JSON.stringify(e)) : String(e))).join('; ')
  return detail ? JSON.stringify(detail) : fallback
}

async function request(method, path, body = null, timeout = DEFAULT_TIMEOUT) {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeout)
  const opts = {
    method,
    headers: { 'Content-Type': 'application/json' },
    signal: controller.signal,
  }
  if (body !== null) opts.body = JSON.stringify(body)
  let res
  try {
    res = await fetch(BASE + path, opts)
  } catch (e) {
    if (e.name === 'AbortError') throw new Error('Request timed out', { cause: e })
    throw e
  } finally {
    clearTimeout(timer)
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(normalizeErrorDetail(err.detail, `HTTP ${res.status}`))
  }
  return res.json()
}

/** POST /discover — returns TopologyResult */
export function discover(payload) {
  return request('POST', '/discover', payload, LONG_TIMEOUT)
}

/** POST /probe — returns ProbeResult */
export function probe(payload) {
  return request('POST', '/probe', payload)
}

/** GET /sessions — returns TopologyResult[] */
export function listSessions() {
  return request('GET', '/sessions')
}

/** GET /sessions/:id — returns TopologyResult */
export function getSession(id) {
  return request('GET', `/sessions/${id}`)
}

/** POST /config-dump — run full show-command dump on a device */
export function createConfigDump(payload) {
  return request('POST', '/config-dump', payload, LONG_TIMEOUT)
}

/** GET /config-dump?device_id=X — list dumps, optionally filtered by device */
export function listConfigDumps(deviceId = null) {
  const qs = deviceId ? `?device_id=${encodeURIComponent(deviceId)}` : ''
  return request('GET', `/config-dump${qs}`)
}

/** GET /config-dump/:id — fetch a single dump */
export function getConfigDump(dumpId) {
  return request('GET', `/config-dump/${dumpId}`)
}

/** Download dump as .txt file */
export function downloadConfigDump(dumpId) {
  const a = document.createElement('a')
  a.href = `/config-dump/${dumpId}/download`
  a.download = ''
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
}

/** POST /retry — retry auth-failed devices with new credentials */
export function retryAuth(payload) {
  return request('POST', '/retry', payload)
}

/** POST /retry-failed — retry all failed devices (any failure type) */
export function retryFailed(payload) {
  return request('POST', '/retry-failed', payload, LONG_TIMEOUT)
}

/**
 * POST /discover/stream — SSE-powered discovery with real-time progress.
 * Returns { eventSource, resultPromise }.
 * @param {Object} payload - DiscoverRequest body
 * @param {function} onProgress - called with DiscoveryProgress objects
 * @returns {Promise<Object>} TopologyResult
 */
export function discoverWithProgress(payload, onProgress) {
  return new Promise((resolve, reject) => {
    const controller = new AbortController()

    // Overall timeout: abort if no result within 5 minutes
    const overallTimer = setTimeout(() => {
      if (!settled) {
        settled = true
        controller.abort()
        reject(new Error('Discovery timed out — no result received within 5 minutes'))
      }
    }, LONG_TIMEOUT)

    let settled = false

    fetch(BASE + '/discover/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
      signal: controller.signal,
    }).then(res => {
      if (!res.ok) {
        res.json().catch(() => ({ detail: res.statusText })).then(err => {
          if (!settled) {
            settled = true
            clearTimeout(overallTimer)
            reject(new Error(normalizeErrorDetail(err.detail, `HTTP ${res.status}`)))
          }
        })
        return
      }

      const reader = res.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      // Track currentEvent across chunks — SSE event: and data: lines
      // may arrive in separate TCP segments for large payloads
      let currentEvent = null

      function processChunk() {
        reader.read().then(({ done, value }) => {
          if (done) {
            // Flush decoder and process any remaining buffered data
            buffer += decoder.decode()
            if (buffer.trim()) {
              processLines(buffer.split('\n'))
            }
            // If the promise was never resolved (e.g. stream closed unexpectedly),
            // reject so the UI doesn't hang forever
            if (!settled) {
              settled = true
              clearTimeout(overallTimer)
              reject(new Error('Discovery stream ended without a result'))
            }
            return
          }

          buffer += decoder.decode(value, { stream: true })
          const lines = buffer.split('\n')
          buffer = lines.pop() // keep incomplete line

          processLines(lines)
          if (!settled) processChunk()
        }).catch(err => {
          if (err.name !== 'AbortError' && !settled) {
            settled = true
            clearTimeout(overallTimer)
            reject(err)
          }
        })
      }

      function processLines(lines) {
        for (const line of lines) {
          if (settled) return
          if (line.startsWith('event: ')) {
            currentEvent = line.slice(7).trim()
          } else if (line.startsWith('data: ') && currentEvent) {
            const data = line.slice(6)
            try {
              const parsed = JSON.parse(data)
              if (currentEvent === 'progress' && onProgress) {
                onProgress(parsed)
              } else if (currentEvent === 'result') {
                settled = true
                clearTimeout(overallTimer)
                resolve(parsed)
              } else if (currentEvent === 'error') {
                settled = true
                clearTimeout(overallTimer)
                reject(new Error(data))
              }
            } catch (parseErr) {
              // JSON parse failed — for result events this is fatal
              if (currentEvent === 'result') {
                settled = true
                clearTimeout(overallTimer)
                reject(new Error('Failed to parse discovery result'))
              } else if (currentEvent === 'error') {
                settled = true
                clearTimeout(overallTimer)
                reject(new Error(data))
              }
            }
            currentEvent = null
          } else if (line === '' || line.startsWith(':')) {
            // SSE event boundary or comment — do NOT reset currentEvent
            // because event: and data: lines may arrive in separate chunks.
            // Only reset after we've processed the data: line (above).
          }
        }
      }

      processChunk()
    }).catch(err => {
      if (err.name !== 'AbortError' && !settled) {
        clearTimeout(overallTimer)
        reject(err)
      }
    })
  })
}

/** GET /sessions/:id/vlan-map — network-wide VLAN summary */
export function getVlanMap(sessionId) {
  return request('GET', `/sessions/${sessionId}/vlan-map`)
}

/** GET /sessions/:id/summary — discovery summary dashboard */
export function getSessionSummary(sessionId) {
  return request('GET', `/sessions/${sessionId}/summary`)
}

/** POST /sessions/:id/resolve-placeholder — manually resolve a placeholder device */
export function resolvePlaceholder(sessionId, payload) {
  return request('POST', `/sessions/${sessionId}/resolve-placeholder`, payload)
}

/** GET /demo — loads fake topology, returns TopologyResult */
export function loadDemo() {
  return request('GET', '/demo')
}

/** Export download helpers — return a download URL */
export function exportUrl(sessionId, format) {
  return `${BASE}/export/${sessionId}/${format}`
}

export function downloadExport(sessionId, format) {
  const url = exportUrl(sessionId, format)
  const a = document.createElement('a')
  a.href = url
  a.download = ''
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
}

/** POST /sessions/:id/rediscover — re-run discovery with same parameters */
export function rediscover(sessionId, body = null) {
  return request('POST', `/sessions/${sessionId}/rediscover`, body, LONG_TIMEOUT)
}

/** GET /sessions/:id/diff/:previousId — get diff between two snapshots */
export function getDiff(currentId, previousId) {
  return request('GET', `/sessions/${currentId}/diff/${previousId}`)
}

/** GET /search?q=<term> — full-text search across all collected network data */
export function searchDevices(q, sessionId = null, limit = 50) {
  const params = new URLSearchParams({ q, limit })
  if (sessionId) params.set('session_id', sessionId)
  return request('GET', `/search?${params}`)
}

/** GET /snapshots — list all snapshot metadata (no full device data) */
export function listSnapshots() {
  return request('GET', '/snapshots')
}

/** GET /snapshots/:id — load a full topology snapshot */
export function getSnapshot(id) {
  return request('GET', `/snapshots/${id}`)
}

/** POST /alerts/rules — create a new alert rule */
export function createAlertRule(payload) {
  return request('POST', '/alerts/rules', payload)
}

/** GET /alerts/rules — list all alert rules */
export function listAlertRules() {
  return request('GET', '/alerts/rules')
}

/** PUT /alerts/rules/:id — update an alert rule */
export function updateAlertRule(ruleId, payload) {
  return request('PUT', `/alerts/rules/${ruleId}`, payload)
}

/** DELETE /alerts/rules/:id — delete an alert rule */
export function deleteAlertRule(ruleId) {
  return request('DELETE', `/alerts/rules/${ruleId}`)
}

/** POST /alerts/test-webhook — test a webhook endpoint */
export function testWebhook(payload) {
  return request('POST', '/alerts/test-webhook', payload)
}

/** GET /alerts — list recent fired alerts */
export function listAlerts(limit = 200) {
  return request('GET', `/alerts?limit=${limit}`)
}

/** PATCH /alerts/:id/ack — acknowledge or un-acknowledge an alert */
export function ackAlert(alertId, acknowledged = true) {
  return request('PATCH', `/alerts/${alertId}/ack`, { acknowledged })
}

/** POST /sessions/:id/path-trace — trace L3 path from source to destination */
export function pathTrace(sessionId, payload) {
  return request('POST', `/sessions/${sessionId}/path-trace`, payload)
}

// ---------------------------------------------------------------------------
// Advanced Mode — write operations (VLAN changes, audit, undo)
// ---------------------------------------------------------------------------

/** GET /advanced/status — check if Advanced Mode is available */
export function getAdvancedStatus() {
  return request('GET', '/advanced/status')
}

/** POST /advanced/authenticate — verify password to enable Advanced Mode */
export function authenticateAdvanced(password) {
  return request('POST', '/advanced/authenticate', { password })
}

/** POST /advanced/vlan-change — execute VLAN change on selected ports */
export function executeVlanChange(payload) {
  return request('POST', '/advanced/vlan-change', payload, LONG_TIMEOUT)
}

/** GET /advanced/audit — list audit records (paginated, filterable) */
export function listAuditRecords({ deviceId, status, limit, offset } = {}) {
  const params = new URLSearchParams()
  if (deviceId) params.set('device_id', deviceId)
  if (status) params.set('status', status)
  if (limit) params.set('limit', String(limit))
  if (offset) params.set('offset', String(offset))
  const qs = params.toString()
  return request('GET', `/advanced/audit${qs ? '?' + qs : ''}`)
}

/** GET /advanced/audit/:id — get single audit record with full detail */
export function getAuditRecord(auditId) {
  return request('GET', `/advanced/audit/${encodeURIComponent(auditId)}`)
}

/** POST /advanced/audit/:id/undo — undo a specific change */
export function undoAuditRecord(auditId, credentials) {
  return request('POST', `/advanced/audit/${encodeURIComponent(auditId)}/undo`, credentials, LONG_TIMEOUT)
}

// ---------------------------------------------------------------------------
// Playbooks — configuration playbook management and execution
// ---------------------------------------------------------------------------

/** GET /playbooks — list all playbooks (with optional search/filter) */
export function listPlaybooks({ search, category, platform } = {}) {
  const params = new URLSearchParams()
  if (search) params.set('search', search)
  if (category) params.set('category', category)
  if (platform) params.set('platform', platform)
  const qs = params.toString()
  return request('GET', `/playbooks${qs ? '?' + qs : ''}`)
}

/** GET /playbooks/:id — get playbook details */
export function getPlaybook(id) {
  return request('GET', `/playbooks/${encodeURIComponent(id)}`)
}

/** POST /playbooks — create new playbook */
export function createPlaybook(payload) {
  return request('POST', '/playbooks', payload)
}

/** PUT /playbooks/:id — update playbook */
export function updatePlaybook(id, payload) {
  return request('PUT', `/playbooks/${encodeURIComponent(id)}`, payload)
}

/** DELETE /playbooks/:id — delete playbook */
export function deletePlaybook(id) {
  return request('DELETE', `/playbooks/${encodeURIComponent(id)}`)
}

/** POST /playbooks/import — import playbook from YAML */
export function importPlaybook(yamlString) {
  return request('POST', '/playbooks/import', { yaml: yamlString })
}

/** GET /playbooks/:id/export — export playbook as YAML */
export function exportPlaybook(id) {
  return request('GET', `/playbooks/${encodeURIComponent(id)}/export`)
}

/** POST /playbooks/:id/dry-run — preview interpolated commands */
export function playbookDryRun(id, payload) {
  return request('POST', `/playbooks/${encodeURIComponent(id)}/dry-run`, payload)
}

/** POST /playbooks/:id/execute — execute playbook against device(s) */
export function executePlaybook(id, payload) {
  return request('POST', `/playbooks/${encodeURIComponent(id)}/execute`, payload, LONG_TIMEOUT)
}

/** GET /playbook-runs — list execution history */
export function listPlaybookRuns({ playbookId, deviceId, status, limit, offset } = {}) {
  const params = new URLSearchParams()
  if (playbookId) params.set('playbook_id', playbookId)
  if (deviceId) params.set('device_id', deviceId)
  if (status) params.set('status', status)
  if (limit) params.set('limit', String(limit))
  if (offset) params.set('offset', String(offset))
  const qs = params.toString()
  return request('GET', `/playbook-runs${qs ? '?' + qs : ''}`)
}

/** GET /playbook-runs/:id — get execution details */
export function getPlaybookRun(id) {
  return request('GET', `/playbook-runs/${encodeURIComponent(id)}`)
}

/** POST /playbook-runs/:id/undo — undo an execution */
export function undoPlaybookRun(id, credentials) {
  return request('POST', `/playbook-runs/${encodeURIComponent(id)}/undo`, credentials, LONG_TIMEOUT)
}

/** GET /playbook-runs/:id/diff — compare config snapshots */
export function diffPlaybookRun(id, compareRunId) {
  const params = compareRunId ? `?compare_run_id=${encodeURIComponent(compareRunId)}` : ''
  return request('GET', `/playbook-runs/${encodeURIComponent(id)}/diff${params}`)
}

// ---------------------------------------------------------------------------
// Backup / Restore & Session Import / Export
// ---------------------------------------------------------------------------

/** GET /backup/database — download full SQLite backup */
export function downloadBackup() {
  const a = document.createElement('a')
  a.href = `${BASE}/backup/database`
  a.download = ''
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
}

/** POST /backup/restore — upload a .db backup file to restore */
export async function restoreBackup(file) {
  const form = new FormData()
  form.append('file', file)
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), LONG_TIMEOUT)
  try {
    const res = await fetch(`${BASE}/backup/restore`, {
      method: 'POST',
      body: form,
      signal: controller.signal,
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }))
      throw new Error(normalizeErrorDetail(err.detail, `HTTP ${res.status}`))
    }
    return res.json()
  } finally {
    clearTimeout(timer)
  }
}

/** GET /sessions/:id/export-bundle — download session as portable JSON bundle */
export function downloadSessionBundle(sessionId) {
  const a = document.createElement('a')
  a.href = `${BASE}/sessions/${sessionId}/export-bundle`
  a.download = ''
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
}

/** POST /sessions/import-bundle — upload a session bundle JSON file */
export async function importSessionBundle(file) {
  const form = new FormData()
  form.append('file', file)
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), LONG_TIMEOUT)
  try {
    const res = await fetch(`${BASE}/sessions/import-bundle`, {
      method: 'POST',
      body: form,
      signal: controller.signal,
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }))
      throw new Error(normalizeErrorDetail(err.detail, `HTTP ${res.status}`))
    }
    return res.json()
  } finally {
    clearTimeout(timer)
  }
}

// ---------------------------------------------------------------------------
// Settings — persistent configuration management
// ---------------------------------------------------------------------------

/** GET /settings — retrieve all settings (merged: saved + env overrides) */
export function getSettings() {
  return request('GET', '/settings')
}

/** PUT /settings — update settings (partial update, env vars still override) */
export function updateSettings(payload) {
  return request('PUT', '/settings', payload)
}

/** POST /settings/test-credential — test SSH connectivity with a credential set */
export function testCredential(payload) {
  return request('POST', '/settings/test-credential', payload)
}

/** POST /settings/reset — reset all settings to defaults */
export function resetSettings() {
  return request('POST', '/settings/reset')
}

// ---------------------------------------------------------------------------
// Saved Views & Annotations
// ---------------------------------------------------------------------------

/** GET /views — list saved topology views */
export function listViews(sessionId = null) {
  const qs = sessionId ? `?session_id=${encodeURIComponent(sessionId)}` : ''
  return request('GET', `/views${qs}`)
}

/** GET /views/:id — get a single saved view */
export function getView(viewId) {
  return request('GET', `/views/${encodeURIComponent(viewId)}`)
}

/** POST /views — create a new saved view */
export function createView(payload) {
  return request('POST', '/views', payload)
}

/** PUT /views/:id — update a saved view */
export function updateView(viewId, payload) {
  return request('PUT', `/views/${encodeURIComponent(viewId)}`, payload)
}

/** DELETE /views/:id — delete a saved view */
export function deleteView(viewId) {
  return request('DELETE', `/views/${encodeURIComponent(viewId)}`)
}

/** PATCH /views/:id/rename — rename a saved view */
export function renameView(viewId, name) {
  return request('PATCH', `/views/${encodeURIComponent(viewId)}/rename`, { name })
}

/** PATCH /views/:id/default — set view as default */
export function setDefaultView(viewId) {
  return request('PATCH', `/views/${encodeURIComponent(viewId)}/default`)
}

/** POST /views/:id/annotations — add annotation to view */
export function addAnnotation(viewId, payload) {
  return request('POST', `/views/${encodeURIComponent(viewId)}/annotations`, payload)
}

/** PUT /views/:viewId/annotations/:annotationId — update annotation */
export function updateAnnotation(viewId, annotationId, payload) {
  return request('PUT', `/views/${encodeURIComponent(viewId)}/annotations/${encodeURIComponent(annotationId)}`, payload)
}

/** DELETE /views/:viewId/annotations/:annotationId — delete annotation */
export function deleteAnnotation(viewId, annotationId) {
  return request('DELETE', `/views/${encodeURIComponent(viewId)}/annotations/${encodeURIComponent(annotationId)}`)
}

/** GET /advanced/audit/export — export audit log as CSV or JSON */
export function exportAuditLog(format = 'csv') {
  const a = document.createElement('a')
  a.href = `${BASE}/advanced/audit/export?format=${encodeURIComponent(format)}`
  a.download = ''
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
}
