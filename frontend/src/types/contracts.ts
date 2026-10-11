export type IncidentType = 'physical_altercation' | 'fall_collapse' | 'abnormal_crowd_movement'
export type IncidentStatus = 'new' | 'acknowledged' | 'resolved'
export type Severity = 'low' | 'medium' | 'high'

export interface Location { lat: number; lng: number; label: string }
export interface Verification { window_seconds: number; frames_confirmed: number; frames_required: number }
export interface Incident {
  id: string
  camera_id: string
  camera_name: string
  location: Location
  type: IncidentType
  confidence: number
  severity: Severity
  timestamp: string
  status: IncidentStatus
  snapshot_url: string
  clip_url: string
  notes: string
  verification: Verification
}
export interface Camera { id: string; name: string; location: Location; status: 'online' | 'offline'; stream_url: string }
export interface Stats {
  total: number
  by_type: Record<IncidentType, number>
  by_status: Record<IncidentStatus, number>
  by_hour: Array<{ hour: string; count: number }>
  by_camera: Array<{ camera_id: string; name: string; count: number }>
}
export type Page = 'Live Ops' | 'Map' | 'Committee Inbox' | 'Incidents' | 'Analytics' | 'Settings'