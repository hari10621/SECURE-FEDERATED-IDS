import type { AttackReplay } from './types'
import { apiRequest } from './api'

export type LabSpec = {
  topology: 'single' | 'linear' | 'tree'
  switches: number
  hosts: number
  subnet: string
  controller: string
  port: number
}
export type LabHost = {
  name: string
  ip: string
  mac: string
  switch: string
  port: number
  connected: boolean
  client: string | null
  organization?: string
  retraining?: string
  alerts: number
  tx_packets: number
  rx_packets: number
}
export type LabSnapshot = {
  state: string
  reason: string
  config: LabSpec | null
  running: boolean
  lab_id: string | null
  packets: number | null
  hosts: LabHost[]
  switches: {
    name: string
    dpid: string
    connected: boolean
    ports: Record<string, number>
  }[]
  links: {
    source: string
    target: string
    source_port: string
    target_port: string
    up: boolean
  }[]
  flows: { switch: string; rule: string }[]
  history: { time: number; pps: number; bps: number }[]
  events: {
    host: string
    client: string
    kind: string
    ts: number
    result: { label: number; prediction: number; version: string }
  }[]
}
export const labRequest = <T>(path: string, body?: unknown) =>
  apiRequest<T>('/api/v1/sdn/' + path, {
    method: body === undefined ? 'GET' : 'POST',
    body,
    timeoutMs: 45000,
  })
export const snapshot = () => labRequest<LabSnapshot>('topology')
export type Capture = {
  id: string
  features: number[]
  prediction: AttackReplay | null
  observed_flows: {
    source: string
    destination: string
    protocol: number
    packets: number
  }[]
}
