import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import ProtocolFilter from '../ProtocolFilter.vue'

describe('ProtocolFilter', () => {
  it('renders three filter buttons', () => {
    const wrapper = mount(ProtocolFilter, {
      props: { modelValue: 'all' },
    })
    const buttons = wrapper.findAll('button')
    expect(buttons.length).toBe(3)
  })

  it('highlights the active filter', () => {
    const wrapper = mount(ProtocolFilter, {
      props: { modelValue: 'cdp' },
    })
    const buttons = wrapper.findAll('button')
    const activeButton = buttons.find(b => b.text().toLowerCase().includes('cdp'))
    expect(activeButton.classes().join(' ')).toContain('bg-')
  })

  it('emits update:modelValue when a filter is clicked', async () => {
    const wrapper = mount(ProtocolFilter, {
      props: { modelValue: 'all' },
    })
    const buttons = wrapper.findAll('button')
    // Click the second button (CDP)
    await buttons[1].trigger('click')
    expect(wrapper.emitted('update:modelValue')).toBeTruthy()
  })

  it('defaults to "all" filter', () => {
    const wrapper = mount(ProtocolFilter)
    expect(wrapper.text()).toContain('All')
  })
})
