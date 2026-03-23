/**
 * v-resizable-columns directive
 *
 * Adds draggable resize handles to <table> column headers.
 * Usage: <table v-resizable-columns> or <table v-resizable-columns="'my-table-key'">
 *
 * When a storage key is provided, column widths persist to localStorage.
 */

const _HANDLE_WIDTH = 6 // px — clickable area for the drag handle
const MIN_COL_WIDTH = 40 // px

function createHandle() {
  const handle = document.createElement('div')
  handle.className = 'col-resize-handle'
  return handle
}

function saveWidths(key, widths) {
  if (!key) return
  try {
    localStorage.setItem(`netscope-col-widths:${key}`, JSON.stringify(widths))
  } catch {
    // quota exceeded — silently ignore
  }
}

function loadWidths(key) {
  if (!key) return null
  try {
    const raw = localStorage.getItem(`netscope-col-widths:${key}`)
    return raw ? JSON.parse(raw) : null
  } catch {
    return null
  }
}

function setup(el, storageKey) {
  const thead = el.querySelector('thead')
  if (!thead) return

  const ths = Array.from(thead.querySelectorAll('tr:first-child th'))
  if (!ths.length) return

  // Make table use fixed layout so column widths are respected
  el.style.tableLayout = 'fixed'

  // Restore saved widths
  const saved = loadWidths(storageKey)
  ths.forEach((th, i) => {
    th.style.position = 'relative'
    th.style.overflow = 'hidden'
    th.style.textOverflow = 'ellipsis'
    th.style.whiteSpace = 'nowrap'

    if (saved && saved[i]) {
      th.style.width = saved[i] + 'px'
    }

    // Skip last column — no resize handle needed on the rightmost header
    if (i === ths.length - 1) return

    const handle = createHandle()
    th.appendChild(handle)

    let startX = 0
    let startWidth = 0
    let nextStartWidth = 0

    function onMouseDown(e) {
      e.preventDefault()
      e.stopPropagation()
      startX = e.clientX
      startWidth = th.offsetWidth
      const nextTh = ths[i + 1]
      nextStartWidth = nextTh ? nextTh.offsetWidth : 0

      document.body.style.cursor = 'col-resize'
      document.body.style.userSelect = 'none'
      handle.classList.add('active')

      document.addEventListener('mousemove', onMouseMove)
      document.addEventListener('mouseup', onMouseUp)
    }

    function onMouseMove(e) {
      const dx = e.clientX - startX
      const newWidth = Math.max(MIN_COL_WIDTH, startWidth + dx)
      th.style.width = newWidth + 'px'

      // Adjust next column to keep total width stable
      const nextTh = ths[i + 1]
      if (nextTh) {
        const nextWidth = Math.max(MIN_COL_WIDTH, nextStartWidth - dx)
        nextTh.style.width = nextWidth + 'px'
      }
    }

    function onMouseUp() {
      document.body.style.cursor = ''
      document.body.style.userSelect = ''
      handle.classList.remove('active')

      document.removeEventListener('mousemove', onMouseMove)
      document.removeEventListener('mouseup', onMouseUp)

      // Persist widths
      const widths = ths.map(t => t.offsetWidth)
      saveWidths(storageKey, widths)
    }

    handle.addEventListener('mousedown', onMouseDown)
  })
}

function cleanup(el) {
  const handles = el.querySelectorAll('.col-resize-handle')
  handles.forEach(h => h.remove())
  el.style.tableLayout = ''
}

// Use MutationObserver to re-setup when thead content changes (e.g. v-if tab switches)
function observe(el, storageKey) {
  const observer = new MutationObserver(() => {
    // Disconnect before modifying DOM to prevent re-entrant triggers
    observer.disconnect()
    cleanup(el)
    setup(el, storageKey)
    // Reconnect after DOM modifications are complete
    observer.observe(el, { childList: true, subtree: true })
  })
  observer.observe(el, { childList: true, subtree: true })
  el._resizeObserver = observer
}

export const vResizableColumns = {
  mounted(el, binding) {
    const storageKey = binding.value || null
    // Defer to next frame so table has rendered its content
    requestAnimationFrame(() => {
      setup(el, storageKey)
      observe(el, storageKey)
    })
  },
  updated(el, binding) {
    // Re-run setup if storage key changes
    const storageKey = binding.value || null
    // Disconnect observer during update to prevent infinite loop
    if (el._resizeObserver) el._resizeObserver.disconnect()
    cleanup(el)
    requestAnimationFrame(() => {
      setup(el, storageKey)
      if (el._resizeObserver) {
        el._resizeObserver.observe(el, { childList: true, subtree: true })
      }
    })
  },
  unmounted(el) {
    if (el._resizeObserver) {
      el._resizeObserver.disconnect()
      delete el._resizeObserver
    }
    cleanup(el)
  },
}
