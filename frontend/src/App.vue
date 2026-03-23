<template>
  <div class="h-full flex flex-col bg-gray-950 text-gray-200 overflow-hidden">
    <!-- Skip to main content link (accessibility) -->
    <a href="#main-content" class="skip-link">Skip to main content</a>
    <!-- Header / Top Bar -->
    <header role="banner" class="flex items-center justify-between px-4 bg-gray-900 border-b border-gray-700 shrink-0" style="height: 48px;">
      <div class="flex items-center gap-3">
        <!-- NetScope Logo -->
        <div class="flex items-center gap-2">
          <svg class="w-6 h-6 text-orange-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5"
              d="M9 3H5a2 2 0 00-2 2v4m6-6h10a2 2 0 012 2v4M9 3v18m0 0h10a2 2 0 002-2V9M9 21H5a2 2 0 01-2-2V9m0 0h18"/>
          </svg>
          <span class="text-gray-50 text-lg font-semibold tracking-tight font-display">Net<span class="text-orange-500">Scope</span></span>
        </div>
        <span class="text-gray-600 text-xs">v1.1.0</span>
        <span v-if="session" class="badge bg-gray-800 text-gray-400 font-mono ml-1">
          {{ session.session_id.slice(0, 8) }}
        </span>
        <span
          class="inline-block w-2 h-2 rounded-full ml-1 flex-shrink-0"
          :class="backendOnline ? 'bg-green-400' : 'bg-red-500'"
          :title="backendOnline ? 'Backend connected' : 'Backend unreachable'"
          aria-hidden="true"
        />
        <span class="text-xs" :class="backendOnline ? 'text-green-400' : 'text-red-400'" role="status" aria-live="polite">
          {{ backendOnline ? 'Connected' : 'Disconnected' }}
        </span>
      </div>

      <!-- Search bar -->
      <div class="relative flex-1 max-w-sm mx-4 header-search" ref="searchContainerRef" role="search" aria-label="Search devices">
        <input
          v-model="searchQuery"
          type="text"
          placeholder="Search devices, IPs, MACs, VLANs… (/)"
          aria-label="Search devices, IPs, MACs, VLANs"
          aria-autocomplete="list"
          :aria-expanded="searchResults.length > 0"
          class="w-full bg-gray-800 border border-gray-600 rounded px-3 py-1.5 text-sm text-gray-100 placeholder-gray-500 focus:outline-none focus:border-orange-500 focus:ring-1 focus:ring-orange-500"
          @input="onSearchInput"
          @keydown.escape="closeSearch"
          @keydown.down.prevent="searchNavDown"
          @keydown.up.prevent="searchNavUp"
          @keydown.enter.prevent="searchSelectActive"
          @focus="searchQuery.length >= 2 && fetchSearch()"
        />
        <span v-if="searchLoading" class="absolute right-2 top-1/2 -translate-y-1/2 text-gray-500">
          <svg class="animate-spin w-3 h-3" viewBox="0 0 24 24" fill="none">
            <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"/>
            <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z"/>
          </svg>
        </span>
        <!-- Results dropdown -->
        <div
          v-if="searchResults.length > 0"
          role="listbox"
          aria-label="Search results"
          class="absolute top-full left-0 right-0 mt-1 bg-gray-850 border border-gray-700 rounded shadow-md z-50 max-h-80 overflow-y-auto"
        >
          <div
            v-for="(hit, idx) in searchResults"
            :key="`${hit.session_id}-${hit.device_id}-${hit.result_type}-${idx}`"
            class="flex items-start gap-2 px-3 py-2 cursor-pointer border-b border-gray-700/50 last:border-0"
            :class="idx === searchActiveIdx ? 'bg-gray-700' : 'hover:bg-gray-800'"
            @click="selectSearchResult(hit)"
            @mouseenter="searchActiveIdx = idx"
          >
            <span
              class="shrink-0 mt-0.5 text-xs font-mono px-1 rounded"
              :class="searchTypeClass(hit.result_type)"
            >{{ hit.result_type }}</span>
            <div class="min-w-0 flex-1">
              <div class="text-sm text-gray-100 truncate">{{ hit.label }}</div>
              <div v-if="hit.detail" class="text-xs text-gray-500 truncate font-mono">{{ hit.detail }}</div>
            </div>
          </div>
        </div>
        <div
          v-else-if="searchQuery.length >= 2 && !searchLoading && searchFired"
          class="absolute top-full left-0 right-0 mt-1 bg-gray-850 border border-gray-700 rounded shadow-md z-50 px-3 py-2 text-xs text-gray-500"
        >
          No results for "{{ searchQuery }}"
        </div>
      </div>

      <nav class="flex items-center gap-2 shrink-0 header-toolbar" aria-label="Main toolbar">
        <AdvancedToggle v-model="advancedMode" />
        <ExportBar
          :session-id="session?.session_id || null"
          @export-png="graphRef?.exportPng()"
        />
        <!-- Re-discover button -->
        <button
          v-if="session"
          class="btn-secondary btn-sm"
          :class="{ 'opacity-50 cursor-not-allowed': rediscovering }"
          :title="rediscovering ? 'Re-discovering…' : 'Re-run discovery with same parameters'"
          :aria-label="rediscovering ? 'Re-discovery in progress' : 'Re-run discovery'"
          :aria-busy="rediscovering"
          @click="rediscovering ? null : handleRediscover()"
        >
          {{ rediscovering ? 'Re-discovering…' : '↺ Re-discover' }}
        </button>
        <!-- View Diff button -->
        <button
          v-if="diffIds"
          class="btn-secondary btn-sm text-orange-400 border-orange-800"
          title="View topology diff"
          aria-label="View topology diff"
          @click="openDiffPanel"
        >
          Δ Diff
        </button>
        <!-- History -->
        <button
          class="btn-secondary btn-sm"
          :class="{ 'bg-gray-700 text-gray-100': showSnapshotBrowser }"
          title="Browse snapshot history"
          aria-label="Browse snapshot history"
          :aria-pressed="showSnapshotBrowser"
          @click="showSnapshotBrowser ? (showSnapshotBrowser = false) : openSnapshotBrowser()"
        >
          ⊙ History
        </button>
        <!-- Alerts -->
        <button
          class="btn-secondary btn-sm"
          :class="{ 'bg-gray-700 text-gray-100': showAlertsPanel }"
          title="Change detection alerts"
          aria-label="Change detection alerts"
          :aria-pressed="showAlertsPanel"
          @click="showAlertsPanel ? (showAlertsPanel = false) : openAlertsPanel()"
        >
          ⚑ Alerts
        </button>
        <!-- Path Trace -->
        <button
          v-if="session"
          class="btn-secondary btn-sm"
          :class="{ 'bg-gray-700 text-gray-100': showPathTrace }"
          title="Trace L3 path between devices"
          aria-label="Trace L3 path between devices"
          :aria-pressed="showPathTrace"
          @click="showPathTrace ? (showPathTrace = false) : openPathTrace()"
        >
          ⟶ Path
        </button>
        <!-- STP Root panel -->
        <button
          v-if="session"
          class="btn-secondary btn-sm"
          :class="{ 'bg-gray-700 text-gray-100': showStpPanel }"
          title="STP root bridge per VLAN"
          aria-label="STP root bridge per VLAN"
          :aria-pressed="showStpPanel"
          @click="showStpPanel ? (showStpPanel = false) : openStpPanel()"
        >
          ⊤ STP
        </button>
        <!-- Playbooks (Advanced Mode only) -->
        <button
          v-if="advancedMode"
          class="btn-secondary btn-sm"
          :class="{ 'bg-orange-500/20 text-orange-400 border-orange-500/30': showPlaybookLibrary || showPlaybookRunHistory }"
          title="Configuration playbooks"
          aria-label="Configuration playbooks"
          :aria-pressed="showPlaybookLibrary || showPlaybookRunHistory"
          @click="showPlaybookLibrary ? (showPlaybookLibrary = false) : openPlaybookLibrary()"
        >
          &#x25B6; Playbooks
        </button>
        <!-- Audit Log (Advanced Mode only) -->
        <button
          v-if="advancedMode"
          class="btn-secondary btn-sm"
          :class="{ 'bg-orange-500/20 text-orange-400 border-orange-500/30': showAuditPanel }"
          title="View change audit log"
          aria-label="View change audit log"
          :aria-pressed="showAuditPanel"
          @click="showAuditPanel ? (showAuditPanel = false) : openAuditPanel()"
        >
          Audit
        </button>
        <!-- Saved Views -->
        <button
          v-if="session"
          class="btn-secondary btn-sm"
          :class="{ 'bg-gray-700 text-gray-100': showSavedViews }"
          title="Saved topology views &amp; annotations"
          aria-label="Saved topology views and annotations"
          :aria-pressed="showSavedViews"
          @click="showSavedViews ? (showSavedViews = false) : openSavedViews()"
        >
          ⊟ Views
        </button>
        <!-- Theme Toggle -->
        <button
          class="btn-ghost p-1.5"
          :title="isDark ? 'Switch to light theme' : 'Switch to dark theme'"
          :aria-label="isDark ? 'Switch to light theme' : 'Switch to dark theme'"
          @click="toggleTheme"
        >
          <svg v-if="isDark" class="w-4 h-4 text-gray-400 hover:text-orange-400 transition-colors" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
              d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z"/>
          </svg>
          <svg v-else class="w-4 h-4 text-gray-400 hover:text-orange-400 transition-colors" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
              d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z"/>
          </svg>
        </button>
        <!-- Settings -->
        <button
          class="btn-secondary btn-sm"
          :class="{ 'bg-gray-700 text-gray-100': showSettingsPanel }"
          title="Application settings"
          aria-label="Application settings"
          :aria-pressed="showSettingsPanel"
          @click="showSettingsPanel ? (showSettingsPanel = false) : openSettingsPanel()"
        >
          ⚙ Settings
        </button>
        <!-- Help -->
        <button
          class="btn-secondary btn-sm"
          :class="{ 'bg-gray-700 text-gray-100': showHelpPanel }"
          title="Help and quick reference"
          aria-label="Help and quick reference"
          :aria-pressed="showHelpPanel"
          @click="showHelpPanel ? (showHelpPanel = false) : openHelpPanel()"
        >
          ? Help
        </button>
        <button
          class="btn-ghost p-1.5"
          title="Refresh session"
          aria-label="Refresh session"
          :aria-busy="loading"
          @click="loading ? null : session && reloadSession()"
        >
          <svg class="w-4 h-4" :class="{ 'animate-spin': loading }" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
              d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/>
          </svg>
        </button>
      </nav>
    </header>

    <!-- Progress bar -->
    <div class="relative h-0.5 bg-gray-800 shrink-0 overflow-hidden">
      <div
        v-if="loading"
        class="absolute inset-y-0 left-0 bg-orange-500 transition-all duration-500 ease-out"
        :style="{ width: progress + '%' }"
      />
    </div>

    <!-- Error banner -->
    <div v-if="error" class="flex items-center gap-3 px-4 py-2 bg-red-900/30 border-b border-red-800/50 text-sm text-red-300 shrink-0">
      <span class="shrink-0 text-red-400">⚠</span>
      <span class="flex-1">{{ error }}</span>
      <button class="text-red-500 hover:text-red-300 text-xs" @click="error = null">✕</button>
    </div>

    <!-- Backend disconnect banner -->
    <div v-if="!backendOnline" class="flex items-center gap-3 px-4 py-2 bg-orange-900/20 border-b border-orange-800/40 text-sm text-orange-300 shrink-0">
      <span class="shrink-0">⚠</span>
      <span class="flex-1">Backend unreachable — check if the server is running</span>
    </div>

    <!-- Main layout -->
    <div class="flex-1 flex overflow-hidden">
      <!-- Left sidebar: DiscoverForm -->
      <aside
        class="shrink-0 border-r border-gray-700 overflow-hidden flex flex-col bg-gray-900 sidebar-left transition-[width] duration-200 ease-out relative"
        :class="leftSidebarCollapsed ? 'w-0 border-r-0' : 'w-64'"
        aria-label="Discovery controls"
      >
        <div class="w-64 h-full overflow-y-auto overflow-x-hidden">
          <DiscoverForm
            :loading="loading"
            @discover-requested="handleDiscover"
            @session-selected="loadSession"
          />
        </div>
      </aside>
      <!-- Sidebar collapse/expand toggle -->
      <button
        class="shrink-0 w-5 flex items-center justify-center bg-gray-900 border-r border-gray-700 hover:bg-gray-800 transition-colors cursor-pointer group sidebar-toggle"
        :title="leftSidebarCollapsed ? 'Expand sidebar' : 'Collapse sidebar'"
        :aria-label="leftSidebarCollapsed ? 'Expand sidebar' : 'Collapse sidebar'"
        :aria-expanded="!leftSidebarCollapsed"
        @click="toggleLeftSidebar"
      >
        <svg
          class="w-3.5 h-3.5 text-gray-500 group-hover:text-orange-400 transition-all duration-200"
          :class="{ 'rotate-180': leftSidebarCollapsed }"
          fill="none" stroke="currentColor" viewBox="0 0 24 24" stroke-width="2"
        >
          <path stroke-linecap="round" stroke-linejoin="round" d="M15 19l-7-7 7-7" />
        </svg>
      </button>

      <!-- Center: graph -->
      <main id="main-content" class="flex-1 relative overflow-hidden bg-gray-950" role="main" aria-label="Network topology">
        <TopologyGraph
          ref="graphRef"
          :devices="session?.devices || []"
          :links="session?.links || []"
          :highlight-vlan="vlanFilter"
          :path-node-ids="pathTraceResult?.node_ids || []"
          :path-link-keys="pathTraceResult?.link_keys || []"
          :protocol-filter="protocolFilter"
          @node-selected="selectedDevice = $event"
        />
        <!-- Protocol filter overlay — bottom-right to avoid legend overlap -->
        <div v-if="session" class="absolute bottom-4 right-4 z-10">
          <ProtocolFilter v-model="protocolFilter" />
        </div>

        <!-- Loading overlay -->
        <Transition name="fade">
          <div v-if="loading" class="absolute inset-0 bg-gray-950/70 flex flex-col items-center justify-center z-20 gap-4">
            <svg class="animate-spin h-10 w-10 text-orange-500" viewBox="0 0 24 24" fill="none">
              <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"/>
              <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z"/>
            </svg>
            <div class="text-center">
              <p class="text-orange-400 font-medium font-display">{{ statusMessage }}</p>
              <p class="text-gray-500 text-sm mt-1">{{ statusDetail }}</p>
            </div>
            <!-- Mini progress bar -->
            <div class="w-48 h-1 bg-gray-700 rounded-full overflow-hidden">
              <div
                class="h-full bg-orange-500 rounded-full transition-all duration-500 ease-out"
                :style="{ width: progress + '%' }"
              />
            </div>
            <span class="text-orange-500 text-xs font-mono">{{ Math.round(progress) }}%</span>
          </div>
        </Transition>
      </main>

      <!-- Right sidebar -->
      <aside
        class="border-l border-gray-700 overflow-hidden shrink-0 bg-gray-900 relative sidebar-right"
        :class="{ 'sidebar-right-closed': rightPanelPx === '0px' }"
        :style="{ width: rightPanelPx }"
        aria-label="Detail panel"
      >
        <!-- Resize handle (left edge) -->
        <div
          v-if="rightPanelPx !== '0px'"
          class="absolute top-0 left-0 bottom-0 w-1.5 cursor-ew-resize z-20 group/resize hover:bg-orange-500/30 active:bg-orange-500/50 flex items-center justify-center"
          @mousedown="startSidebarResize"
          @dblclick="resetSidebarWidth"
        >
          <div class="w-0.5 h-8 rounded-full bg-gray-600 opacity-0 group-hover/resize:opacity-100 transition-opacity" />
        </div>
        <ConfigDumpPanel
          v-if="configDumpDevice"
          :device="configDumpDevice"
          :initial-creds="lastCredentials"
          :credential-sets="lastCredentialSets"
          @close="closeConfigDump"
        />
        <VlanMapPanel
          v-else-if="showVlanMap && session"
          :session-id="session.session_id"
          @close="showVlanMap = false; vlanFilter = null"
          @device-selected="selectDeviceById"
          @vlan-filter="vlanFilter = $event"
        />
        <AlertsPanel
          v-else-if="showAlertsPanel"
          @close="showAlertsPanel = false"
        />
        <PathTracePanel
          v-else-if="showPathTrace && session"
          :session-id="session.session_id"
          @close="showPathTrace = false; pathTraceResult = null"
          @device-selected="id => { showPathTrace = false; pathTraceResult = null; selectDeviceById(id) }"
          @path-result="pathTraceResult = $event"
        />
        <StpRootPanel
          v-else-if="showStpPanel && session"
          :devices="session.devices"
          @close="showStpPanel = false"
          @device-selected="id => { showStpPanel = false; selectDeviceById(id) }"
        />
        <SnapshotBrowserPanel
          v-else-if="showSnapshotBrowser"
          :active-id="session?.session_id || null"
          @close="showSnapshotBrowser = false"
          @snapshot-loaded="handleSnapshotLoaded"
          @compare="handleSnapshotCompare"
        />
        <AuditLogPanel
          v-else-if="showAuditPanel && advancedMode"
          @close="showAuditPanel = false"
          @view-detail="handleAuditDetail"
          @undo="handleAuditDetail"
        />
        <PlaybookLibraryPanel
          v-else-if="showPlaybookLibrary && advancedMode"
          ref="playbookLibraryRef"
          @close="showPlaybookLibrary = false"
          @create="openPlaybookEditor(null)"
          @edit="openPlaybookEditor"
          @select="openPlaybookEditor"
          @execute="openPlaybookExecute"
          @import="handlePlaybookImport"
          @show-history="openPlaybookRunHistory"
        />
        <PlaybookRunHistoryPanel
          v-else-if="showPlaybookRunHistory && advancedMode"
          ref="playbookRunHistoryRef"
          @close="showPlaybookRunHistory = false"
          @back="showPlaybookRunHistory = false; showPlaybookLibrary = true"
          @undo="handlePlaybookUndo"
        />
        <DiffPanel
          v-else-if="diffIds && session"
          :current-id="diffIds.current"
          :previous-id="diffIds.previous"
          @close="diffIds = null"
        />
        <SavedViewsPanel
          v-else-if="showSavedViews && session"
          ref="savedViewsPanelRef"
          :session-id="session.session_id"
          :active-view-id="activeViewId"
          @close="showSavedViews = false"
          @load-view="handleLoadView"
          @update-view="handleUpdateView"
          @save-view="handleSaveView"
        />
        <SettingsPanel
          v-else-if="showSettingsPanel"
          @close="showSettingsPanel = false"
        />
        <HelpPanel
          v-else-if="showHelpPanel"
          @close="showHelpPanel = false"
        />
        <DevicePanel
          v-else
          :device="selectedDevice"
          :links="session?.links || []"
          :initial-tab="selectedDeviceTab"
          :advanced-mode="advancedMode"
          @close="selectedDevice = null; selectedDeviceTab = null"
          @config-dump="openConfigDump"
          @vlan-change="handleVlanChangeRequest"
          @open-audit="handleAuditDetail"
        />
      </aside>
    </div>

    <!-- Auth retry modal -->
    <AuthRetryModal
      v-if="showRetryModal && session"
      :failures="pendingAuthFailures"
      :session-id="session.session_id"
      :initial-username="lastCredentials.username"
      :initial-password="lastCredentials.password"
      @session-update="applySessionUpdate"
      @device-succeeded="markDeviceRetried"
      @close="handleRetryClose"
    />

    <!-- Failures panel (all failure types) -->
    <FailuresPanel
      v-if="showFailuresPanel && session"
      :failures="session.failures"
      :session-id="session.session_id"
      :credential-sets="lastCredentialSets"
      :username="lastCredentials.username"
      :password="lastCredentials.password"
      :enable-password="lastCredentials.enable_password"
      @session-update="applySessionUpdate"
      @close="showFailuresPanel = false"
    />

    <!-- Discovery Summary panel -->
    <DiscoverySummaryPanel
      :visible="showSummaryPanel"
      :session-id="session?.session_id || null"
      :devices="session?.devices || []"
      @close="showSummaryPanel = false"
      @session-updated="applySessionUpdate($event)"
    />

    <!-- VLAN Change modal -->
    <VlanChangeModal
      v-if="showVlanChangeModal && vlanChangeDevice"
      :show="showVlanChangeModal"
      :device="vlanChangeDevice"
      :ports="vlanChangePorts"
      :vlans="vlanChangeDevice?.vlans || []"
      :credentials="lastCredentials"
      @close="showVlanChangeModal = false"
      @apply="handleVlanChangeApply"
    />

    <!-- Change Progress modal -->
    <ChangeProgressModal
      :show="showChangeProgress"
      :device-name="vlanChangeDevice?.hostname || vlanChangeDevice?.id || ''"
      :current-step="changeProgressStep"
      :result="changeProgressResult"
      :error-at-step="changeProgressError"
      @close="showChangeProgress = false"
      @view-audit="showChangeProgress = false; openAuditPanel()"
    />

    <!-- Audit Detail modal -->
    <AuditDetailModal
      :show="showAuditDetail"
      :record="auditDetailRecord"
      @close="showAuditDetail = false; auditDetailRecord = null"
      @undo="handleAuditUndo"
    />

    <!-- Playbook Editor modal -->
    <PlaybookEditorModal
      :show="showPlaybookEditor"
      :playbook="editingPlaybook"
      @close="showPlaybookEditor = false; editingPlaybook = null"
      @save="handlePlaybookSave"
      @delete="handlePlaybookDelete"
    />

    <!-- Playbook Execute modal -->
    <PlaybookExecuteModal
      v-if="showPlaybookExecute && executingPlaybook"
      :show="showPlaybookExecute"
      :playbook="executingPlaybook"
      :devices="session?.devices || []"
      :pre-selected-device="playbookPreSelectedDevice"
      :credentials="lastCredentials"
      @close="showPlaybookExecute = false; executingPlaybook = null; playbookPreSelectedDevice = null"
      @done="handlePlaybookExecuteDone"
      @view-history="showPlaybookExecute = false; executingPlaybook = null; openPlaybookRunHistory()"
    />

    <!-- Setup Wizard (first-run) -->
    <SetupWizard
      ref="setupWizardRef"
      :visible="showSetupWizard"
      @discover="handleWizardDiscover"
      @demo-loaded="handleWizardDemoLoaded"
      @skip="handleWizardSkip"
      @finish="handleWizardFinish"
    />

    <!-- Status bar / Bottom drawer -->
    <div
      class="border-t border-gray-700 bg-gray-900 shrink-0 relative"
      :style="{ height: tableOpen ? tableHeight + 'px' : '28px' }"
    >
      <!-- Resize handle (top edge) -->
      <div
        v-if="tableOpen"
        class="absolute top-0 left-0 right-0 h-1 cursor-ns-resize z-20 hover:bg-orange-500/30 active:bg-orange-500/50"
        @mousedown="startTableResize"
      />
      <div class="flex items-center px-3 h-7 select-none border-b border-gray-700/50">
        <span class="text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer hover:text-gray-300 transition-colors" @click="tableOpen = !tableOpen">
          {{ tableOpen ? '▼' : '▶' }}
          <span class="ml-1">Data Tables</span>
        </span>
        <span v-if="session" class="ml-3 text-xs text-gray-600 font-mono">
          {{ session.devices.length }} devices · {{ session.links.length }} links ·
          <button
            v-if="session.failures.length > 0"
            class="text-red-400 hover:text-red-300 cursor-pointer"
            @click.stop="showFailuresPanel = true"
          >{{ session.failures.length }} failures</button>
          <span v-else>0 failures</span>
        </span>
        <span v-if="advancedMode" class="ml-3 text-xs text-orange-400/80 flex items-center gap-1">
          <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
              d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4.5c-.77-.833-2.694-.833-3.464 0L3.34 16.5c-.77.833.192 2.5 1.732 2.5z"/>
          </svg>
          Advanced Mode &mdash; configuration changes enabled
        </span>
        <button
          v-if="session"
          class="ml-auto text-xs px-2 py-0.5 rounded transition-colors"
          :class="showSummaryPanel ? 'bg-orange-500/20 text-orange-400 border border-orange-500/30' : 'text-gray-500 hover:text-gray-300 hover:bg-gray-800'"
          @click.stop="showSummaryPanel = true; showVlanMap = false"
        >
          Summary
        </button>
        <button
          v-if="session"
          class="text-xs px-2 py-0.5 rounded transition-colors ml-1"
          :class="showVlanMap ? 'bg-orange-500/20 text-orange-400 border border-orange-500/30' : 'text-gray-500 hover:text-gray-300 hover:bg-gray-800'"
          @click.stop="openVlanMap"
        >
          VLAN Map
        </button>
      </div>
      <div v-if="tableOpen" class="h-[calc(100%-28px)] overflow-hidden">
        <DeviceTable
          :devices="session?.devices || []"
          :links="session?.links || []"
          :failures="session?.failures || []"
          @device-selected="selectedDevice = $event"
          @config-dump="openConfigDump"
        />
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, nextTick, onMounted, onUnmounted } from 'vue'
import { useTheme } from './composables/useTheme.js'
import DiscoverForm from './components/DiscoverForm.vue'
import TopologyGraph from './components/TopologyGraph.vue'
import DevicePanel from './components/DevicePanel.vue'
import DeviceTable from './components/DeviceTable.vue'
import ExportBar from './components/ExportBar.vue'
import AuthRetryModal from './components/AuthRetryModal.vue'
import ConfigDumpPanel from './components/ConfigDumpPanel.vue'
import VlanMapPanel from './components/VlanMapPanel.vue'
import DiffPanel from './components/DiffPanel.vue'
import SnapshotBrowserPanel from './components/SnapshotBrowserPanel.vue'
import AlertsPanel from './components/AlertsPanel.vue'
import PathTracePanel from './components/PathTracePanel.vue'
import StpRootPanel from './components/StpRootPanel.vue'
import AdvancedToggle from './components/AdvancedToggle.vue'
import VlanChangeModal from './components/VlanChangeModal.vue'
import ChangeProgressModal from './components/ChangeProgressModal.vue'
import AuditLogPanel from './components/AuditLogPanel.vue'
import AuditDetailModal from './components/AuditDetailModal.vue'
import HelpPanel from './components/HelpPanel.vue'
import PlaybookLibraryPanel from './components/PlaybookLibraryPanel.vue'
import PlaybookEditorModal from './components/PlaybookEditorModal.vue'
import PlaybookExecuteModal from './components/PlaybookExecuteModal.vue'
import PlaybookRunHistoryPanel from './components/PlaybookRunHistoryPanel.vue'
import ProtocolFilter from './components/ProtocolFilter.vue'
import SettingsPanel from './components/SettingsPanel.vue'
import SetupWizard from './components/SetupWizard.vue'
import FailuresPanel from './components/FailuresPanel.vue'
import DiscoverySummaryPanel from './components/DiscoverySummaryPanel.vue'
import SavedViewsPanel from './components/SavedViewsPanel.vue'
import { discoverWithProgress, getSession, getSnapshot, rediscover, searchDevices, executeVlanChange, undoAuditRecord, undoPlaybookRun, createPlaybook, updatePlaybook, deletePlaybook, listSessions, createView, updateView as apiUpdateView } from './api.js'

// ---------------------------------------------------------------------------
// Theme
// ---------------------------------------------------------------------------
const { theme, isDark, toggleTheme } = useTheme()

// ---------------------------------------------------------------------------
// Search state
// ---------------------------------------------------------------------------
const searchQuery = ref('')
const searchResults = ref([])
const searchLoading = ref(false)
const searchActiveIdx = ref(-1)
const searchFired = ref(false)
const searchContainerRef = ref(null)
let _searchDebounce = null

function searchTypeClass(type) {
  const map = {
    device: 'bg-orange-900/40 text-orange-300',
    interface: 'bg-gray-700 text-gray-300',
    mac: 'bg-purple-900/40 text-purple-300',
    ip: 'bg-green-900/40 text-green-300',
    vlan: 'bg-yellow-900/40 text-yellow-300',
    route: 'bg-gray-700 text-gray-400',
    lldp: 'bg-purple-900/40 text-purple-300',
  }
  return map[type] || 'bg-gray-700 text-gray-300'
}

async function fetchSearch() {
  if (searchQuery.value.length < 2) {
    searchResults.value = []
    searchFired.value = false
    return
  }
  searchLoading.value = true
  searchFired.value = false
  try {
    const resp = await searchDevices(searchQuery.value, session.value?.session_id || null)
    searchResults.value = resp.results || []
    searchFired.value = true
    searchActiveIdx.value = -1
  } catch {
    searchResults.value = []
    searchFired.value = true
  } finally {
    searchLoading.value = false
  }
}

function onSearchInput() {
  clearTimeout(_searchDebounce)
  if (searchQuery.value.length < 2) {
    searchResults.value = []
    searchFired.value = false
    return
  }
  _searchDebounce = setTimeout(fetchSearch, 250)
}

function closeSearch() {
  searchResults.value = []
  searchFired.value = false
  searchActiveIdx.value = -1
}

function searchNavDown() {
  if (searchResults.value.length === 0) return
  searchActiveIdx.value = Math.min(searchActiveIdx.value + 1, searchResults.value.length - 1)
}

function searchNavUp() {
  if (searchResults.value.length === 0) return
  searchActiveIdx.value = Math.max(searchActiveIdx.value - 1, 0)
}

function searchSelectActive() {
  if (searchActiveIdx.value >= 0 && searchResults.value[searchActiveIdx.value]) {
    selectSearchResult(searchResults.value[searchActiveIdx.value])
  }
}

function selectSearchResult(hit) {
  // Load the session if it differs from the current one
  if (!session.value || session.value.session_id !== hit.session_id) {
    const s = store_list_find(hit.session_id)
    if (s) session.value = s
  }
  // Navigate to the device
  const dev = session.value?.devices?.find(d => d.id === hit.device_id)
  if (dev) {
    selectedDevice.value = dev
    configDumpDevice.value = null
    showVlanMap.value = false
    diffIds.value = null
    // Pass tab hint via a custom event so DevicePanel can focus the right tab
    selectedDeviceTab.value = hit.tab
  }
  closeSearch()
  searchQuery.value = ''
}

// Helper to find a session from the in-memory list (only useful in multi-session scenarios)
function store_list_find(_sessionId) {
  return null  // sessions are loaded via the DiscoverForm; this is a no-op for now
}

// Tab hint for DevicePanel
const selectedDeviceTab = ref(null)

const session = ref(null)
const selectedDevice = ref(null)
const loading = ref(false)
const error = ref(null)
const protocolFilter = ref('all')
const showSetupWizard = ref(false)
const setupWizardRef = ref(null)
const tableOpen = ref(false)
const tableHeight = ref(220)
const sidebarWidth = ref(parseInt(localStorage.getItem('netscope-device-panel-width') || '0', 10))
const leftSidebarCollapsed = ref(localStorage.getItem('netscope-left-sidebar-collapsed') === 'true')
const graphRef = ref(null)
const progress = ref(0)
const statusMessage = ref('Discovering network…')
const statusDetail = ref('Connecting to seed devices')

// ---------------------------------------------------------------------------
// Collapsible left sidebar
// ---------------------------------------------------------------------------
function toggleLeftSidebar() {
  leftSidebarCollapsed.value = !leftSidebarCollapsed.value
  localStorage.setItem('netscope-left-sidebar-collapsed', String(leftSidebarCollapsed.value))
}

function handleViewportResize() {
  if (window.innerWidth < 1024 && !leftSidebarCollapsed.value) {
    leftSidebarCollapsed.value = true
    localStorage.setItem('netscope-left-sidebar-collapsed', 'true')
  }
}

// ---------------------------------------------------------------------------
// Resizable bottom drawer
// ---------------------------------------------------------------------------
function startTableResize(e) {
  e.preventDefault()
  const startY = e.clientY
  const startH = tableHeight.value
  function onMove(ev) {
    tableHeight.value = Math.max(100, Math.min(600, startH + (startY - ev.clientY)))
  }
  function onUp() {
    document.removeEventListener('mousemove', onMove)
    document.removeEventListener('mouseup', onUp)
    document.body.style.cursor = ''
    document.body.style.userSelect = ''
  }
  document.body.style.cursor = 'ns-resize'
  document.body.style.userSelect = 'none'
  document.addEventListener('mousemove', onMove)
  document.addEventListener('mouseup', onUp)
}

// ---------------------------------------------------------------------------
// Resizable right sidebar
// ---------------------------------------------------------------------------
function startSidebarResize(e) {
  e.preventDefault()
  const startX = e.clientX
  const startW = sidebarWidth.value || defaultSidebarWidth()
  function onMove(ev) {
    sidebarWidth.value = Math.max(280, Math.min(800, startW + (startX - ev.clientX)))
  }
  function onUp() {
    document.removeEventListener('mousemove', onMove)
    document.removeEventListener('mouseup', onUp)
    document.body.style.cursor = ''
    document.body.style.userSelect = ''
    if (sidebarWidth.value > 0) {
      localStorage.setItem('netscope-device-panel-width', String(sidebarWidth.value))
    }
  }
  document.body.style.cursor = 'ew-resize'
  document.body.style.userSelect = 'none'
  document.addEventListener('mousemove', onMove)
  document.addEventListener('mouseup', onUp)
}

function resetSidebarWidth() {
  sidebarWidth.value = 0
  localStorage.removeItem('netscope-device-panel-width')
}

// Auth retry modal
const showRetryModal = ref(false)
const showFailuresPanel = ref(false)
const showSummaryPanel = ref(false)
const lastCredentials = ref({ username: '', password: '', enable_password: '' })
const lastCredentialSets = ref([])
const retriedOkDevices = ref(new Set())   // targets successfully authed — never re-prompt

const authFailures = computed(() =>
  (session.value?.failures || []).filter(f => f.reason === 'auth_failed')
)
// Only show failures for devices not yet successfully retried
const pendingAuthFailures = computed(() =>
  authFailures.value.filter(f => !retriedOkDevices.value.has(f.target))
)

// Config dump panel
const configDumpDevice = ref(null)
const showVlanMap = ref(false)
const vlanFilter = ref(null)
const showSnapshotBrowser = ref(false)
const showAlertsPanel = ref(false)
const showPathTrace = ref(false)
const pathTraceResult = ref(null)  // PathTraceResult from backend
const showStpPanel = ref(false)

// Re-discovery and diff
const rediscovering = ref(false)
const diffIds = ref(null)  // { current, previous }

// ---------------------------------------------------------------------------
// Advanced Mode state
// ---------------------------------------------------------------------------
const advancedMode = ref(false)
const showVlanChangeModal = ref(false)
const vlanChangePorts = ref([])       // selected interface objects for VLAN change
const vlanChangeDevice = ref(null)    // device being changed
const showChangeProgress = ref(false)
const changeProgressStep = ref(0)
const changeProgressResult = ref(null)
const changeProgressError = ref(-1)
const showAuditPanel = ref(false)
const showSettingsPanel = ref(false)
const showHelpPanel = ref(false)
const showAuditDetail = ref(false)
const auditDetailRecord = ref(null)

// ---------------------------------------------------------------------------
// Playbook state
// ---------------------------------------------------------------------------
const showPlaybookLibrary = ref(false)
const showPlaybookRunHistory = ref(false)
const showPlaybookEditor = ref(false)
const showPlaybookExecute = ref(false)
const editingPlaybook = ref(null)
const executingPlaybook = ref(null)
const playbookPreSelectedDevice = ref(null)
const playbookLibraryRef = ref(null)
const playbookRunHistoryRef = ref(null)

// ---------------------------------------------------------------------------
// Saved Views state
// ---------------------------------------------------------------------------
const showSavedViews = ref(false)
const activeViewId = ref(null)
const savedViewsPanelRef = ref(null)

// Default width per panel type — user can override by dragging
function defaultSidebarWidth() {
  if (configDumpDevice.value) return 480
  if (showVlanMap.value && session.value) return 520
  if (showAuditPanel.value) return 460
  if (showPlaybookLibrary.value) return 400
  if (showPlaybookRunHistory.value) return 460
  if (showSettingsPanel.value) return 420
  if (showSavedViews.value) return 380
  if (showHelpPanel.value) return 380
  if (showSnapshotBrowser.value) return 380
  if (showAlertsPanel.value) return 420
  if (showPathTrace.value && session.value) return 380
  if (showStpPanel.value && session.value) return 380
  if (diffIds.value && session.value) return 420
  if (selectedDevice.value) return 420
  return 0
}

const rightPanelPx = computed(() => {
  const def = defaultSidebarWidth()
  if (def === 0) return '0px'
  // Use user-resized width if set, otherwise default
  return (sidebarWidth.value > 0 ? sidebarWidth.value : def) + 'px'
})

function openPathTrace() {
  showPathTrace.value = true
  showStpPanel.value = false
  showHelpPanel.value = false
  showSettingsPanel.value = false
  showSavedViews.value = false
  configDumpDevice.value = null
  showVlanMap.value = false
  showSnapshotBrowser.value = false
  showAlertsPanel.value = false
  showPlaybookLibrary.value = false
  showPlaybookRunHistory.value = false
  diffIds.value = null
  selectedDevice.value = null
  sidebarWidth.value = 0
}

function openStpPanel() {
  showStpPanel.value = true
  showPathTrace.value = false
  showHelpPanel.value = false
  showSettingsPanel.value = false
  showSavedViews.value = false
  configDumpDevice.value = null
  showVlanMap.value = false
  showSnapshotBrowser.value = false
  showAlertsPanel.value = false
  showPlaybookLibrary.value = false
  showPlaybookRunHistory.value = false
  diffIds.value = null
  selectedDevice.value = null
  sidebarWidth.value = 0
}

function openConfigDump(device) {
  configDumpDevice.value = device
  selectedDevice.value = null
  showVlanMap.value = false
  sidebarWidth.value = 0
}
function closeConfigDump() {
  configDumpDevice.value = null
  sidebarWidth.value = 0
}
function openVlanMap() {
  showVlanMap.value = true
  showSummaryPanel.value = false
  showStpPanel.value = false
  showHelpPanel.value = false
  showSettingsPanel.value = false
  showSavedViews.value = false
  selectedDevice.value = null
  configDumpDevice.value = null
  vlanFilter.value = null
  diffIds.value = null
  showSnapshotBrowser.value = false
  showPlaybookLibrary.value = false
  showPlaybookRunHistory.value = false
  sidebarWidth.value = 0
}

function openSnapshotBrowser() {
  showSnapshotBrowser.value = true
  showStpPanel.value = false
  showHelpPanel.value = false
  showSettingsPanel.value = false
  showSavedViews.value = false
  selectedDevice.value = null
  configDumpDevice.value = null
  showVlanMap.value = false
  showAlertsPanel.value = false
  showPlaybookLibrary.value = false
  showPlaybookRunHistory.value = false
  diffIds.value = null
  sidebarWidth.value = 0
}

function openAlertsPanel() {
  showAlertsPanel.value = true
  showStpPanel.value = false
  showHelpPanel.value = false
  showSettingsPanel.value = false
  showSavedViews.value = false
  selectedDevice.value = null
  configDumpDevice.value = null
  showVlanMap.value = false
  showSnapshotBrowser.value = false
  showPlaybookLibrary.value = false
  showPlaybookRunHistory.value = false
  diffIds.value = null
  sidebarWidth.value = 0
}

function openSettingsPanel() {
  showSettingsPanel.value = true
  showStpPanel.value = false
  showPathTrace.value = false
  showHelpPanel.value = false
  showSavedViews.value = false
  selectedDevice.value = null
  configDumpDevice.value = null
  showVlanMap.value = false
  showSnapshotBrowser.value = false
  showAlertsPanel.value = false
  showPlaybookLibrary.value = false
  showPlaybookRunHistory.value = false
  showAuditPanel.value = false
  diffIds.value = null
  sidebarWidth.value = 0
}

// ---------------------------------------------------------------------------
// Saved Views handlers
// ---------------------------------------------------------------------------
function openSavedViews() {
  showSavedViews.value = true
  showStpPanel.value = false
  showPathTrace.value = false
  showHelpPanel.value = false
  showSettingsPanel.value = false
  selectedDevice.value = null
  configDumpDevice.value = null
  showVlanMap.value = false
  showSnapshotBrowser.value = false
  showAlertsPanel.value = false
  showPlaybookLibrary.value = false
  showPlaybookRunHistory.value = false
  showAuditPanel.value = false
  diffIds.value = null
  sidebarWidth.value = 0
}

async function handleSaveView({ name, is_default }) {
  if (!session.value || !graphRef.value) return
  const layout = graphRef.value.getLayout()
  if (!layout) return
  try {
    const view = await createView({
      name,
      is_default,
      session_id: session.value.session_id,
      zoom: layout.zoom,
      pan_x: layout.pan_x,
      pan_y: layout.pan_y,
      node_positions: layout.node_positions,
      protocol_filter: protocolFilter.value,
      vlan_filter: vlanFilter.value,
    })
    activeViewId.value = view.view_id
  } catch (e) {
    error.value = 'Failed to save view: ' + e.message
  }
}

async function handleLoadView(view) {
  if (!graphRef.value) return
  activeViewId.value = view.view_id
  // Restore layout (zoom, pan, node positions)
  graphRef.value.restoreLayout({
    zoom: view.zoom,
    pan_x: view.pan_x,
    pan_y: view.pan_y,
    node_positions: view.node_positions,
  })
  // Restore filters
  if (view.protocol_filter) protocolFilter.value = view.protocol_filter
  if (view.vlan_filter !== undefined) vlanFilter.value = view.vlan_filter
}

async function handleUpdateView(view) {
  if (!session.value || !graphRef.value) return
  const layout = graphRef.value.getLayout()
  if (!layout) return
  try {
    await apiUpdateView(view.view_id, {
      name: view.name,
      description: view.description || '',
      is_default: view.is_default,
      session_id: session.value.session_id,
      zoom: layout.zoom,
      pan_x: layout.pan_x,
      pan_y: layout.pan_y,
      node_positions: layout.node_positions,
      protocol_filter: protocolFilter.value,
      vlan_filter: vlanFilter.value,
      annotations: view.annotations || [],
    })
    activeViewId.value = view.view_id
    // Refresh the panel
    savedViewsPanelRef.value?.fetchViews()
  } catch (e) {
    error.value = 'Failed to update view: ' + e.message
  }
}

// ---------------------------------------------------------------------------
// Advanced Mode handlers
// ---------------------------------------------------------------------------
function handleVlanChangeRequest(ports) {
  vlanChangePorts.value = ports
  vlanChangeDevice.value = selectedDevice.value
  showVlanChangeModal.value = true
}

async function handleVlanChangeApply(payload) {
  showVlanChangeModal.value = false
  showChangeProgress.value = true
  changeProgressStep.value = 0
  changeProgressResult.value = null
  changeProgressError.value = -1

  try {
    // Simulate step progression (backend sends result, we animate steps)
    changeProgressStep.value = 0
    const stepDelay = () => new Promise(r => setTimeout(r, 600))

    // Step 1: Connecting
    await stepDelay()
    changeProgressStep.value = 1

    // Step 2: Pre-check
    await stepDelay()
    changeProgressStep.value = 2

    // Step 3: Applying — fire the actual API call
    const result = await executeVlanChange(payload)

    // Check if backend returned a failure (e.g. connection error, validation)
    if (result.status === 'failed') {
      changeProgressError.value = changeProgressStep.value
      changeProgressResult.value = result
    } else {
      // Step 4: Post-check done
      changeProgressStep.value = 4
      changeProgressResult.value = result
    }
  } catch (e) {
    changeProgressError.value = changeProgressStep.value
    changeProgressResult.value = {
      status: 'failed',
      error: e.message || 'Change execution failed',
    }
  }
}

function openHelpPanel() {
  showHelpPanel.value = true
  showStpPanel.value = false
  showPathTrace.value = false
  showSettingsPanel.value = false
  showSavedViews.value = false
  selectedDevice.value = null
  configDumpDevice.value = null
  showVlanMap.value = false
  showSnapshotBrowser.value = false
  showAlertsPanel.value = false
  showAuditPanel.value = false
  showPlaybookLibrary.value = false
  showPlaybookRunHistory.value = false
  diffIds.value = null
  sidebarWidth.value = 0
}

function openAuditPanel() {
  showAuditPanel.value = true
  showStpPanel.value = false
  showHelpPanel.value = false
  showSettingsPanel.value = false
  showSavedViews.value = false
  selectedDevice.value = null
  configDumpDevice.value = null
  showVlanMap.value = false
  showSnapshotBrowser.value = false
  showAlertsPanel.value = false
  showPathTrace.value = false
  showPlaybookLibrary.value = false
  showPlaybookRunHistory.value = false
  diffIds.value = null
  sidebarWidth.value = 0
}

function handleAuditDetail(rec) {
  auditDetailRecord.value = rec
  showAuditDetail.value = true
}

async function handleAuditUndo(rec) {
  showAuditDetail.value = false
  auditDetailRecord.value = null
  showChangeProgress.value = true
  changeProgressStep.value = 0
  changeProgressResult.value = null
  changeProgressError.value = -1
  try {
    await new Promise(r => setTimeout(r, 400))
    changeProgressStep.value = 1
    const result = await undoAuditRecord(rec.id, {
      username: lastCredentials.value.username,
      password: lastCredentials.value.password,
      enable_password: lastCredentials.value.enable_password || null,
    })
    changeProgressStep.value = 4
    changeProgressResult.value = result
  } catch (e) {
    changeProgressError.value = changeProgressStep.value
    changeProgressResult.value = { status: 'failed', error: e.message || 'Undo failed' }
  }
}

// ---------------------------------------------------------------------------
// Playbook handlers
// ---------------------------------------------------------------------------
function openPlaybookLibrary() {
  showPlaybookLibrary.value = true
  showPlaybookRunHistory.value = false
  showStpPanel.value = false
  showHelpPanel.value = false
  showPathTrace.value = false
  showSavedViews.value = false
  selectedDevice.value = null
  configDumpDevice.value = null
  showVlanMap.value = false
  showSnapshotBrowser.value = false
  showAlertsPanel.value = false
  showAuditPanel.value = false
  diffIds.value = null
  sidebarWidth.value = 0
}

function openPlaybookRunHistory() {
  showPlaybookRunHistory.value = true
  showPlaybookLibrary.value = false
  showStpPanel.value = false
  showHelpPanel.value = false
  showPathTrace.value = false
  showSavedViews.value = false
  selectedDevice.value = null
  configDumpDevice.value = null
  showVlanMap.value = false
  showSnapshotBrowser.value = false
  showAlertsPanel.value = false
  showAuditPanel.value = false
  diffIds.value = null
  sidebarWidth.value = 0
}

function openPlaybookEditor(pb) {
  editingPlaybook.value = pb || null
  showPlaybookEditor.value = true
}

function openPlaybookExecute(pb, device = null) {
  executingPlaybook.value = pb
  playbookPreSelectedDevice.value = device
  showPlaybookExecute.value = true
}

async function handlePlaybookSave(payload) {
  try {
    if (payload.id) {
      await updatePlaybook(payload.id, payload)
    } else {
      await createPlaybook(payload)
    }
    showPlaybookEditor.value = false
    editingPlaybook.value = null
    // Refresh library if visible
    if (showPlaybookLibrary.value && playbookLibraryRef.value) {
      playbookLibraryRef.value.refresh()
    }
  } catch (e) {
    error.value = e.message || 'Failed to save playbook'
  }
}

async function handlePlaybookDelete(pb) {
  if (!pb?.id) return
  try {
    await deletePlaybook(pb.id)
    showPlaybookEditor.value = false
    editingPlaybook.value = null
    if (showPlaybookLibrary.value && playbookLibraryRef.value) {
      playbookLibraryRef.value.refresh()
    }
  } catch (e) {
    error.value = e.message || 'Failed to delete playbook'
  }
}

function handlePlaybookImport() {
  // Open editor with YAML tab active (empty playbook)
  editingPlaybook.value = null
  showPlaybookEditor.value = true
}

function handlePlaybookExecuteDone() {
  // Refresh run history if visible
  if (showPlaybookRunHistory.value && playbookRunHistoryRef.value) {
    playbookRunHistoryRef.value.refresh()
  }
}

async function handlePlaybookUndo(run) {
  showChangeProgress.value = true
  changeProgressStep.value = 0
  changeProgressResult.value = null
  changeProgressError.value = -1
  try {
    await new Promise(r => setTimeout(r, 400))
    changeProgressStep.value = 1
    const result = await undoPlaybookRun(run.id, {
      username: lastCredentials.value.username,
      password: lastCredentials.value.password,
      enable_password: lastCredentials.value.enable_password || null,
    })
    changeProgressStep.value = 4
    changeProgressResult.value = result
    if (showPlaybookRunHistory.value && playbookRunHistoryRef.value) {
      playbookRunHistoryRef.value.refresh()
    }
  } catch (e) {
    changeProgressError.value = changeProgressStep.value
    changeProgressResult.value = { status: 'failed', error: e.message || 'Undo failed' }
  }
}

async function handleSnapshotLoaded(snapshotId) {
  loading.value = true
  error.value = null
  try {
    session.value = await getSnapshot(snapshotId)
    tableOpen.value = true
    showSnapshotBrowser.value = false
  } catch (e) {
    error.value = e.message || 'Failed to load snapshot'
  } finally {
    loading.value = false
  }
}

function handleSnapshotCompare({ current, previous }) {
  diffIds.value = { current, previous }
  showSnapshotBrowser.value = false
}

function openDiffPanel() {
  selectedDevice.value = null
  configDumpDevice.value = null
  showVlanMap.value = false
}

async function handleRediscover() {
  if (!session.value || rediscovering.value) return
  const previousId = session.value.session_id
  rediscovering.value = true
  error.value = null
  try {
    const newSession = await rediscover(previousId)
    diffIds.value = { current: newSession.session_id, previous: previousId }
    session.value = newSession
    // Automatically open the diff panel
    openDiffPanel()
  } catch (e) {
    error.value = e.message || 'Re-discovery failed'
  } finally {
    rediscovering.value = false
  }
}
function selectDeviceById(deviceId) {
  showVlanMap.value = false
  const dev = session.value?.devices?.find(d => d.id === deviceId)
  if (dev) selectedDevice.value = dev
}

// Progress messages cycled while waiting
const STAGES = [
  { pct: 8,  msg: 'Discovering network…',  detail: 'Connecting to seed devices' },
  { pct: 20, msg: 'Gathering device info…', detail: 'Running show version' },
  { pct: 38, msg: 'Collecting neighbors…',  detail: 'Running show cdp neighbors detail' },
  { pct: 55, msg: 'Walking topology…',      detail: 'Following CDP/LLDP links' },
  { pct: 70, msg: 'Collecting interfaces…', detail: 'Running show interfaces status' },
  { pct: 82, msg: 'Gathering VLANs…',       detail: 'Running show vlan brief' },
  { pct: 91, msg: 'Building topology…',     detail: 'Normalizing links and devices' },
  { pct: 96, msg: 'Almost done…',           detail: 'Saving session' },
]

let progressTimer = null
let stageIdx = 0

function _startProgress() {
  progress.value = 0
  stageIdx = 0
  statusMessage.value = STAGES[0].msg
  statusDetail.value = STAGES[0].detail

  progressTimer = setInterval(() => {
    if (stageIdx < STAGES.length - 1) {
      stageIdx++
      const stage = STAGES[stageIdx]
      progress.value = stage.pct
      statusMessage.value = stage.msg
      statusDetail.value = stage.detail
    }
  }, 1800)
}

function _finishProgress() {
  clearInterval(progressTimer)
  progress.value = 100
  setTimeout(() => { progress.value = 0 }, 600)
}

// ---------------------------------------------------------------------------
// Setup Wizard handlers
// ---------------------------------------------------------------------------
async function handleWizardDiscover(payload) {
  showSetupWizard.value = false
  await handleDiscover(payload)
  // After discovery completes, show wizard success step
  if (session.value && session.value.devices.length > 0) {
    showSetupWizard.value = true
    nextTick(() => setupWizardRef.value?.showSuccess())
  }
}

function handleWizardDemoLoaded(result) {
  session.value = result
  tableOpen.value = true
  showSetupWizard.value = true
  nextTick(() => setupWizardRef.value?.showSuccess())
}

function handleWizardSkip() {
  showSetupWizard.value = false
}

function handleWizardFinish() {
  showSetupWizard.value = false
}

async function handleDiscover(payload) {
  loading.value = true
  error.value = null
  selectedDevice.value = null
  showRetryModal.value = false
  showFailuresPanel.value = false
  retriedOkDevices.value = new Set()   // reset on fresh discovery
  lastCredentials.value = {
    username: payload.credential_sets?.[0]?.username || payload.username || '',
    password: payload.credential_sets?.[0]?.password || payload.password || '',
    enable_password: payload.credential_sets?.[0]?.enable_password || '',
  }
  lastCredentialSets.value = payload.credential_sets || []

  // Use SSE progress stream for real-time updates
  progress.value = 0
  statusMessage.value = 'Discovering network…'
  statusDetail.value = 'Connecting to seed devices'

  try {
    const result = await discoverWithProgress(payload, (p) => {
      // Real-time progress from backend
      const total = p.total_queued || 1
      const done = p.discovered + p.failed
      if (p.phase === 'finalizing') {
        progress.value = 92
        statusMessage.value = 'Building topology…'
        statusDetail.value = 'Normalizing links and devices'
      } else if (p.phase === 'done') {
        progress.value = 100
      } else {
        progress.value = Math.min(90, Math.round((done / total) * 90))
        statusMessage.value = `Discovered ${p.discovered} device${p.discovered !== 1 ? 's' : ''}…`
        statusDetail.value = p.failed > 0
          ? `${p.in_progress} in progress, ${p.failed} failed`
          : `${p.in_progress} in progress`
        if (p.latest_device && p.latest_status === 'ok') {
          statusDetail.value += ` — ${p.latest_device}`
        }
      }
    })
    session.value = result
    tableOpen.value = true

    // Show auth retry modal for auth failures
    if (result.failures.some(f => f.reason === 'auth_failed')) {
      showRetryModal.value = true
    }
    // Show failures panel if non-auth failures exist
    const nonAuthFailures = result.failures.filter(f => f.reason !== 'auth_failed')
    if (nonAuthFailures.length > 0 && !result.failures.some(f => f.reason === 'auth_failed')) {
      showFailuresPanel.value = true
    }
  } catch (e) {
    error.value = e.message || 'Discovery failed'
  } finally {
    progress.value = 100
    setTimeout(() => { progress.value = 0 }, 600)
    loading.value = false
  }
}

function applySessionUpdate(result) {
  session.value = result
}

function markDeviceRetried(target) {
  retriedOkDevices.value = new Set([...retriedOkDevices.value, target])
}

async function handleRetryClose(reason) {
  showRetryModal.value = false
  if (reason === 'done') {
    if (pendingAuthFailures.value.length > 0) {
      // BFS found new auth-failed devices — reopen for them
      nextTick(() => { showRetryModal.value = true })
    } else {
      // All done — silently reload from server to get the definitive merged state
      if (session.value) {
        getSession(session.value.session_id)
          .then(s => { session.value = s })
          .catch(() => {})
      }
    }
  }
}

function loadSession(s) {
  session.value = s
  selectedDevice.value = null
  tableOpen.value = true
}

async function reloadSession() {
  if (!session.value) return
  loading.value = true
  try {
    session.value = await getSession(session.value.session_id)
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

// ---------------------------------------------------------------------------
// Backend health polling
// ---------------------------------------------------------------------------
const backendOnline = ref(true)
let healthTimer = null

async function checkHealth() {
  if (loading.value) return  // skip while discovery is running
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), 5000)
  try {
    const res = await fetch('/health', { signal: controller.signal })
    backendOnline.value = res.ok
  } catch {
    backendOnline.value = false
  } finally {
    clearTimeout(timeout)
  }
}

function onDocumentClick(e) {
  if (searchContainerRef.value && !searchContainerRef.value.contains(e.target)) {
    closeSearch()
  }
}

onMounted(async () => {
  checkHealth()
  healthTimer = setInterval(checkHealth, 15000)
  document.addEventListener('click', onDocumentClick)
  window.addEventListener('resize', handleViewportResize)
  // Auto-collapse on narrow viewports at startup
  handleViewportResize()
  // First-run detection: show wizard if no previous sessions exist
  try {
    const sessions = await listSessions()
    if (!sessions || sessions.length === 0) {
      showSetupWizard.value = true
    }
  } catch {
    // Backend may not be up yet — show wizard anyway for fresh installs
    showSetupWizard.value = true
  }
})

onUnmounted(() => {
  clearInterval(progressTimer)
  clearInterval(healthTimer)
  document.removeEventListener('click', onDocumentClick)
  window.removeEventListener('resize', handleViewportResize)
})
</script>

<style scoped>
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s ease;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
/* Ensure gray-850 is available as inline style fallback */
.bg-gray-850 {
  background-color: #18181f;
}
</style>
