import type { Camera, Incident, IncidentStatus, IncidentType, Stats } from '../types/contracts'

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000'
export const useMock = import.meta.env.VITE_USE_MOCK === 'true'
export const apiUrl = (path: string) => `${API}${path}`

const sites = [
  { id: 'cam_01', name: 'Central Plaza - North', location: { lat: 12.9716, lng: 77.5946, label: 'Central Plaza' } },
  { id: 'cam_02', name: 'Metro Transit Hub - East Concourse', location: { lat: 12.978, lng: 77.6005, label: 'Transit Hub' } },
  { id: 'cam_03', name: 'Stadium Gate 4 - Entry Plaza', location: { lat: 12.9698, lng: 77.589, label: 'Stadium Gate 4' } },
  { id: 'cam_04', name: 'Financial District - Main Arcade', location: { lat: 12.9752, lng: 77.5912, label: 'Financial District' } },
]
const types: IncidentType[] = ['physical_altercation', 'fall_collapse', 'abnormal_crowd_movement']
const severity = (confidence: number): Incident['severity'] => confidence >= .85 ? 'high' : confidence >= .7 ? 'medium' : 'low'

export const mockCameras: Camera[] = sites.map((site) => ({ ...site, status: 'online', stream_url: `/api/stream/${site.id}` }))
export function makeMockIncidents(): Incident[] {
  return Array.from({ length: 6 }, (_, index) => {
    const site = sites[index % sites.length]
    const confidence = Number((.64 + ((index * 17) % 34) / 100).toFixed(2))
    const type = types[index % types.length]
    return {
      id: `inc_${String(index + 1).padStart(4, '0')}`, camera_id: site.id, camera_name: site.name,
      location: site.location, type, confidence, severity: severity(confidence),
      timestamp: new Date(Date.now() - (index * 53 + 11) * 60_000).toISOString(),
      status: index === 0 ? 'new' : index === 1 ? 'acknowledged' : 'resolved',
      snapshot_url: `/media/snapshots/${site.id}_${type}.jpg`, clip_url: `/media/clips/${site.id}_${type}.mp4`,
      notes: index === 0 ? 'Verified event for operator review.' : 'Historical demo record.',
      verification: { window_seconds: 2.5, frames_confirmed: 30 + index % 12, frames_required: 25 },
    }
  })
}

const request = async <T,>(path: string, init?: RequestInit): Promise<T> => {
  const response = await fetch(apiUrl(path), { ...init, headers: { 'Content-Type': 'application/json', ...init?.headers } })
  if (!response.ok) throw new Error(`API ${response.status}: ${await response.text()}`)
  return response.json() as Promise<T>
}

export const api = {
  health: () => request<{ status: string; cameras_online: number; cameras_total: number }>('/api/health'),
  cameras: () => request<Camera[]>('/api/cameras'),
  incidents: () => request<Incident[]>('/api/incidents'),
  stats: () => request<Stats>('/api/stats'),
  update: (id: string, body: { status?: IncidentStatus; notes?: string }) => request<Incident>(`/api/incidents/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),
  simulate: (type: IncidentType, camera_id: string) => request<Incident>('/api/simulate', { method: 'POST', body: JSON.stringify({ type, camera_id }) }),
}

export function createMockIncident(type: IncidentType, cameraId: string): Incident {
  const site = sites.find((camera) => camera.id === cameraId) ?? sites[0]
  const confidence = Number((.77 + Math.random() * .21).toFixed(2))
  return {
    id: `inc_demo_${Date.now()}`, camera_id: site.id, camera_name: site.name, location: site.location,
    type, confidence, severity: severity(confidence), timestamp: new Date().toISOString(), status: 'new',
    snapshot_url: `/media/snapshots/${site.id}_${type}.jpg`, clip_url: `/media/clips/${site.id}_${type}.mp4`,
    notes: 'Simulated demo drill for human operator review.',
    verification: { window_seconds: 2.5, frames_confirmed: 32 + Math.floor(Math.random() * 12), frames_required: 25 },
  }
}