<template>
  <Transition name="slide">
    <div v-if="device" class="flex flex-col h-full overflow-hidden">
      <!-- Header -->
      <div class="flex items-center justify-between px-4 py-3 border-b border-gray-700 shrink-0">
        <div>
          <h2 class="font-semibold text-gray-100 truncate font-mono">{{ device.hostname || device.id }}</h2>
          <p class="text-xs text-gray-400">{{ device.mgmt_ip }}</p>
        </div>
        <button class="btn-ghost p-1 text-gray-500 hover:text-gray-200" @click="$emit('close')">✕</button>
      </div>

      <!-- Tabs -->
      <div class="flex border-b border-gray-700 shrink-0">
        <button
          v-for="tab in tabs"
          :key="tab.key"
          class="px-3 py-2 text-xs font-medium border-b-2 transition-colors"
          :class="activeTab === tab.key
            ? 'border-orange-500 text-orange-400'
            : 'border-transparent text-gray-500 hover:text-gray-300'"
          @click="activeTab = tab.key"
        >
          {{ tab.label }}
          <span v-if="tab.count" class="ml-1 text-gray-600">({{ tab.count }})</span>
        </button>
      </div>

      <!-- Config tab body (full-height, no padding) -->
      <template v-if="activeTab === 'config'">
        <div class="flex-1 overflow-hidden">
          <ConfigDumpPanel :device="device" :show-header="false" />
        </div>
      </template>

      <!-- Body (all non-config tabs) -->
      <div v-else class="flex-1 overflow-y-auto p-4 flex flex-col gap-4">

        <!-- =========== OVERVIEW TAB =========== -->
        <template v-if="activeTab === 'overview'">
          <!-- Status badge + Actions -->
          <div class="flex items-center justify-between">
            <span :class="statusClass(device.status)" class="badge">
              {{ device.status }}
            </span>
            <div class="flex items-center gap-2">
              <a
                v-if="device.mgmt_ip"
                :href="`ssh://${device.mgmt_ip}`"
                class="btn-secondary text-xs px-2 py-1 inline-flex items-center gap-1 no-underline"
                title="Open SSH session"
              >
                >_ SSH
              </a>
              <button
                v-if="device.status === 'ok'"
                class="btn-secondary text-xs px-2 py-1"
                @click="$emit('config-dump', device)"
              >
                Config Dump
              </button>
            </div>
          </div>

          <!-- Identity -->
          <section>
            <p class="section-title">Identity</p>
            <dl class="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-sm">
              <dt class="text-gray-500">Platform</dt>
              <dd class="text-gray-200 truncate">{{ device.platform || '—' }}</dd>
              <dt class="text-gray-500">Serial</dt>
              <dd class="text-gray-200 font-mono text-xs">{{ device.serial || '—' }}</dd>
              <dt class="text-gray-500">OS</dt>
              <dd class="text-gray-200 text-xs truncate">{{ device.os_version || '—' }}</dd>
              <dt class="text-gray-500">Uptime</dt>
              <dd class="text-gray-200 text-xs">{{ device.uptime || '—' }}</dd>
              <dt class="text-gray-500">Gateway</dt>
              <dd class="text-gray-200 text-xs font-mono">{{ defaultGateway || '—' }}</dd>
            </dl>
          </section>

          <!-- Neighbors -->
          <section v-if="neighbors.length">
            <p class="section-title">Neighbors ({{ neighbors.length }})</p>
            <div class="flex flex-col gap-1">
              <div
                v-for="nb in neighbors"
                :key="nb.source_intf + nb.target"
                class="flex items-center gap-2 text-xs bg-gray-800/40 rounded px-2 py-1.5"
              >
                <span class="font-mono text-gray-400 shrink-0">{{ abbreviate(nb.source_intf) }}</span>
                <span class="text-gray-600">-></span>
                <span class="text-gray-200 font-medium truncate">{{ nb.target }}</span>
                <span
                  class="text-[10px] font-mono uppercase shrink-0"
                  :class="nb.protocol === 'LLDP' ? 'text-purple-400' : 'text-gray-500'"
                >{{ nb.protocol }}</span>
                <span v-if="nb.target_intf" class="text-gray-500 font-mono ml-auto shrink-0">{{ abbreviate(nb.target_intf) }}</span>
              </div>
            </div>
          </section>

          <!-- LLDP Detail -->
          <section v-if="lldpNeighbors.length">
            <p class="section-title flex items-center gap-2">
              <span>LLDP Detail</span>
              <span class="badge bg-purple-900/30 text-purple-300 text-[10px]">{{ lldpNeighbors.length }}</span>
            </p>
            <div class="flex flex-col gap-2">
              <div
                v-for="nb in lldpNeighbors"
                :key="nb.source_intf + nb.target"
                class="bg-gray-800/40 rounded p-2"
              >
                <div class="flex items-center gap-2 mb-1.5">
                  <span class="font-mono text-purple-300 text-xs font-medium">{{ abbreviate(nb.source_intf) }} -> {{ nb.target }}</span>
                </div>
                <dl class="grid grid-cols-[auto_1fr] gap-x-2 gap-y-0.5 text-xs">
                  <template v-if="nb.capabilities?.length">
                    <dt class="text-gray-500">Capabilities</dt>
                    <dd>
                      <span v-for="cap in nb.capabilities" :key="cap" class="badge bg-purple-900/30 text-purple-300 mr-1 text-[10px]">{{ cap }}</span>
                    </dd>
                  </template>
                  <template v-if="nb.system_description">
                    <dt class="text-gray-500">System</dt>
                    <dd class="text-gray-300 text-xs truncate">{{ nb.system_description }}</dd>
                  </template>
                  <template v-if="nb.port_description">
                    <dt class="text-gray-500">Port Desc</dt>
                    <dd class="text-gray-300 text-xs truncate">{{ nb.port_description }}</dd>
                  </template>
                  <template v-if="nb.med_device_type">
                    <dt class="text-gray-500">MED Type</dt>
                    <dd class="text-gray-300 text-xs">{{ nb.med_device_type }}</dd>
                  </template>
                  <template v-if="nb.med_poe_requested != null">
                    <dt class="text-gray-500">PoE</dt>
                    <dd class="text-gray-300 text-xs font-mono">{{ nb.med_poe_requested }}W req / {{ nb.med_poe_allocated ?? '—' }}W alloc</dd>
                  </template>
                  <template v-if="nb.med_network_policy">
                    <dt class="text-gray-500">Net Policy</dt>
                    <dd class="text-gray-300 text-xs">{{ nb.med_network_policy }}</dd>
                  </template>
                </dl>
              </div>
            </div>
          </section>

          <!-- VLANs -->
          <section v-if="device.vlans?.length">
            <p class="section-title">VLANs ({{ device.vlans.length }})</p>
            <div class="flex flex-wrap gap-1.5">
              <span
                v-for="vlan in device.vlans"
                :key="vlan.vlan_id"
                class="badge bg-gray-700 text-gray-300 gap-1"
                :title="vlan.status"
              >
                <span class="font-mono">{{ vlan.vlan_id }}</span>
                <span v-if="vlan.name" class="text-gray-500">{{ vlan.name }}</span>
              </span>
            </div>
          </section>
        </template>

        <!-- =========== INTERFACES TAB =========== -->
        <template v-if="activeTab === 'interfaces'">
          <section v-if="device.interfaces?.length">
            <DataTableToolbar
              v-model="intf.search.value"
              label="interfaces"
              :copy-status="intf.copyStatus.value"
              :count="intf.sorted.value.length"
              @copy="intf.copyTable()"
              @export="intf.exportCsv(`${hostname}_interfaces.csv`)"
            />
            <!-- Select all / clear bar in Advanced Mode -->
            <div v-if="advancedMode" class="flex items-center gap-2 mb-2 text-xs text-gray-500">
              <button class="hover:text-gray-300" @click="selectAllAccessPorts">Select all access ports</button>
              <span class="text-gray-700">|</span>
              <button class="hover:text-gray-300" @click="clearSelection">Clear</button>
            </div>
            <div class="overflow-x-auto">
              <table v-resizable-columns="'dp-interfaces'" class="w-full text-xs table-fixed">
                <thead>
                  <tr class="text-gray-500 border-b border-gray-700">
                    <th v-if="advancedMode" class="w-6 pb-1 pr-1"></th>
                    <th v-for="col in intfCols" :key="col.key" class="text-left pb-1 pr-2 cursor-pointer select-none hover:text-gray-300" @click="intf.toggleSort(col.key)">{{ col.label }}{{ intf.sortIndicator(col.key) }}</th>
                  </tr>
                </thead>
                <tbody>
                  <tr
                    v-for="row in intf.sorted.value"
                    :key="row.name"
                    class="border-b border-gray-800 hover:bg-gray-700/30"
                    :class="{ 'bg-orange-950/20': selectedPorts.has(row.name) }"
                  >
                    <td v-if="advancedMode" class="py-0.5 pr-1 text-center">
                      <input
                        v-if="isAccessPort(row)"
                        type="checkbox"
                        :checked="selectedPorts.has(row.name)"
                        class="accent-orange-500 cursor-pointer"
                        @change="togglePort(row)"
                      />
                      <span
                        v-else-if="isTrunkPort(row)"
                        class="text-gray-700 cursor-help"
                        title="Trunk ports cannot be changed here"
                      >&mdash;</span>
                      <span
                        v-else-if="isPortChannelMember(row)"
                        class="text-gray-700 cursor-help"
                        :title="`Member of ${isPortChannelMember(row)} — change the port-channel instead`"
                      >&mdash;</span>
                      <span v-else class="text-gray-800">&mdash;</span>
                    </td>
                    <td class="py-0.5 pr-2 font-mono text-gray-300">{{ row.name }}</td>
                    <td class="py-0.5 pr-2">
                      <span :class="intfStatusClass(row.status)" class="badge">{{ row.status || '—' }}</span>
                    </td>
                    <td class="py-0.5 pr-2 text-gray-400">{{ row.vlan || '—' }}</td>
                    <td class="py-0.5 pr-2 text-gray-400">{{ row.speed || '—' }}</td>
                    <td class="py-0.5 pr-2 text-gray-400">{{ row.duplex || '—' }}</td>
                    <td class="py-0.5 text-gray-400 font-mono">{{ row.ip_address || '—' }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
            <!-- Change VLAN action bar -->
            <div
              v-if="advancedMode && selectedPorts.size > 0"
              class="sticky bottom-0 flex items-center justify-between mt-3 px-3 py-2 rounded bg-gray-800 border border-orange-500/30"
            >
              <span class="text-xs text-gray-300">
                {{ selectedPorts.size }} port{{ selectedPorts.size > 1 ? 's' : '' }} selected
              </span>
              <button
                class="btn-primary btn-sm text-xs font-medium"
                @click="$emit('vlan-change', selectedPortObjects)"
              >
                Change VLAN
              </button>
            </div>
          </section>
          <p v-else class="text-xs text-gray-600">No interface data</p>
        </template>

        <!-- =========== ARP TAB =========== -->
        <template v-if="activeTab === 'arp'">
          <section v-if="device.arp_table?.length">
            <DataTableToolbar
              v-model="arp.search.value"
              label="ARP entries"
              :copy-status="arp.copyStatus.value"
              :count="arp.sorted.value.length"
              @copy="arp.copyTable()"
              @export="arp.exportCsv(`${hostname}_arp.csv`)"
            />
            <div class="overflow-x-auto">
              <table v-resizable-columns="'dp-arp'" class="w-full text-xs table-fixed">
                <thead>
                  <tr class="text-gray-500 border-b border-gray-700">
                    <th v-for="col in arpCols" :key="col.key" class="text-left pb-1 pr-2 cursor-pointer select-none hover:text-gray-300" :style="{ width: col.key === 'ip_address' ? '26%' : col.key === 'mac_address' ? '30%' : col.key === 'interface' ? '26%' : '18%' }" @click="arp.toggleSort(col.key)">{{ col.label }}{{ arp.sortIndicator(col.key) }}</th>
                  </tr>
                </thead>
                <tbody>
                  <tr
                    v-for="(entry, i) in arp.sorted.value"
                    :key="i"
                    class="border-b border-gray-800 hover:bg-gray-700/30"
                  >
                    <td class="py-0.5 pr-2 font-mono text-gray-200 truncate" :title="entry.ip_address">{{ entry.ip_address }}</td>
                    <td class="py-0.5 pr-2 font-mono text-gray-400 truncate" :title="entry.mac_address">{{ entry.mac_address }}</td>
                    <td class="py-0.5 pr-2 text-gray-400 truncate" :title="entry.interface">{{ entry.interface }}</td>
                    <td class="py-0.5 truncate">
                      <span
                        class="badge text-xs"
                        :class="entry.entry_type === 'static' ? 'bg-gray-700 text-gray-400' : 'bg-orange-900/30 text-orange-400'"
                      >{{ entry.entry_type }}</span>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </section>
          <p v-else class="text-xs text-gray-600">No ARP data</p>
        </template>

        <!-- =========== MAC TAB =========== -->
        <template v-if="activeTab === 'mac'">
          <section v-if="device.mac_table?.length">
            <DataTableToolbar
              v-model="mac.search.value"
              label="MAC entries"
              :copy-status="mac.copyStatus.value"
              :count="mac.sorted.value.length"
              @copy="mac.copyTable()"
              @export="mac.exportCsv(`${hostname}_mac.csv`)"
            />
            <div class="overflow-x-auto">
              <table v-resizable-columns="'dp-mac'" class="w-full text-xs table-fixed">
                <thead>
                  <tr class="text-gray-500 border-b border-gray-700">
                    <th v-for="col in macCols" :key="col.key" class="text-left pb-1 pr-2 cursor-pointer select-none hover:text-gray-300" :style="{ width: col.key === 'mac_address' ? '30%' : col.key === 'vlan_id' ? '14%' : col.key === 'interface' ? '34%' : '22%' }" @click="mac.toggleSort(col.key)">{{ col.label }}{{ mac.sortIndicator(col.key) }}</th>
                  </tr>
                </thead>
                <tbody>
                  <tr
                    v-for="(entry, i) in mac.sorted.value"
                    :key="i"
                    class="border-b border-gray-800 hover:bg-gray-700/30"
                  >
                    <td class="py-0.5 pr-2 font-mono text-gray-200 truncate" :title="entry.mac_address">{{ entry.mac_address }}</td>
                    <td class="py-0.5 pr-2 text-gray-400 truncate">{{ entry.vlan_id || '—' }}</td>
                    <td class="py-0.5 pr-2 text-gray-400 font-mono truncate" :title="entry.interface">{{ entry.interface }}</td>
                    <td class="py-0.5 truncate">
                      <span
                        class="badge text-xs"
                        :class="entry.entry_type === 'static' ? 'bg-gray-700 text-gray-400' : 'bg-orange-900/30 text-orange-400'"
                      >{{ entry.entry_type }}</span>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </section>
          <p v-else class="text-xs text-gray-600">No MAC address table data</p>
        </template>

        <!-- =========== ROUTES TAB =========== -->
        <template v-if="activeTab === 'routes'">
          <section v-if="device.route_table?.length">
            <DataTableToolbar
              v-model="route.search.value"
              label="routes"
              :copy-status="route.copyStatus.value"
              :count="route.sorted.value.length"
              @copy="route.copyTable()"
              @export="route.exportCsv(`${hostname}_routes.csv`)"
            />
            <div class="overflow-x-auto">
              <table v-resizable-columns="'dp-routes'" class="w-full text-xs table-fixed">
                <thead>
                  <tr class="text-gray-500 border-b border-gray-700">
                    <th v-for="col in routeCols" :key="col.key" class="text-left pb-1 pr-2 cursor-pointer select-none hover:text-gray-300" :style="{ width: col.key === 'destination' ? '24%' : col.key === 'next_hop' ? '24%' : col.key === 'interface' ? '22%' : col.key === 'metric' ? '12%' : '18%' }" @click="route.toggleSort(col.key)">{{ col.label }}{{ route.sortIndicator(col.key) }}</th>
                  </tr>
                </thead>
                <tbody>
                  <tr
                    v-for="(entry, i) in route.sorted.value"
                    :key="i"
                    class="border-b border-gray-800 hover:bg-gray-700/30"
                  >
                    <td class="py-0.5 pr-2 font-mono text-gray-200 truncate" :title="entry.destination">{{ entry.destination }}</td>
                    <td class="py-0.5 pr-2 font-mono text-gray-400 truncate" :title="entry.next_hop || '—'">{{ entry.next_hop || '—' }}</td>
                    <td class="py-0.5 pr-2 text-gray-400 truncate" :title="entry.interface || '—'">{{ entry.interface || '—' }}</td>
                    <td class="py-0.5 pr-2 text-gray-400 font-mono truncate">{{ entry.metric || '—' }}</td>
                    <td class="py-0.5 truncate">
                      <span
                        class="badge text-xs"
                        :class="routeTypeClass(entry.route_type)"
                      >{{ entry.route_type }}</span>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </section>
          <p v-else class="text-xs text-gray-600">No routing table data</p>
        </template>

        <!-- =========== ETHERCHANNEL TAB =========== -->
        <template v-if="activeTab === 'etherchannel'">
          <section v-if="device.etherchannels?.length">
            <div class="flex flex-col gap-3">
              <div
                v-for="ec in device.etherchannels"
                :key="ec.channel_id"
                class="bg-gray-800/40 rounded-lg p-3"
              >
                <div class="flex items-center gap-2 mb-2">
                  <span class="font-mono font-medium text-gray-200 text-sm">{{ ec.port_channel }}</span>
                  <span
                    class="badge text-xs"
                    :class="ec.status === 'up' ? 'bg-orange-900/50 text-orange-400' : 'bg-red-900/50 text-red-400'"
                  >{{ ec.status }}</span>
                  <span v-if="ec.protocol" class="badge text-xs bg-blue-900/30 text-blue-400">{{ ec.protocol }}</span>
                  <span v-if="ec.layer" class="badge text-xs bg-gray-700 text-gray-400">{{ ec.layer }}</span>
                </div>
                <div v-if="ec.members?.length" class="overflow-x-auto">
                  <table v-resizable-columns="'dp-ec-members'" class="w-full text-xs table-fixed">
                    <thead>
                      <tr class="text-gray-500 border-b border-gray-700">
                        <th class="text-left pb-1 pr-2">Member Port</th>
                        <th class="text-left pb-1 pr-2">Flag</th>
                        <th class="text-left pb-1">Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr
                        v-for="(member, i) in ec.members"
                        :key="i"
                        class="border-b border-gray-800 hover:bg-gray-700/30"
                      >
                        <td class="py-0.5 pr-2 font-mono text-gray-300">{{ member.interface }}</td>
                        <td class="py-0.5 pr-2">
                          <span class="badge text-xs" :class="ecMemberClass(member.status)">{{ member.status }}</span>
                        </td>
                        <td class="py-0.5 text-gray-400">{{ member.status_desc || '—' }}</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
                <p v-else class="text-xs text-gray-600">No member ports</p>
              </div>
            </div>
          </section>
          <p v-else class="text-xs text-gray-600">No EtherChannel data</p>
        </template>

        <!-- =========== STP TAB =========== -->
        <template v-if="activeTab === 'stp'">
          <section v-if="device.stp_info?.length">
            <div class="flex flex-col gap-3">
              <div
                v-for="sv in device.stp_info"
                :key="sv.vlan_id"
                class="bg-gray-800/40 rounded-lg p-3"
              >
                <!-- VLAN header -->
                <div class="flex items-center gap-2 mb-2">
                  <span class="font-mono font-medium text-gray-200 text-sm">VLAN {{ sv.vlan_id }}</span>
                  <span v-if="sv.protocol" class="badge text-xs bg-blue-900/30 text-blue-400">{{ sv.protocol }}</span>
                  <span v-if="sv.is_root" class="badge text-xs bg-green-900/50 text-green-400">Root Bridge</span>
                </div>

                <!-- Bridge info -->
                <dl class="grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 text-xs mb-2">
                  <template v-if="!sv.is_root">
                    <dt class="text-gray-500">Root Priority</dt>
                    <dd class="text-gray-300 font-mono">{{ sv.root_priority || '—' }}</dd>
                    <dt class="text-gray-500">Root Address</dt>
                    <dd class="text-gray-300 font-mono">{{ sv.root_address || '—' }}</dd>
                    <dt class="text-gray-500">Cost to Root</dt>
                    <dd class="text-gray-300 font-mono">{{ sv.root_cost || '—' }}</dd>
                  </template>
                  <dt class="text-gray-500">Bridge Priority</dt>
                  <dd class="text-gray-300 font-mono">{{ sv.bridge_priority || '—' }}</dd>
                  <dt class="text-gray-500">Bridge Address</dt>
                  <dd class="text-gray-300 font-mono">{{ sv.bridge_address || '—' }}</dd>
                </dl>

                <!-- Port table -->
                <div v-if="sv.ports?.length" class="overflow-x-auto">
                  <table v-resizable-columns="'dp-stp-ports'" class="w-full text-xs table-fixed">
                    <thead>
                      <tr class="text-gray-500 border-b border-gray-700">
                        <th class="text-left pb-1 pr-2">Interface</th>
                        <th class="text-left pb-1 pr-2">Role</th>
                        <th class="text-left pb-1 pr-2">State</th>
                        <th class="text-left pb-1 pr-2">Cost</th>
                        <th class="text-left pb-1">Type</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr
                        v-for="(port, i) in sv.ports"
                        :key="i"
                        class="border-b border-gray-800 hover:bg-gray-700/30"
                      >
                        <td class="py-0.5 pr-2 font-mono text-gray-300">{{ port.interface }}</td>
                        <td class="py-0.5 pr-2">
                          <span class="badge text-xs" :class="stpRoleClass(port.role)">{{ port.role }}</span>
                        </td>
                        <td class="py-0.5 pr-2">
                          <span class="badge text-xs" :class="stpStateClass(port.state)">{{ port.state }}</span>
                        </td>
                        <td class="py-0.5 pr-2 text-gray-400 font-mono">{{ port.cost || '—' }}</td>
                        <td class="py-0.5 text-gray-400">{{ port.link_type || '—' }}</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          </section>
          <p v-else class="text-xs text-gray-600">No Spanning Tree data</p>
        </template>

        <!-- =========== VXLAN TAB =========== -->
        <template v-if="activeTab === 'vxlan'">
          <template v-if="(device.nve_peers?.length || 0) + (device.vni_mappings?.length || 0) + (device.evpn_neighbors?.length || 0) > 0">

            <!-- NVE Peers -->
            <section v-if="device.nve_peers?.length">
              <p class="section-title">NVE Peers ({{ device.nve_peers.length }})</p>
              <div class="overflow-x-auto">
                <table v-resizable-columns="'dp-nve-peers'" class="w-full text-xs table-fixed">
                  <thead>
                    <tr class="text-gray-500 border-b border-gray-700">
                      <th class="text-left pb-1 pr-2">Peer IP</th>
                      <th class="text-left pb-1 pr-2">State</th>
                      <th class="text-left pb-1 pr-2">Type</th>
                      <th class="text-left pb-1 pr-2">Uptime</th>
                      <th class="text-left pb-1">Router MAC</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr
                      v-for="(peer, i) in device.nve_peers"
                      :key="i"
                      class="border-b border-gray-800 hover:bg-gray-700/30"
                    >
                      <td class="py-0.5 pr-2 font-mono text-gray-200">{{ peer.peer_ip }}</td>
                      <td class="py-0.5 pr-2">
                        <span
                          class="badge text-xs"
                          :class="peer.state === 'Up' ? 'bg-orange-900/50 text-orange-400' : 'bg-red-900/50 text-red-400'"
                        >{{ peer.state }}</span>
                      </td>
                      <td class="py-0.5 pr-2 text-gray-400">{{ peer.learn_type || '—' }}</td>
                      <td class="py-0.5 pr-2 text-gray-400">{{ peer.uptime || '—' }}</td>
                      <td class="py-0.5 font-mono text-gray-400">{{ peer.router_mac || '—' }}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </section>

            <!-- VNI Mappings -->
            <section v-if="device.vni_mappings?.length">
              <p class="section-title">VNI Mappings ({{ device.vni_mappings.length }})</p>
              <div class="overflow-x-auto">
                <table v-resizable-columns="'dp-vni-map'" class="w-full text-xs table-fixed">
                  <thead>
                    <tr class="text-gray-500 border-b border-gray-700">
                      <th class="text-left pb-1 pr-2">VNI</th>
                      <th class="text-left pb-1 pr-2">Type</th>
                      <th class="text-left pb-1 pr-2">State</th>
                      <th class="text-left pb-1 pr-2">Multicast</th>
                      <th class="text-left pb-1">BD/VRF</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr
                      v-for="(vni, i) in device.vni_mappings"
                      :key="i"
                      class="border-b border-gray-800 hover:bg-gray-700/30"
                    >
                      <td class="py-0.5 pr-2 font-mono text-gray-200">{{ vni.vni }}</td>
                      <td class="py-0.5 pr-2">
                        <span
                          class="badge text-xs"
                          :class="vni.vni_type?.startsWith('L2') ? 'bg-blue-900/30 text-blue-400' : 'bg-purple-900/30 text-purple-400'"
                        >{{ vni.vni_type?.split(' ')[0] || '—' }}</span>
                      </td>
                      <td class="py-0.5 pr-2 text-gray-400">{{ vni.state || '—' }}</td>
                      <td class="py-0.5 pr-2 text-gray-400">{{ vni.multicast_group || '—' }}</td>
                      <td class="py-0.5 text-gray-400">{{ vni.bd_vrf || '—' }}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </section>

            <!-- EVPN Neighbors -->
            <section v-if="device.evpn_neighbors?.length">
              <p class="section-title">EVPN Neighbors ({{ device.evpn_neighbors.length }})</p>
              <div class="overflow-x-auto">
                <table v-resizable-columns="'dp-evpn'" class="w-full text-xs table-fixed">
                  <thead>
                    <tr class="text-gray-500 border-b border-gray-700">
                      <th class="text-left pb-1 pr-2">Neighbor</th>
                      <th class="text-left pb-1 pr-2">ASN</th>
                      <th class="text-left pb-1 pr-2">Up/Down</th>
                      <th class="text-left pb-1">Prefixes</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr
                      v-for="(nb, i) in device.evpn_neighbors"
                      :key="i"
                      class="border-b border-gray-800 hover:bg-gray-700/30"
                    >
                      <td class="py-0.5 pr-2 font-mono text-gray-200">{{ nb.neighbor }}</td>
                      <td class="py-0.5 pr-2 text-gray-400">{{ nb.asn || '—' }}</td>
                      <td class="py-0.5 pr-2 text-gray-400">{{ nb.up_down || '—' }}</td>
                      <td class="py-0.5">
                        <span class="badge text-xs bg-orange-900/30 text-orange-400">{{ nb.state_pfx_rcv || '—' }}</span>
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </section>

          </template>
          <p v-else class="text-xs text-gray-600">No VXLAN data</p>
        </template>

        <!-- =========== VLANS TAB =========== -->
        <template v-if="activeTab === 'vlans'">
          <section v-if="device.vlans?.length">
            <DataTableToolbar
              v-model="vlan.search.value"
              label="VLANs"
              :copy-status="vlan.copyStatus.value"
              :count="vlan.sorted.value.length"
              @copy="vlan.copyTable()"
              @export="vlan.exportCsv(`${hostname}_vlans.csv`)"
            />
            <div class="overflow-x-auto">
              <table v-resizable-columns="'dp-vlans'" class="w-full text-xs table-fixed">
                <thead>
                  <tr class="text-gray-500 border-b border-gray-700">
                    <th v-for="col in vlanCols" :key="col.key" class="text-left pb-1 pr-2 cursor-pointer select-none hover:text-gray-300" @click="vlan.toggleSort(col.key)">{{ col.label }}{{ vlan.sortIndicator(col.key) }}</th>
                  </tr>
                </thead>
                <tbody>
                  <tr
                    v-for="row in vlan.sorted.value"
                    :key="row.vlan_id"
                    class="border-b border-gray-800 hover:bg-gray-700/30"
                  >
                    <td class="py-0.5 pr-2 font-mono text-gray-200">{{ row.vlan_id }}</td>
                    <td class="py-0.5 pr-2 text-gray-300">{{ row.name || '—' }}</td>
                    <td class="py-0.5">
                      <span
                        class="badge text-xs"
                        :class="row.status === 'active' ? 'bg-orange-900/50 text-orange-400' : 'bg-gray-700 text-gray-500'"
                      >{{ row.status || '—' }}</span>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </section>
          <p v-else class="text-xs text-gray-600">No VLAN data</p>
        </template>

        <!-- =========== AUDIT TAB (Advanced Mode only) =========== -->
        <template v-if="activeTab === 'audit' && advancedMode">
          <section>
            <p class="text-xs text-gray-500 mb-2">Changes made to this device:</p>
            <AuditLogPanel
              :device-id="device.id"
              @close="activeTab = 'overview'"
              @view-detail="(rec) => $emit('open-audit', rec)"
              @undo="(rec) => $emit('open-audit', rec)"
            />
          </section>
        </template>

      </div>
    </div>
  </Transition>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import ConfigDumpPanel from './ConfigDumpPanel.vue'
import AuditLogPanel from './AuditLogPanel.vue'
import DataTableToolbar from './DataTableToolbar.vue'
import { useTableActions } from '../composables/useTableActions.js'

const props = defineProps({
  device: { type: Object, default: null },
  links: { type: Array, default: () => [] },
  initialTab: { type: String, default: null },
  advancedMode: { type: Boolean, default: false },
})
defineEmits(['close', 'config-dump', 'vlan-change', 'open-audit'])

const activeTab = ref('overview')
const selectedPorts = ref(new Set())

// Reset to Overview (or initialTab) when device selection changes
watch(() => props.device?.id, () => {
  activeTab.value = props.initialTab || 'overview'
  selectedPorts.value = new Set()
})

// --- Table actions for each data tab ---
const hostname = computed(() => props.device?.hostname || props.device?.id || 'device')

const intfCols = [
  { key: 'name', label: 'Port' },
  { key: 'status', label: 'Status' },
  { key: 'vlan', label: 'VLAN' },
  { key: 'speed', label: 'Speed' },
  { key: 'duplex', label: 'Duplex' },
  { key: 'ip_address', label: 'IP Address' },
]
const intf = useTableActions(() => props.device?.interfaces, intfCols)

const arpCols = [
  { key: 'ip_address', label: 'IP Address' },
  { key: 'mac_address', label: 'MAC Address' },
  { key: 'interface', label: 'Interface' },
  { key: 'entry_type', label: 'Type' },
]
const arp = useTableActions(() => props.device?.arp_table, arpCols)

const macCols = [
  { key: 'mac_address', label: 'MAC Address' },
  { key: 'vlan_id', label: 'VLAN' },
  { key: 'interface', label: 'Interface' },
  { key: 'entry_type', label: 'Type' },
]
const mac = useTableActions(() => props.device?.mac_table, macCols)

const routeCols = [
  { key: 'destination', label: 'Destination' },
  { key: 'next_hop', label: 'Next Hop' },
  { key: 'interface', label: 'Interface' },
  { key: 'metric', label: 'Metric' },
  { key: 'route_type', label: 'Type' },
]
const route = useTableActions(() => props.device?.route_table, routeCols)

const vlanCols = [
  { key: 'vlan_id', label: 'VLAN ID' },
  { key: 'name', label: 'Name' },
  { key: 'status', label: 'Status' },
]
const vlan = useTableActions(() => props.device?.vlans, vlanCols)

// Access port detection — only access ports are selectable in Advanced Mode
function isAccessPort(intf) {
  if (!intf) return false
  const name = (intf.name || '').toLowerCase()
  // Exclude management, loopback, VLAN SVI, port-channel, tunnel interfaces
  if (/^(vlan|loopback|lo|tunnel|nve|mgmt|management|port-channel|po)/i.test(name)) return false
  // Exclude trunk ports (vlan field would be 'trunk' or 'trunking')
  const vlan = String(intf.vlan || '').toLowerCase()
  if (vlan === 'trunk' || vlan === 'trunking') return false
  // Must have a numeric VLAN
  if (!/^\d+$/.test(String(intf.vlan || ''))) return false
  return true
}

function isTrunkPort(intf) {
  const vlan = String(intf.vlan || '').toLowerCase()
  return vlan === 'trunk' || vlan === 'trunking'
}

function isPortChannelMember(intf) {
  // Check etherchannel members
  const ecs = props.device?.etherchannels || []
  for (const ec of ecs) {
    if (ec.members?.some(m => m.interface === intf.name)) return ec.port_channel
  }
  return null
}

function togglePort(intf) {
  const newSet = new Set(selectedPorts.value)
  if (newSet.has(intf.name)) {
    newSet.delete(intf.name)
  } else {
    newSet.add(intf.name)
  }
  selectedPorts.value = newSet
}

function selectAllAccessPorts() {
  const all = (props.device?.interfaces || []).filter(isAccessPort).map(i => i.name)
  selectedPorts.value = new Set(all)
}

function clearSelection() {
  selectedPorts.value = new Set()
}

const selectedPortObjects = computed(() => {
  return (props.device?.interfaces || []).filter(i => selectedPorts.value.has(i.name))
})

// Compute neighbors from links for this device
const neighbors = computed(() => {
  if (!props.device || !props.links) return []
  const id = props.device.id
  return props.links
    .filter(l => l.source === id || l.target === id)
    .map(l => l.source === id
      ? { source_intf: l.source_intf, target: l.target, target_intf: l.target_intf, protocol: l.protocol }
      : { source_intf: l.target_intf || '?', target: l.source, target_intf: l.source_intf, protocol: l.protocol }
    )
})

// LLDP neighbors with rich metadata
const lldpNeighbors = computed(() => {
  if (!props.device || !props.links) return []
  const id = props.device.id
  return props.links
    .filter(l => l.protocol === 'LLDP' && (l.source === id || l.target === id))
    .filter(l => l.capabilities?.length || l.med_device_type || l.port_description || l.system_description)
    .map(l => l.source === id
      ? {
          source_intf: l.source_intf, target: l.target, target_intf: l.target_intf,
          capabilities: l.capabilities, system_description: l.system_description,
          port_description: l.port_description, med_device_type: l.med_device_type,
          med_poe_requested: l.med_poe_requested, med_poe_allocated: l.med_poe_allocated,
          med_network_policy: l.med_network_policy,
        }
      : {
          source_intf: l.target_intf || '?', target: l.source, target_intf: l.source_intf,
          capabilities: l.capabilities, system_description: l.system_description,
          port_description: l.port_description, med_device_type: l.med_device_type,
          med_poe_requested: l.med_poe_requested, med_poe_allocated: l.med_poe_allocated,
          med_network_policy: l.med_network_policy,
        }
    )
})

const defaultGateway = computed(() => {
  const routes = props.device?.route_table
  if (!routes) return null
  const def = routes.find(r => r.destination === '0.0.0.0/0')
  return def?.next_hop || null
})

const tabs = computed(() => {
  const d = props.device
  if (!d) return []
  return [
    { key: 'overview', label: 'Overview', count: null },
    { key: 'interfaces', label: 'Interfaces', count: d.interfaces?.length || 0 },
    { key: 'vlans', label: 'VLANs', count: d.vlans?.length || 0 },
    { key: 'arp', label: 'ARP', count: d.arp_table?.length || 0 },
    { key: 'mac', label: 'MAC', count: d.mac_table?.length || 0 },
    { key: 'routes', label: 'Routes', count: d.route_table?.length || 0 },
    { key: 'etherchannel', label: 'EtherChannel', count: d.etherchannels?.length || 0 },
    { key: 'stp', label: 'STP', count: d.stp_info?.length || 0 },
    { key: 'vxlan', label: 'VXLAN', count: (d.nve_peers?.length || 0) + (d.vni_mappings?.length || 0) + (d.evpn_neighbors?.length || 0) },
    { key: 'config', label: 'Config', count: null },
    ...(props.advancedMode ? [{ key: 'audit', label: 'Audit', count: null }] : []),
  ]
})

function abbreviate(name) {
  if (!name) return ''
  return name
    .replace(/Wlan-GigabitEthernet/gi, 'WGi')
    .replace(/AppGigabitEthernet/gi, 'AppGi')
    .replace(/TwentyFiveGigabitEthernet/gi, 'Twe')
    .replace(/TwentyFiveGigE/gi, 'Twe')
    .replace(/HundredGigabitEthernet/gi, 'Hu')
    .replace(/HundredGigE/gi, 'Hu')
    .replace(/FortyGigabitEthernet/gi, 'Fo')
    .replace(/TenGigabitEthernet/gi, 'Te')
    .replace(/GigabitEthernet/gi, 'Gi')
    .replace(/FastEthernet/gi, 'Fa')
    .replace(/Ethernet/gi, 'Et')
    .replace(/Port-channel/gi, 'Po')
    .replace(/Loopback/gi, 'Lo')
    .replace(/Serial/gi, 'Se')
    .replace(/Management/gi, 'Mg')
    .replace(/mgmt/gi, 'Mg')
}

function statusClass(status) {
  const map = {
    ok: 'bg-orange-900/50 text-orange-300 border border-orange-700',
    placeholder: 'bg-gray-700 text-gray-400 border border-gray-600',
    unreachable: 'bg-red-900/50 text-red-300 border border-red-700',
    auth_failed: 'bg-amber-900/50 text-amber-300 border border-amber-700',
    timeout: 'bg-amber-900/50 text-amber-300 border border-amber-700',
    no_cdp_lldp: 'bg-purple-900/50 text-purple-300 border border-purple-700',
  }
  return map[status] || 'bg-gray-700 text-gray-400'
}

function routeTypeClass(type) {
  const map = {
    connected: 'bg-orange-900/30 text-orange-400',
    local: 'bg-gray-700 text-gray-400',
    static: 'bg-blue-900/30 text-blue-400',
    ospf: 'bg-purple-900/30 text-purple-400',
    bgp: 'bg-amber-900/30 text-amber-400',
    eigrp: 'bg-indigo-900/30 text-indigo-400',
    rip: 'bg-orange-900/30 text-orange-400',
  }
  return map[type] || 'bg-gray-700 text-gray-400'
}

function ecMemberClass(flag) {
  const map = {
    P: 'bg-orange-900/50 text-orange-400',
    p: 'bg-orange-900/50 text-orange-400',
    D: 'bg-red-900/50 text-red-400',
    I: 'bg-amber-900/50 text-amber-400',
    s: 'bg-amber-900/50 text-amber-400',
    H: 'bg-blue-900/30 text-blue-400',
    w: 'bg-gray-700 text-gray-400',
    M: 'bg-red-900/50 text-red-400',
  }
  return map[flag] || 'bg-gray-700 text-gray-400'
}

function stpRoleClass(role) {
  const map = {
    Root: 'bg-orange-900/50 text-orange-400',
    Desg: 'bg-blue-900/30 text-blue-400',
    Altn: 'bg-amber-900/50 text-amber-400',
    Back: 'bg-red-900/50 text-red-400',
    Mstr: 'bg-purple-900/30 text-purple-400',
  }
  return map[role] || 'bg-gray-700 text-gray-400'
}

function stpStateClass(state) {
  const map = {
    FWD: 'bg-orange-900/50 text-orange-400',
    BLK: 'bg-red-900/50 text-red-400',
    LRN: 'bg-amber-900/50 text-amber-400',
    LIS: 'bg-amber-900/50 text-amber-400',
    DIS: 'bg-gray-700 text-gray-500',
  }
  return map[state] || 'bg-gray-700 text-gray-400'
}

function intfStatusClass(status) {
  if (!status) return 'bg-gray-700 text-gray-500'
  const s = status.toLowerCase()
  if (s.includes('connected') || s === 'up') return 'bg-orange-900/50 text-orange-400'
  if (s.includes('notconnect') || s === 'down') return 'bg-gray-700 text-gray-500'
  if (s.includes('err') || s.includes('disabled')) return 'bg-red-900/50 text-red-400'
  return 'bg-gray-700 text-gray-400'
}
</script>

