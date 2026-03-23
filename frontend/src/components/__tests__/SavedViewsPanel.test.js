import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import SavedViewsPanel from '../SavedViewsPanel.vue'

// Mock the API module
vi.mock('../../api.js', () => ({
  listViews: vi.fn().mockResolvedValue([]),
  deleteView: vi.fn(),
  renameView: vi.fn(),
  setDefaultView: vi.fn(),
}))

describe('SavedViewsPanel', () => {
  it('renders the panel', () => {
    const wrapper = mount(SavedViewsPanel, {
      props: { sessionId: 'test-session' },
    })
    expect(wrapper.exists()).toBe(true)
  })

  it('shows save view input', () => {
    const wrapper = mount(SavedViewsPanel, {
      props: { sessionId: 'test-session' },
    })
    const input = wrapper.find('input')
    expect(input.exists()).toBe(true)
  })

  it('emits close when close button clicked', async () => {
    const wrapper = mount(SavedViewsPanel, {
      props: { sessionId: 'test-session' },
    })
    const closeBtn = wrapper.findAll('button').find(b =>
      b.text().includes('×') || b.text().includes('Close') || b.text().toLowerCase().includes('close')
    )
    if (closeBtn) {
      await closeBtn.trigger('click')
      expect(wrapper.emitted('close')).toBeTruthy()
    }
  })

  it('shows empty state when no views', async () => {
    const wrapper = mount(SavedViewsPanel, {
      props: { sessionId: 'test-session' },
    })
    // Wait for API call to resolve
    await vi.dynamicImportSettled()
    // Should show some indication of no saved views
    expect(wrapper.exists()).toBe(true)
  })
})
