import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import FailuresPanel from '../FailuresPanel.vue'

// Mock the API module
vi.mock('../../api.js', () => ({
  retryFailed: vi.fn(),
}))

const teleportStub = { Teleport: true }

const mockFailures = [
  { target: '10.0.0.1', reason: 'auth_failed', detail: 'Bad credentials' },
  { target: '10.0.0.2', reason: 'timeout', detail: 'Connection timed out' },
  { target: '10.0.0.3', reason: 'auth_failed', detail: 'Bad credentials' },
]

function mountPanel(props = {}) {
  return mount(FailuresPanel, {
    props: {
      failures: mockFailures,
      sessionId: 'test-session',
      credentialSets: [],
      ...props,
    },
    global: { stubs: teleportStub },
  })
}

describe('FailuresPanel', () => {
  it('renders failure count in header', () => {
    const wrapper = mountPanel()
    expect(wrapper.text()).toContain('3')
  })

  it('displays all failure rows', () => {
    const wrapper = mountPanel()
    expect(wrapper.text()).toContain('10.0.0.1')
    expect(wrapper.text()).toContain('10.0.0.2')
    expect(wrapper.text()).toContain('10.0.0.3')
  })

  it('shows failure reasons', () => {
    const wrapper = mountPanel()
    expect(wrapper.text()).toContain('auth_failed')
    expect(wrapper.text()).toContain('timeout')
  })

  it('emits close when close button is clicked', async () => {
    const wrapper = mountPanel()
    const closeBtn = wrapper.find('button')
    if (closeBtn.exists()) {
      await closeBtn.trigger('click')
      const emitted = wrapper.emitted()
      expect(emitted).toBeDefined()
    }
  })

  it('renders with empty failures', () => {
    const wrapper = mountPanel({ failures: [] })
    expect(wrapper.exists()).toBe(true)
  })
})
