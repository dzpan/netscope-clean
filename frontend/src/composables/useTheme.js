import { ref, watch, readonly } from 'vue'

const STORAGE_KEY = 'netscope-theme'
const THEMES = ['dark', 'light']

function getSystemPreference() {
  if (window.matchMedia?.('(prefers-color-scheme: light)').matches) {
    return 'light'
  }
  return 'dark'
}

function getInitialTheme() {
  const stored = localStorage.getItem(STORAGE_KEY)
  if (stored && THEMES.includes(stored)) return stored
  return getSystemPreference()
}

// Singleton state shared across all component instances
const theme = ref(getInitialTheme())

function applyTheme(value) {
  document.documentElement.setAttribute('data-theme', value)
}

// Apply immediately on module load
applyTheme(theme.value)

// Watch for changes
watch(theme, (value) => {
  applyTheme(value)
  localStorage.setItem(STORAGE_KEY, value)
})

// Listen for system preference changes (only when no explicit user choice)
window.matchMedia?.('(prefers-color-scheme: light)')
  .addEventListener('change', (e) => {
    if (!localStorage.getItem(STORAGE_KEY)) {
      theme.value = e.matches ? 'light' : 'dark'
    }
  })

export function useTheme() {
  function toggleTheme() {
    theme.value = theme.value === 'dark' ? 'light' : 'dark'
  }

  function setTheme(value) {
    if (THEMES.includes(value)) {
      theme.value = value
    }
  }

  const isDark = ref(theme.value === 'dark')
  watch(theme, (v) => { isDark.value = v === 'dark' })

  return {
    theme: readonly(theme),
    isDark,
    toggleTheme,
    setTheme,
  }
}
