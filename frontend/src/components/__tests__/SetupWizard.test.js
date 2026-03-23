import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import SetupWizard from '../SetupWizard.vue'

// Mock the API module
vi.mock('../../api.js', () => ({
  probe: vi.fn(),
  loadDemo: vi.fn(),
}))

const teleportStub = { Teleport: true }

describe('SetupWizard', () => {
  it('renders wizard content when visible', () => {
    const wrapper = mount(SetupWizard, {
      props: { visible: true },
      global: { stubs: teleportStub },
    })
    // Should contain NetScope branding or setup text
    expect(wrapper.text()).toContain('Scope')
  })

  it('shows skip button', () => {
    const wrapper = mount(SetupWizard, {
      props: { visible: true },
      global: { stubs: teleportStub },
    })
    const skipBtn = wrapper.findAll('button').find(b =>
      b.text().toLowerCase().includes('skip')
    )
    expect(skipBtn).toBeDefined()
  })

  it('emits skip when skip button is clicked', async () => {
    const wrapper = mount(SetupWizard, {
      props: { visible: true },
      global: { stubs: teleportStub },
    })
    const skipBtn = wrapper.findAll('button').find(b =>
      b.text().toLowerCase().includes('skip')
    )
    if (skipBtn) {
      await skipBtn.trigger('click')
      expect(wrapper.emitted('skip')).toBeTruthy()
    }
  })

  it('does not render content when not visible', () => {
    const wrapper = mount(SetupWizard, {
      props: { visible: false },
      global: { stubs: teleportStub },
    })
    // v-if="visible" should hide the wizard content
    expect(wrapper.find('.fixed').exists()).toBe(false)
  })
})
