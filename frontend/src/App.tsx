import { useEffect, useMemo, useRef, useState } from 'react'
import {
  Activity, AlertTriangle, ArrowUpRight, Bell, Check, ChevronDown, ClipboardList, Cloud, CloudOff,
  Eye, FileText, Filter, MapPin, Menu, Radio, Search, Settings2, Shield, Siren, Users, Volume2, VolumeX, X,
} from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'
import { MapContainer, Circle, CircleMarker, Popup, TileLayer } from 'react-leaflet'
import { Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api, apiUrl, createMockIncident, makeMockIncidents, mockCameras, useMock } from './api/client'
import { playIncidentBuzzer, unlockAudioAlerts } from './api/alertSound'
import { useIncidentsSocket } from './hooks/useIncidentsSocket'
import { useSentinelStore } from './store/useSentinelStore'
import type { Camera, Incident, IncidentStatus, IncidentType, Page, Stats } from './types/contracts'
import './styles.css'

const nav: Array<{ name: Page; icon: typeof Activity }> = [
  { name: 'Live Ops', icon: Activity }, { name: 'Map', icon: MapPin }, { name: 'Committee Inbox', icon: Users }, { name: 'Incidents', icon: FileText },
  { name: 'Analytics', icon: ArrowUpRight }, { name: 'Settings', icon: Settings2 },
]
const typeLabel: Record<IncidentType, string> = {
  physical_altercation: 'Physical altercation', fall_collapse: 'Fall / collapse', abnormal_crowd_movement: 'Abnormal crowd movement',
}
const typeIcon: Record<IncidentType, typeof Activity> = {
  physical_altercation: Siren, fall_collapse: AlertTriangle, abnormal_crowd_movement: Activity,
}
const colorType = { physical_altercation: '#ef5b65', fall_collapse: '#f4b45f', abnormal_crowd_movement: '#45d4c1' }
const committeeFor: Record<IncidentType, string> = {
  physical_altercation: 'Security Response Committee',
  fall_collapse: 'Medical Response Committee',
  abnormal_crowd_movement: 'Crowd Safety Committee',
}

function relativeTime(value: string) {
  const seconds = Math.max(0, Math.floor((Date.now() - new Date(value).getTime()) / 1000))
  if (seconds < 60) return `${seconds}s ago`
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`
  return `${Math.floor(seconds / 3600)}h ago`
}

function mockStats(incidents: Incident[]): Stats {
  const now = new Date()
  const hours = Array.from({ length: 24 }, (_, index) => {
    const at = new Date(now.getTime() - (23 - index) * 3_600_000)
    return { hour: `${String(at.getHours()).padStart(2, '0')}:00`, count: incidents.filter((item) => new Date(item.timestamp).getHours() === at.getHours()).length }
  })
  const by_type = { physical_altercation: 0, fall_collapse: 0, abnormal_crowd_movement: 0 }
  const by_status = { new: 0, acknowledged: 0, resolved: 0 }
  incidents.forEach((item) => { by_type[item.type]++; by_status[item.status]++ })
  return { total: incidents.length, by_type, by_status, by_hour: hours, by_camera: mockCameras.map((camera) => ({ camera_id: camera.id, name: camera.name, count: incidents.filter((item) => item.camera_id === camera.id).length })) }
}

export default function App() {
  const { incidents, cameras, stats, page, selected, connected, mockMode, sound, toast, setData, upsert, setPage, select, setConnected, setMockMode, setSound, setToast } = useSentinelStore()
  const [loading, setLoading] = useState(true)
  const [apiError, setApiError] = useState('')
  const [clock, setClock] = useState(new Date())
  const [demoMode, setDemoMode] = useState(true)
  const [simulateOpen, setSimulateOpen] = useState(false)
  const [mobileNav, setMobileNav] = useState(false)
  useIncidentsSocket()

  useEffect(() => {
    const timer = window.setInterval(() => setClock(new Date()), 1000)
    return () => window.clearInterval(timer)
  }, [])

  useEffect(() => {
    const unlock = () => unlockAudioAlerts()
    window.addEventListener('pointerdown', unlock, { once: true })
    return () => window.removeEventListener('pointerdown', unlock)
  }, [])

  useEffect(() => {
    let active = true
    const load = async () => {
      setLoading(true)
      if (useMock) {
        const initial = makeMockIncidents()
        if (active) { setData(initial, mockCameras, mockStats(initial)); setMockMode(true); setLoading(false) }
        return
      }
      try {
        const [cameraData, incidentData, statsData] = await Promise.all([api.cameras(), api.incidents(), api.stats()])
        if (active) { setData(incidentData, cameraData, statsData); setConnected(true); setApiError('') }
      } catch (error) {
        if (active) {
          setApiError(error instanceof Error ? error.message : 'API unavailable')
          setConnected(false)
          setMockMode(false)
        }
      } finally { if (active) setLoading(false) }
    }
    void load()
    return () => { active = false }
  }, [setConnected, setData, setMockMode])

  useEffect(() => {
    if (!connected || useMock || incidents.length > 0) return
    let active = true
    void Promise.all([api.cameras(), api.incidents(), api.stats()]).then(([cameraData, incidentData, statsData]) => {
      if (active) { setData(incidentData, cameraData, statsData); setApiError('') }
    }).catch((error: unknown) => {
      if (active) setApiError(error instanceof Error ? error.message : 'API unavailable')
    })
    return () => { active = false }
  }, [connected, incidents.length, setData])

  const activeCount = incidents.filter((item) => item.status === 'new' && Date.now() - new Date(item.timestamp).getTime() < 24 * 60 * 60 * 1000).length
  const acknowledgedCount = incidents.filter((item) => item.status === 'acknowledged').length
  const resolvedToday = incidents.filter((item) => item.status === 'resolved' && new Date(item.timestamp).toDateString() === new Date().toDateString()).length
  const avgConfidence = incidents.length ? incidents.reduce((sum, item) => sum + item.confidence, 0) / incidents.length : 0
  const openIncident = (incident: Incident) => select(incident)
  const simulate = async (type: IncidentType, cameraId: string) => {
    setSimulateOpen(false)
    try {
      const localDemo = mockMode || useMock
      const incident = localDemo ? createMockIncident(type, cameraId) : await api.simulate(type, cameraId)
      upsert(incident); select(incident); setPage('Live Ops')
      if (incident.severity === 'high') {
        if (localDemo) playIncidentBuzzer(sound)
        setToast(incident)
        window.setTimeout(() => setToast(null), 5000)
      }
    } catch (error) { setApiError(error instanceof Error ? error.message : 'Could not simulate incident') }
  }
  const patchIncident = async (incident: Incident, body: { status?: IncidentStatus; notes?: string }) => {
    const optimistic = { ...incident, ...body }
    upsert(optimistic)
    select(optimistic)
    if (mockMode || useMock) return
    try {
      if (body.status === 'resolved' && incident.status === 'new') {
        await api.update(incident.id, { status: 'acknowledged' })
      }
      const confirmed = await api.update(incident.id, body)
      upsert(confirmed)
      select(confirmed)
    } catch (error) {
      upsert(incident)
      select(incident)
      setApiError(error instanceof Error ? error.message : 'Could not update incident')
    }
  }
  const resolveForCommittee = async (incident: Incident) => {
    await patchIncident(incident, { status: 'resolved' })
  }

  return <div className="app-shell">
    <div className="ambient-grid" aria-hidden="true" />
    <header className="topbar">
      <button className="mobile-menu icon-button" title="Toggle navigation" onClick={() => setMobileNav(!mobileNav)}><Menu size={18} /></button>
      <div className="brand-mark"><span className="brand-icon"><Shield size={20} /><Eye size={10} /></span><span className="brand-name">SENTINEL<span>AI</span></span><span className="brand-divider" /><span className="brand-context">OPERATIONS</span></div>
      <div className="top-status">
        <span className={`connection ${connected ? 'is-online' : mockMode ? 'is-mock' : ''}`}><i />{mockMode ? 'DEMO DATA' : connected ? 'API CONNECTED' : 'API OFFLINE'}</span>
        <span className="top-divider" />
        <span className="camera-count"><Radio size={14} /> {cameras.filter((camera) => camera.status === 'online').length || (mockMode ? 4 : 0)} <small>CAMERAS</small></span>
      </div>
      <div className="top-actions">
        <span className="clock"><span>{clock.toLocaleTimeString([], { hour12: false })}</span><small>LOCAL TIME</small></span>
        <button className={`mode-toggle ${demoMode ? 'active' : ''}`} onClick={() => setDemoMode(!demoMode)}><span className="toggle-track"><i /></span><span>DEMO MODE</span></button>
        <button className="icon-button sound-button" title={sound ? 'Mute alert sound' : 'Enable alert sound'} onClick={() => { if (!sound) unlockAudioAlerts(); setSound(!sound) }}>{sound ? <Volume2 size={17} /> : <VolumeX size={17} />}</button>
      </div>
    </header>

    <div className="workspace">
      <aside className={`sidebar ${mobileNav ? 'sidebar-open' : ''}`}>
        <div className="side-overline">WORKSPACE</div>
        <nav>{nav.map(({ name, icon: Icon }) => <button key={name} className={`nav-item ${page === name ? 'selected' : ''}`} onClick={() => { setPage(name); setMobileNav(false) }}><Icon size={17} /><span>{name}</span>{name === 'Incidents' && activeCount > 0 && <b>{activeCount}</b>}{name === 'Committee Inbox' && activeCount > 0 && <b>{activeCount}</b>}</button>)}</nav>
        <div className="sidebar-bottom"><div className="operator-card"><div className="operator-avatar">OP</div><div><strong>Operations desk</strong><small>LOCAL SESSION</small></div><ChevronDown size={14} /></div><div className="sidebar-build"><span>BUILD 0.9.4</span><span className="build-dot" /> OFFLINE CAPABLE</div></div>
      </aside>

      <main className="main-content">
        <div className="page-heading"><div><div className="eyebrow"><span className="live-pulse" /> SECURITY OPERATIONS <span className="eyebrow-slash">/</span> {page.toUpperCase()}</div><h1>{page === 'Analytics' ? 'Review history, trends, hotspots' : page === 'Live Ops' ? 'Live operations' : page === 'Map' ? 'Camera map' : page === 'Incidents' ? 'Incident register' : page === 'Committee Inbox' ? 'Committee response inbox' : 'System settings'}</h1><p>{page === 'Live Ops' ? 'Verified events across authorized feeds.' : page === 'Analytics' ? 'Incident activity across the last 24 hours.' : page === 'Map' ? 'Camera locations and current response activity.' : page === 'Incidents' ? 'Search, filter, and review verified events.' : page === 'Committee Inbox' ? 'Incidents routed to the appropriate response committee.' : 'Tune the operator console for this session.'}</p></div>
          <div className="heading-actions"><span className="updated-at"><span className="status-dot" /> SYSTEM NOMINAL</span><button className="outline-button" onClick={() => void window.location.reload()}><Activity size={14} /> Refresh</button></div>
        </div>

        {apiError && !mockMode && <div className="error-banner"><CloudOff size={16} /><span>Backend unavailable: {apiError}. Set <code>VITE_USE_MOCK=true</code> to run the offline demo.</span><button onClick={() => setApiError('')}><X size={15} /></button></div>}
        {page === 'Live Ops' && <LiveOps incidents={incidents} cameras={cameras} loading={loading} openIncident={openIncident} goToIncidents={() => setPage('Incidents')} simulate={() => setSimulateOpen(true)} activeCount={activeCount} acknowledgedCount={acknowledgedCount} resolvedToday={resolvedToday} avgConfidence={avgConfidence} mockMode={mockMode} />}
        {page === 'Map' && <MapView incidents={incidents} cameras={cameras} openIncident={openIncident} />}
        {page === 'Committee Inbox' && <CommitteeInbox incidents={incidents} openIncident={openIncident} resolveIncident={resolveForCommittee} />}
        {page === 'Incidents' && <IncidentsView incidents={incidents} cameras={cameras} loading={loading} openIncident={openIncident} />}
        {page === 'Analytics' && <AnalyticsView stats={stats} incidents={incidents} />}
        {page === 'Settings' && <SettingsView sound={sound} setSound={setSound} />}
      </main>
    </div>
    <footer className="privacy-footer"><span><Shield size={12} /> No facial recognition</span><i /> <span>Authorized feeds only</span><i /> <span>Human-in-the-loop</span><span className="footer-right">SENTINELAI CONTROL ROOM <b>•</b> {mockMode ? 'SIMULATION' : 'LOCAL INSTANCE'}</span></footer>

    <button className="simulate-fab" onClick={() => setSimulateOpen(!simulateOpen)}><span className="fab-spark"><Siren size={17} /></span><span>Simulate incident</span><ChevronDown size={14} /></button>
    <AnimatePresence>{simulateOpen && <SimulateMenu cameras={cameras} onChoose={simulate} onClose={() => setSimulateOpen(false)} />}</AnimatePresence>
    <AnimatePresence>{selected && <IncidentDrawer incident={selected} close={() => select(null)} patch={patchIncident} />}</AnimatePresence>
    <AnimatePresence>{toast && <motion.button className="toast" initial={{ x: 80, opacity: 0 }} animate={{ x: 0, opacity: 1 }} exit={{ x: 80, opacity: 0 }} onClick={() => select(toast)}><span className="toast-icon"><Bell size={17} /></span><span><strong>High severity verified</strong><small>{typeLabel[toast.type]} · {toast.camera_name}</small></span><X size={15} onClick={(event) => { event.stopPropagation(); setToast(null) }} /></motion.button>}</AnimatePresence>
  </div>
}

function StatCard({ label, value, unit, icon: Icon, tone, detail }: { label: string; value: string | number; unit?: string; icon: typeof Activity; tone: string; detail: string }) {
  return <div className="stat-card"><div className="stat-top"><span>{label}</span><span className={`stat-icon ${tone}`}><Icon size={16} /></span></div><div className="stat-value">{value}<small>{unit}</small></div><div className="stat-foot"><span className="stat-indicator" />{detail}</div></div>
}

function LiveOps({ incidents, cameras, loading, openIncident, goToIncidents, simulate, activeCount, acknowledgedCount, resolvedToday, avgConfidence, mockMode }: {
  incidents: Incident[]; cameras: Camera[]; loading: boolean; openIncident: (incident: Incident) => void; goToIncidents: () => void; simulate: () => void;
  activeCount: number; acknowledgedCount: number; resolvedToday: number; avgConfidence: number; mockMode: boolean
}) {
  const activeCameras = new Set(incidents.filter((item) => item.status === 'new').map((item) => item.camera_id))
  return <>
    <section className="stats-grid">
      <StatCard label="Active incidents" value={activeCount.toString().padStart(2, '0')} icon={Siren} tone="red" detail="Awaiting review" />
      <StatCard label="Acknowledged" value={acknowledgedCount.toString().padStart(2, '0')} icon={Check} tone="amber" detail="Operator engaged" />
      <StatCard label="Resolved today" value={resolvedToday.toString().padStart(2, '0')} icon={Activity} tone="green" detail="Across all locations" />
      <StatCard label="Cameras online" value={`${cameras.filter((camera) => camera.status === 'online').length.toString().padStart(2, '0')} / ${cameras.length.toString().padStart(2, '0')}`} icon={Radio} tone="cyan" detail="Authorized feeds" />
      <StatCard label="Avg confidence" value={`${Math.round(avgConfidence * 100)}`} unit="%" icon={Eye} tone="cyan" detail="Temporal verification" />
    </section>
    <section className="ops-layout">
      <div className="camera-section"><div className="section-heading"><div><h2>Camera grid <span className="section-count">{cameras.length.toString().padStart(2, '0')}</span></h2><p>LIVE AUTHORIZED FEEDS</p></div><div className="grid-legend"><span><i className="legend-live" /> Live</span><span><i className="legend-alert" /> Active alert</span></div></div>
        {loading ? <div className="camera-grid">{[1, 2, 3, 4].map((number) => <div className="skeleton camera-skeleton" key={number} />)}</div> : <div className="camera-grid">{cameras.slice(0, 4).map((camera, index) => <CameraTile key={camera.id} camera={camera} index={index} hasIncident={activeCameras.has(camera.id)} mockMode={mockMode} />)}</div>}
      </div>
      <aside className="feed-panel"><div className="section-heading feed-heading"><div><h2>Incident feed</h2><p><span className="live-pulse small" /> LIVE EVENT STREAM</p></div><button className="icon-button small-button" title="Open incident register"><ArrowUpRight size={15} /></button></div>
        <div className="feed-scroll">{incidents.slice(0, 8).map((incident) => <IncidentRow key={incident.id} incident={incident} onClick={() => openIncident(incident)} compact />)}{incidents.length === 0 && <EmptyState title="No incidents detected" text="Verified events will appear here." />}</div>
        <button className="feed-all" onClick={goToIncidents}>View incident register <ArrowUpRight size={14} /></button>
      </aside>
    </section>
    <section className="ops-bottom"><div className="integrity-strip"><span className="integrity-icon"><Shield size={18} /></span><div><strong>Temporal verification active</strong><small>Alerts require a sustained pattern across multiple frames. No single-frame triggers.</small></div><span className="integrity-state"><i /> SYSTEM GUARDRAIL</span></div><button className="quick-sim" onClick={simulate}><Siren size={15} /> Run a demo drill <ArrowUpRight size={14} /></button></section>
  </>
}

function CameraTile({ camera, index, hasIncident, mockMode }: { camera: Camera; index: number; hasIncident: boolean; mockMode: boolean }) {
  const [failed, setFailed] = useState(false)
  const live = !mockMode && !failed
  return <motion.article className={`camera-tile ${hasIncident ? 'camera-alert' : ''}`} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: index * .07 }}>
    <div className="camera-image">
      {live ? <img src={apiUrl(camera.stream_url)} alt={`${camera.name} live feed`} onError={() => setFailed(true)} /> : <div className={`feed-simulation feed-${index}`}><div className="feed-grid" /><span className="feed-crosshair" /><span className="feed-object" /><span className="feed-coordinate">CAM {camera.id.slice(-2)} · {new Date().toLocaleTimeString([], { hour12: false })}</span><span className="feed-state-label">{mockMode ? 'SIMULATED FEED' : 'NO SIGNAL'}</span><div className="feed-scanline" /></div>}
      <div className="camera-overlay"><span className="live-badge"><i /> LIVE</span><span className="camera-serial">{camera.id.toUpperCase()}</span></div>
      {hasIncident && <div className="camera-alert-label"><span /> ACTIVE INCIDENT</div>}
      <div className="camera-bottom"><div><strong>{camera.name}</strong><small><MapPin size={11} /> {camera.location.label}</small></div></div>
    </div>
  </motion.article>
}

function IncidentRow({ incident, onClick, compact = false }: { incident: Incident; onClick: () => void; compact?: boolean }) {
  const Icon = typeIcon[incident.type]
  return <button className={`incident-row ${compact ? 'compact' : ''}`} onClick={onClick}>
    <span className={`incident-type-icon ${incident.type}`}><Icon size={15} /></span>
    <span className="incident-main"><span className="incident-title">{typeLabel[incident.type]}</span><span className="incident-meta">{incident.camera_name} <i /> {relativeTime(incident.timestamp)}</span>{!compact && <span className="confidence-track"><i style={{ width: `${incident.confidence * 100}%` }} /></span>}</span>
    <span className="incident-side"><span className={`severity-chip ${incident.severity}`}>{incident.severity}</span><span className={`status-label ${incident.status}`}>{incident.status}</span></span>
  </button>
}

function EmptyState({ title, text }: { title: string; text: string }) {
  return <div className="empty-state"><span><Cloud size={19} /></span><strong>{title}</strong><small>{text}</small></div>
}

function IncidentsView({ incidents, cameras, loading, openIncident }: { incidents: Incident[]; cameras: Camera[]; loading: boolean; openIncident: (incident: Incident) => void }) {
  const [search, setSearch] = useState('')
  const [typeFilter, setTypeFilter] = useState('all')
  const [statusFilter, setStatusFilter] = useState('all')
  const [cameraFilter, setCameraFilter] = useState('all')
  const filtered = incidents.filter((incident) => (typeFilter === 'all' || incident.type === typeFilter) && (statusFilter === 'all' || incident.status === statusFilter) && (cameraFilter === 'all' || incident.camera_id === cameraFilter) && `${incident.id} ${incident.camera_name} ${typeLabel[incident.type]}`.toLowerCase().includes(search.toLowerCase()))
  return <section className="view-panel incident-register"><div className="table-toolbar"><div className="search-box"><Search size={15} /><input placeholder="Search incidents or cameras" value={search} onChange={(event) => setSearch(event.target.value)} /></div><div className="filter-controls"><label><Filter size={13} /><select value={typeFilter} onChange={(event) => setTypeFilter(event.target.value)}><option value="all">All types</option>{Object.entries(typeLabel).map(([key, value]) => <option key={key} value={key}>{value}</option>)}</select></label><label><select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}><option value="all">All status</option><option value="new">New</option><option value="acknowledged">Acknowledged</option><option value="resolved">Resolved</option></select></label><label><select value={cameraFilter} onChange={(event) => setCameraFilter(event.target.value)}><option value="all">All cameras</option>{cameras.map((camera) => <option key={camera.id} value={camera.id}>{camera.name}</option>)}</select></label></div></div>
    <div className="table-head"><span>INCIDENT</span><span>CAMERA / LOCATION</span><span>DETECTED</span><span>CONFIDENCE</span><span>SEVERITY</span><span>STATUS</span></div>
    {loading ? <div className="table-loading"><div className="skeleton" /><div className="skeleton" /><div className="skeleton" /></div> : filtered.length ? <div className="incident-table">{filtered.map((incident) => <button className="table-row" key={incident.id} onClick={() => openIncident(incident)}><span className="table-type"><span className={`incident-type-icon ${incident.type}`}><Activity size={14} /></span><span>{typeLabel[incident.type]}<small>{incident.id}</small></span></span><span className="table-location">{incident.camera_name}<small>{incident.location.label}</small></span><span className="table-time">{new Date(incident.timestamp).toLocaleString([], { month: 'short', day: '2-digit', hour: '2-digit', minute: '2-digit' })}</span><span className="table-confidence"><b>{Math.round(incident.confidence * 100)}%</b><i><em style={{ width: `${incident.confidence * 100}%` }} /></i></span><span><span className={`severity-chip ${incident.severity}`}>{incident.severity}</span></span><span><span className={`status-label ${incident.status}`}>{incident.status}</span></span></button>)}</div> : <EmptyState title="No matching incidents" text="Try changing your filters or search terms." />}
    <div className="table-footer"><span>Showing <b>{filtered.length}</b> of {incidents.length} records</span><span>Newest first <ChevronDown size={12} /></span></div>
  </section>
}

function CommitteeInbox({ incidents, openIncident, resolveIncident }: {
  incidents: Incident[]
  openIncident: (incident: Incident) => void
  resolveIncident: (incident: Incident) => Promise<void>
}) {
  const [resolving, setResolving] = useState<string | null>(null)
  const queue = incidents.filter((incident) => incident.status !== 'resolved')
  const resolve = async (incident: Incident) => {
    setResolving(incident.id)
    try { await resolveIncident(incident) } finally { setResolving(null) }
  }
  return <section className="committee-inbox">
    <div className="committee-summary"><span className="committee-summary-icon"><Users size={18} /></span><div><strong>{queue.length} incident{queue.length === 1 ? '' : 's'} awaiting committee review</strong><small>Assignments are routed by incident type. Review the clip before resolving.</small></div><span className="human-review-chip">HUMAN REVIEW</span></div>
    {queue.length ? <div className="committee-list">{queue.map((incident) => {
      const Icon = typeIcon[incident.type]
      return <article className="committee-card" key={incident.id}>
        <div className="committee-card-main"><span className={`incident-type-icon ${incident.type}`}><Icon size={16} /></span><div className="committee-incident-title"><strong>{typeLabel[incident.type]}</strong><small>{incident.camera_name} · {relativeTime(incident.timestamp)} · {incident.id}</small></div><span className={`severity-chip ${incident.severity}`}>{incident.severity}</span></div>
        <div className="committee-assignment"><span><Users size={13} /> Assigned committee</span><strong>{committeeFor[incident.type]}</strong><span className={`status-label ${incident.status}`}>{incident.status}</span></div>
        <div className="committee-actions"><button className="committee-watch" onClick={() => openIncident(incident)}><Eye size={14} /> Watch evidence</button><button className="committee-resolve" disabled={resolving === incident.id} onClick={() => void resolve(incident)}><Check size={14} /> {resolving === incident.id ? 'Saving...' : 'Resolve incident'}</button></div>
      </article>
    })}</div> : <EmptyState title="Committee inbox is clear" text="New verified incidents will route here for human review." />}
  </section>
}

function MapView({ incidents, cameras, openIncident }: { incidents: Incident[]; cameras: Camera[]; openIncident: (incident: Incident) => void }) {
  const activeByCamera = useMemo(() => new Map(cameras.map((camera) => [camera.id, incidents.find((item) => item.camera_id === camera.id && item.status === 'new')])), [cameras, incidents])
  return <section className="map-panel"><div className="map-topline"><span><i className="legend-live" /> {cameras.length} CAMERAS</span><span><i className="legend-alert" /> ACTIVE INCIDENT</span><span className="map-coordinates">12.9716° N &nbsp; 77.5946° E</span></div><MapContainer center={[12.973, 77.595]} zoom={14} scrollWheelZoom className="leaflet-map"><TileLayer attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors' url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" /><Circle center={[12.973, 77.595]} radius={750} pathOptions={{ color: '#20c7cd', weight: 1, opacity: .45, fillColor: '#20c7cd', fillOpacity: .055 }} />{cameras.map((camera) => { const incident = activeByCamera.get(camera.id); return <CircleMarker key={camera.id} center={[camera.location.lat, camera.location.lng]} radius={incident ? 9 : 6} pathOptions={{ color: incident ? '#f45e65' : '#4ce0d2', fillColor: incident ? '#f45e65' : '#4ce0d2', fillOpacity: .95, weight: 2 }}><Popup><div className="map-popup"><strong>{camera.name}</strong><small>{camera.location.label}</small>{incident ? <><span className="popup-alert">{typeLabel[incident.type]} · {Math.round(incident.confidence * 100)}%</span><button onClick={() => openIncident(incident)}>Open incident</button></> : <span className="popup-online">● Feed online</span>}</div></Popup></CircleMarker> })}</MapContainer><div className="map-legend"><span><i className="map-pin-normal" /> Online</span><span><i className="map-pin-active" /> Active incident</span><span><i className="map-zone" /> Response zone</span></div></section>
}

function AnalyticsView({ stats, incidents }: { stats: Stats | null; incidents: Incident[] }) {
  const current = stats ?? mockStats(incidents)
  const pieData = Object.entries(current.by_type).map(([key, value]) => ({ name: typeLabel[key as IncidentType], value, color: colorType[key as IncidentType] }))
  return <div className="analytics-view"><div className="analytics-kpis"><div><small>TOTAL EVENTS / 24H</small><strong>{current.total}</strong><span>Across all authorized feeds</span></div><div><small>NEW / AWAITING REVIEW</small><strong className="text-red">{current.by_status.new}</strong><span>Operator action required</span></div><div><small>RESOLVED</small><strong className="text-green">{current.by_status.resolved}</strong><span>Human-confirmed resolution</span></div></div><div className="chart-grid"><section className="chart-panel chart-wide"><div className="chart-heading"><div><h3>Event activity</h3><small>HOURLY INCIDENT COUNTS · LAST 24 HOURS</small></div><span className="chart-legend"><i /> INCIDENTS</span></div><div className="chart-area"><ResponsiveContainer width="100%" height="100%"><AreaChart data={current.by_hour}><defs><linearGradient id="cyanFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#28c8d1" stopOpacity={.32} /><stop offset="95%" stopColor="#28c8d1" stopOpacity={0} /></linearGradient></defs><CartesianGrid stroke="rgba(255,255,255,.06)" vertical={false} /><XAxis dataKey="hour" tick={{ fill: '#778494', fontSize: 10 }} axisLine={false} tickLine={false} interval={3} /><YAxis allowDecimals={false} tick={{ fill: '#778494', fontSize: 10 }} axisLine={false} tickLine={false} width={26} /><Tooltip contentStyle={{ background: '#101a29', border: '1px solid #253445', borderRadius: 4, color: '#eff5f4' }} /><Area type="monotone" dataKey="count" stroke="#3bd3d2" strokeWidth={2} fill="url(#cyanFill)" /></AreaChart></ResponsiveContainer></div></section><section className="chart-panel"><div className="chart-heading"><div><h3>Incident mix</h3><small>EVENTS BY DETECTION TYPE</small></div></div><div className="chart-donut"><ResponsiveContainer width="100%" height="100%"><PieChart><Pie data={pieData} dataKey="value" innerRadius="66%" outerRadius="88%" paddingAngle={4} stroke="none">{pieData.map((item) => <Cell key={item.name} fill={item.color} />)}</Pie><Tooltip contentStyle={{ background: '#101a29', border: '1px solid #253445', borderRadius: 4 }} /></PieChart></ResponsiveContainer><div className="donut-center"><strong>{current.total}</strong><small>EVENTS</small></div></div><div className="chart-keys">{pieData.map((item) => <span key={item.name}><i style={{ background: item.color }} />{item.name}<b>{item.value}</b></span>)}</div></section><section className="chart-panel chart-wide"><div className="chart-heading"><div><h3>Location hotspots</h3><small>VERIFIED EVENTS BY CAMERA</small></div></div><div className="bar-chart"><ResponsiveContainer width="100%" height="100%"><BarChart data={current.by_camera} layout="vertical" margin={{ left: 8, right: 20 }}><CartesianGrid stroke="rgba(255,255,255,.05)" horizontal={false} /><XAxis type="number" allowDecimals={false} tick={{ fill: '#778494', fontSize: 10 }} axisLine={false} tickLine={false} /><YAxis type="category" dataKey="name" width={170} tick={{ fill: '#aab6c0', fontSize: 10 }} axisLine={false} tickLine={false} /><Tooltip contentStyle={{ background: '#101a29', border: '1px solid #253445', borderRadius: 4 }} /><Bar dataKey="count" fill="#43c8c4" radius={[0, 3, 3, 0]} barSize={13} /></BarChart></ResponsiveContainer></div></section></div></div>
}

function SettingsView({ sound, setSound }: { sound: boolean; setSound: (value: boolean) => void }) {
  const [enabled, setEnabled] = useState<Record<IncidentType, boolean>>({ physical_altercation: true, fall_collapse: true, abnormal_crowd_movement: true })
  const [threshold, setThreshold] = useState(70)
  return <div className="settings-view"><section className="settings-panel"><div className="settings-section-title"><div><h3>Detection categories</h3><p>Session controls · changes are local to this dashboard</p></div><span className="ui-only-label">UI CONTROL</span></div><div className="detection-options">{(Object.keys(typeLabel) as IncidentType[]).map((type) => { const Icon = typeIcon[type]; return <button key={type} className={`detection-option ${enabled[type] ? 'enabled' : ''}`} onClick={() => setEnabled((old) => ({ ...old, [type]: !old[type] }))}><span className={`incident-type-icon ${type}`}><Icon size={16} /></span><span><strong>{typeLabel[type]}</strong><small>Temporal verification required</small></span><span className={`ready-chip ${enabled[type] ? 'ready' : ''}`}>{enabled[type] ? 'READY' : 'PAUSED'}</span></button> })}</div></section><section className="settings-panel"><div className="settings-section-title"><div><h3>Alert threshold</h3><p>Minimum confidence displayed as an operator alert</p></div><span className="threshold-number">{threshold}%</span></div><input className="threshold-slider" type="range" min="50" max="95" value={threshold} onChange={(event) => setThreshold(Number(event.target.value))} /><div className="range-labels"><span>50% · MORE SENSITIVE</span><span>95% · HIGHER CONFIDENCE</span></div></section><section className="settings-panel sound-setting"><div className="settings-section-title"><div><h3>Audible alerts</h3><p>Play a four-pulse buzzer for a new high-severity event</p></div><button className={`switch ${sound ? 'on' : ''}`} onClick={() => setSound(!sound)} aria-label="Toggle audible alerts"><i /></button></div></section><div className="privacy-note"><Shield size={17} /><span><strong>Privacy guardrails are always on</strong><small>No facial recognition or identity features. Operators remain responsible for every response.</small></span><Check size={16} /></div></div>
}

function SimulateMenu({ cameras, onChoose, onClose }: { cameras: Camera[]; onChoose: (type: IncidentType, cameraId: string) => void; onClose: () => void }) {
  const [cameraId, setCameraId] = useState(cameras[0]?.id ?? 'cam_01')
  return <motion.div className="simulate-menu" initial={{ opacity: 0, y: 10, scale: .98 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, y: 8 }}><div className="simulate-menu-head"><div><span className="eyebrow">DEMO SAFETY NET</span><h3>Simulate an incident</h3></div><button className="icon-button" onClick={onClose}><X size={15} /></button></div><label className="camera-select-label">CAMERA<select value={cameraId} onChange={(event) => setCameraId(event.target.value)}>{cameras.map((camera) => <option key={camera.id} value={camera.id}>{camera.id} · {camera.name}</option>)}</select></label><div className="simulate-types">{(Object.keys(typeLabel) as IncidentType[]).map((type) => { const Icon = typeIcon[type]; return <button key={type} onClick={() => onChoose(type, cameraId)}><span className={`incident-type-icon ${type}`}><Icon size={15} /></span><span>{typeLabel[type]}</span><ArrowUpRight size={14} /></button> })}</div><small className="simulate-footnote">Creates a clearly labeled demo event. No automated response.</small></motion.div>
}

function IncidentDrawer({ incident, close, patch }: { incident: Incident; close: () => void; patch: (incident: Incident, body: { status?: IncidentStatus; notes?: string }) => Promise<void> }) {
  const [notes, setNotes] = useState(incident.notes)
  const [saving, setSaving] = useState(false)
  const videoRef = useRef<HTMLVideoElement>(null)
  const Icon = typeIcon[incident.type]
  const save = async (body: { status?: IncidentStatus; notes?: string }) => { setSaving(true); try { await patch(incident, body) } finally { setSaving(false) } }
  useEffect(() => setNotes(incident.notes), [incident.id, incident.notes])
  useEffect(() => {
    const video = videoRef.current
    if (!video) return
    video.muted = true
    void video.play().catch(() => {})
  }, [incident.id])
  return <><motion.button className="drawer-scrim" aria-label="Close incident details" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={close} /><motion.aside className="incident-drawer" initial={{ x: 560 }} animate={{ x: 0 }} exit={{ x: 560 }} transition={{ type: 'spring', damping: 30, stiffness: 280 }}><div className="drawer-head"><div><span className="eyebrow">INCIDENT RECORD · {incident.id.toUpperCase()}</span><button className="drawer-close icon-button" onClick={close}><X size={18} /></button></div><h2>{typeLabel[incident.type]}</h2><p><span className={`severity-chip ${incident.severity}`}>{incident.severity} severity</span><span className={`status-label ${incident.status}`}>{incident.status}</span></p></div><div className="drawer-media"><video ref={videoRef} key={incident.id} controls preload="auto" autoPlay muted playsInline poster={apiUrl(incident.snapshot_url)} src={apiUrl(incident.clip_url)} /><span className="media-tag"><Radio size={11} /> EVENT FOOTAGE · MUTED</span></div><div className="drawer-content"><div className="committee-recipient"><Users size={15} /><span><small>ROUTED TO</small><strong>{committeeFor[incident.type]}</strong></span><span className="recipient-received"><Check size={12} /> RECEIVED</span></div><div className="confidence-block"><div><small>MODEL CONFIDENCE</small><strong>{Math.round(incident.confidence * 100)}<i>%</i></strong></div><div className="confidence-ring" style={{ '--confidence': `${incident.confidence * 100}%` } as React.CSSProperties}><span><Icon size={17} /></span></div></div><div className="detail-grid"><div><small>CAMERA</small><strong>{incident.camera_name}</strong></div><div><small>LOCATION</small><strong>{incident.location.label}</strong></div><div><small>DETECTED</small><strong>{new Date(incident.timestamp).toLocaleString()}</strong></div><div><small>INCIDENT ID</small><strong className="mono">{incident.id}</strong></div></div><div className="verification-box"><div><Shield size={15} /><strong>Temporal verification</strong><span>CONFIRMED</span></div><p><b>{incident.verification.frames_confirmed} / {incident.verification.frames_required}</b> frames confirmed over {incident.verification.window_seconds}s window</p><div className="verification-bar"><i style={{ width: `${Math.min(100, incident.verification.frames_confirmed / incident.verification.frames_required * 100)}%` }} /></div></div><div className="timeline"><small className="detail-overline">RESPONSE TIMELINE</small><div className="timeline-row done"><i /><span>Detected & verified</span><time>{new Date(incident.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</time></div><div className={`timeline-row ${incident.status !== 'new' ? 'done' : ''}`}><i /><span>Operator acknowledged</span>{incident.status !== 'new' && <Check size={13} />}</div><div className={`timeline-row ${incident.status === 'resolved' ? 'done' : ''}`}><i /><span>Resolved</span>{incident.status === 'resolved' && <Check size={13} />}</div></div><label className="notes-label">OPERATOR NOTES<textarea value={notes} onChange={(event) => setNotes(event.target.value)} onBlur={() => { if (notes !== incident.notes) void save({ notes }) }} placeholder="Add context for the response team..." /></label><div className="drawer-actions">{incident.status === 'new' && <button className="ack-button" disabled={saving} onClick={() => void save({ status: 'acknowledged' })}><Check size={15} /> Acknowledge</button>}{incident.status !== 'resolved' && <button className="resolve-button" disabled={saving} onClick={() => void save({ status: 'resolved' })}>Mark resolved</button>}<button className="evidence-button" onClick={() => window.open(apiUrl(incident.snapshot_url), '_blank')}><Eye size={14} /> Snapshot</button></div></div></motion.aside></>
}