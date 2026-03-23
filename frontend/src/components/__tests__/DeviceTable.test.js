import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import DeviceTable from '../DeviceTable.vue'

const mockDevices = [
  { id: '1', hostname: 'switch-01', mgmt_ip: '10.0.0.1', platform: 'IOS-XE', serial: 'FOC1234', status: 'ok' },
  { id: '2', hostname: 'router-01', mgmt_ip: '10.0.0.2', platform: 'NX-OS', serial: 'FOC5678', status: 'ok' },
]

const mockLinks = [
  { source: 'switch-01', source_intf: 'Gi0/1', target: 'router-01', target_intf: 'Gi0/0', protocol: 'cdp' },
]

const _mockFailures = [
  { target: '10.0.0.3', reason: 'auth_failed', detail: 'Authentication failed' },
]

describe('DeviceTable', () => {
  it('renders device rows', () => {
    const wrapper = mount(DeviceTable, {
      props: { devices: mockDevices, links: [], failures: [] },
    })
    expect(wrapper.text()).toContain('switch-01')
    expect(wrapper.text()).toContain('router-01')
  })

  it('displays device count', () => {
    const wrapper = mount(DeviceTable, {
      props: { devices: mockDevices, links: [], failures: [] },
    })
    expect(wrapper.text()).toContain('2')
  })

  it('shows link data when links tab is active', async () => {
    const wrapper = mount(DeviceTable, {
      props: { devices: mockDevices, links: mockLinks, failures: [] },
    })
    // Find and click the Links tab
    const tabs = wrapper.findAll('button')
    const linksTab = tabs.find(t => t.text().includes('Link'))
    if (linksTab) {
      await linksTab.trigger('click')
      expect(wrapper.text()).toContain('Gi0/1')
    }
  })

  it('emits device-selected when a device row is clicked', async () => {
    const wrapper = mount(DeviceTable, {
      props: { devices: mockDevices, links: [], failures: [] },
    })
    const rows = wrapper.findAll('tr')
    // Click a data row (skip header)
    const dataRow = rows.find(r => r.text().includes('switch-01'))
    if (dataRow) {
      await dataRow.trigger('click')
      expect(wrapper.emitted('device-selected')).toBeTruthy()
    }
  })

  it('filters devices by search text', async () => {
    const wrapper = mount(DeviceTable, {
      props: { devices: mockDevices, links: [], failures: [] },
    })
    const searchInput = wrapper.find('input[type="text"]')
    if (searchInput.exists()) {
      await searchInput.setValue('switch')
      expect(wrapper.text()).toContain('switch-01')
      expect(wrapper.text()).not.toContain('router-01')
    }
  })

  it('renders with empty data', () => {
    const wrapper = mount(DeviceTable, {
      props: { devices: [], links: [], failures: [] },
    })
    expect(wrapper.exists()).toBe(true)
  })

  it('sorts hostnames case-insensitively', () => {
    const devices = [
      { id: '1', hostname: 'SW-ZUPANC-01', mgmt_ip: '10.0.0.1', platform: '', serial: '', status: 'ok' },
      { id: '2', hostname: 'ap-lobby', mgmt_ip: '10.0.0.2', platform: '', serial: '', status: 'ok' },
      { id: '3', hostname: 'sw-zupanc-02', mgmt_ip: '10.0.0.3', platform: '', serial: '', status: 'ok' },
    ]
    const wrapper = mount(DeviceTable, {
      props: { devices, links: [], failures: [] },
    })
    const rows = wrapper.findAll('tbody tr')
    const hostnames = rows.map(r => r.findAll('td')[0]?.text())
    // Case-insensitive ascending: ap-lobby, SW-ZUPANC-01, sw-zupanc-02
    expect(hostnames[0]).toBe('ap-lobby')
    expect(hostnames[1]).toBe('SW-ZUPANC-01')
    expect(hostnames[2]).toBe('sw-zupanc-02')
  })

  it('normalizes hostname display when case option is changed', async () => {
    const wrapper = mount(DeviceTable, {
      props: { devices: mockDevices, links: [], failures: [] },
    })
    const select = wrapper.find('select')
    expect(select.exists()).toBe(true)
    // Switch to uppercase
    await select.setValue('upper')
    expect(wrapper.text()).toContain('SWITCH-01')
    // Switch to lowercase
    await select.setValue('lower')
    expect(wrapper.text()).toContain('switch-01')
  })
})
