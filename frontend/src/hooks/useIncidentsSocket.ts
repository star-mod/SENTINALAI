import { useEffect } from 'react'
import { api, apiUrl, createMockIncident, useMock } from '../api/client'
import { playIncidentBuzzer } from '../api/alertSound'
import { useSentinelStore } from '../store/useSentinelStore'
import type { Incident, IncidentType } from '../types/contracts'

export function useIncidentsSocket() {
  const { upsert, setConnected, setToast, select, sound, setMockMode } = useSentinelStore()

  useEffect(() => {
    let socket: WebSocket | undefined
    let reconnectTimer: number | undefined
    let generatorTimer: number | undefined
    let disposed = false
    const handleIncident = (incident: Incident, isCreated = false) => {
      upsert(incident)
      if (isCreated && incident.status === 'new' && incident.severity === 'high') {
        setToast(incident)
        select(incident)
        playIncidentBuzzer(sound)
        window.setTimeout(() => setToast(null), 5200)
      }
    }

    if (useMock) {
      setMockMode(true)
      generatorTimer = window.setInterval(() => {
        const cameraId = `cam_0${1 + Math.floor(Math.random() * 4)}`
        const types: IncidentType[] = ['physical_altercation', 'fall_collapse', 'abnormal_crowd_movement', 'vehicle_accident']
        const type = types[Math.floor(Math.random() * types.length)]
        handleIncident(createMockIncident(type, cameraId), true)
      }, 60_000)
      return () => window.clearInterval(generatorTimer)
    }

    const connect = () => {
      if (disposed) return
      const socketUrl = apiUrl('/ws/incidents').replace(/^http/, 'ws')
      socket = new WebSocket(socketUrl)
      socket.onopen = () => {
        setConnected(true)
        setMockMode(false)
        void api.incidentSnapshot()
          .then((snapshot) => snapshot.items.forEach((incident) => handleIncident(incident)))
          .catch((error: unknown) => console.error('Incident snapshot synchronization failed', error))
      }
      socket.onmessage = (event) => {
        const message = JSON.parse(event.data) as { event: string; data: Incident }
        if (message.event === 'incident.created') handleIncident(message.data, true)
        if (message.event === 'incident.updated' || message.event === 'workflow.updated') handleIncident(message.data)
      }
      socket.onclose = () => {
        setConnected(false)
        if (!disposed) reconnectTimer = window.setTimeout(connect, 1800)
      }
      socket.onerror = () => socket?.close()
    }
    connect()
    return () => {
      disposed = true
      if (reconnectTimer) window.clearTimeout(reconnectTimer)
      socket?.close()
    }
  }, [select, setConnected, setMockMode, setToast, sound, upsert])
}