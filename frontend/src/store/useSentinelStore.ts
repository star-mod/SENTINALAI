import { create } from 'zustand'
import type { Camera, Incident, Page, Stats } from '../types/contracts'

interface SentinelState {
  incidents: Incident[]
  cameras: Camera[]
  stats: Stats | null
  page: Page
  selected: Incident | null
  connected: boolean
  mockMode: boolean
  sound: boolean
  toast: Incident | null
  setData: (incidents: Incident[], cameras: Camera[], stats: Stats) => void
  upsert: (incident: Incident) => void
  setPage: (page: Page) => void
  select: (incident: Incident | null) => void
  setConnected: (connected: boolean) => void
  setMockMode: (mockMode: boolean) => void
  setSound: (sound: boolean) => void
  setToast: (incident: Incident | null) => void
}

export const useSentinelStore = create<SentinelState>((set) => ({
  incidents: [], cameras: [], stats: null, page: 'Live Ops', selected: null,
  connected: false, mockMode: false, sound: true, toast: null,
  setData: (incidents, cameras, stats) => set({ incidents, cameras, stats }),
  upsert: (incident) => set((state) => ({
    incidents: [incident, ...state.incidents.filter((item) => item.id !== incident.id)].sort((a, b) => b.timestamp.localeCompare(a.timestamp)),
    stats: state.stats ? (() => {
      const previous = state.incidents.find((item) => item.id === incident.id)
      const by_type = { ...state.stats.by_type }
      const by_status = { ...state.stats.by_status }
      const cameras = state.stats.by_camera.map((camera) => ({ ...camera }))
      if (previous) {
        by_type[previous.type] = Math.max(0, by_type[previous.type] - 1)
        by_status[previous.status] = Math.max(0, by_status[previous.status] - 1)
        const oldCamera = cameras.find((camera) => camera.camera_id === previous.camera_id)
        if (oldCamera) oldCamera.count = Math.max(0, oldCamera.count - 1)
      }
      by_type[incident.type]++
      by_status[incident.status]++
      const camera = cameras.find((item) => item.camera_id === incident.camera_id)
      if (camera) camera.count++
      const by_hour = state.stats.by_hour.map((item) => ({ ...item }))
      const changeHour = (timestamp: string, delta: number) => {
        const hour = `${String(new Date(timestamp).getUTCHours()).padStart(2, '0')}:00`
        const bucket = by_hour.find((item) => item.hour === hour)
        if (bucket) bucket.count = Math.max(0, bucket.count + delta)
      }
      if (previous) changeHour(previous.timestamp, -1)
      changeHour(incident.timestamp, 1)
      return { ...state.stats, total: state.stats.total + (previous ? 0 : 1), by_type, by_status, by_hour, by_camera: cameras.sort((a, b) => b.count - a.count) }
    })() : null,
  })),
  setPage: (page) => set({ page }), select: (selected) => set({ selected }),
  setConnected: (connected) => set({ connected }), setMockMode: (mockMode) => set({ mockMode }),
  setSound: (sound) => set({ sound }), setToast: (toast) => set({ toast }),
}))