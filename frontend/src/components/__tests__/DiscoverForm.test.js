import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import DiscoverForm from '../DiscoverForm.vue'

// Mock the API module
vi.mock('../../api.js', () => ({
  probe: vi.fn(),
  listSessions: vi.fn().mockResolvedValue([]),
}))

describe('DiscoverForm', () => {
  it('renders the discover form', () => {
    const wrapper = mount(DiscoverForm, {
      props: { loading: false },
    })
    expect(wrapper.exists()).toBe(true)
  })

  it('shows seed input field', () => {
    const wrapper = mount(DiscoverForm, {
      props: { loading: false },
    })
    const textarea = wrapper.find('textarea')
    expect(textarea.exists()).toBe(true)
  })

  it('shows credential fields', () => {
    const wrapper = mount(DiscoverForm, {
      props: { loading: false },
    })
    const text = wrapper.text().toLowerCase()
    expect(text.includes('username') || text.includes('credential')).toBe(true)
  })

  it('disables form when loading', () => {
    const wrapper = mount(DiscoverForm, {
      props: { loading: true },
    })
    const discoverBtn = wrapper.findAll('button').find(b =>
      b.text().toLowerCase().includes('discover')
    )
    if (discoverBtn) {
      expect(discoverBtn.attributes('disabled')).toBeDefined()
    }
  })

  it('shows collection profile options', () => {
    const wrapper = mount(DiscoverForm, {
      props: { loading: false },
    })
    const text = wrapper.text().toLowerCase()
    expect(text.includes('minimal') || text.includes('standard') || text.includes('profile')).toBe(true)
  })
})
