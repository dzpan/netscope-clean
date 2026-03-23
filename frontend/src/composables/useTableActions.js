import { ref, computed } from 'vue'

/**
 * Composable for table sorting, filtering, CSV export, and clipboard copy.
 *
 * @param {() => Array} dataFn - reactive getter returning the raw data array
 * @param {Array<{key: string, label: string}>} columns - column definitions
 */
export function useTableActions(dataFn, columns) {
  const sortKey = ref(null)
  const sortAsc = ref(true)
  const search = ref('')

  const filtered = computed(() => {
    const term = search.value.trim().toLowerCase()
    let rows = dataFn() || []
    if (term) {
      const keys = columns.map(c => c.key)
      rows = rows.filter(row =>
        keys.some(k => String(row[k] ?? '').toLowerCase().includes(term))
      )
    }
    return rows
  })

  const sorted = computed(() => {
    const rows = [...filtered.value]
    const key = sortKey.value
    if (!key) return rows
    const dir = sortAsc.value ? 1 : -1
    return rows.sort((a, b) => {
      const va = a[key] ?? ''
      const vb = b[key] ?? ''
      if (typeof va === 'number' && typeof vb === 'number') return (va - vb) * dir
      return String(va).localeCompare(String(vb), undefined, { numeric: true }) * dir
    })
  })

  function toggleSort(key) {
    if (sortKey.value === key) {
      sortAsc.value = !sortAsc.value
    } else {
      sortKey.value = key
      sortAsc.value = true
    }
  }

  function sortIndicator(key) {
    if (sortKey.value !== key) return ''
    return sortAsc.value ? ' ↑' : ' ↓'
  }

  function toCsvString(rows) {
    const header = columns.map(c => c.label).join(',')
    const body = rows.map(row =>
      columns.map(c => {
        const val = String(row[c.key] ?? '')
        // Escape CSV fields containing commas, quotes, or newlines
        if (/[,"\n\r]/.test(val)) return '"' + val.replace(/"/g, '""') + '"'
        return val
      }).join(',')
    ).join('\n')
    return header + '\n' + body
  }

  function exportCsv(filename) {
    const csv = toCsvString(sorted.value)
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    a.click()
    URL.revokeObjectURL(url)
  }

  const copyStatus = ref('')

  async function copyTable() {
    const csv = toCsvString(sorted.value)
    try {
      await navigator.clipboard.writeText(csv)
      copyStatus.value = 'Copied!'
      setTimeout(() => { copyStatus.value = '' }, 1500)
    } catch {
      copyStatus.value = 'Failed'
      setTimeout(() => { copyStatus.value = '' }, 1500)
    }
  }

  return { search, sortKey, sortAsc, filtered, sorted, toggleSort, sortIndicator, exportCsv, copyTable, copyStatus }
}
