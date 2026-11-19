import { ApiError } from './api'

export function cn(...values: Array<string | false | null | undefined>): string {
  return values.filter(Boolean).join(' ')
}

export function humanize(value: string | null | undefined): string {
  if (!value) return 'Unknown'
  return value
    .replace(/[_-]+/g, ' ')
    .replace(/\b\w/g, (letter) => letter.toUpperCase())
}

export function formatDate(value: string | null | undefined): string {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '—'
  return new Intl.DateTimeFormat(undefined, {
    month: 'short',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date)
}

export function formatBytes(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes < 0) return '—'
  if (bytes < 1024) return `${bytes} B`
  const units = ['KB', 'MB', 'GB', 'TB']
  let value = bytes / 1024
  let index = 0
  while (value >= 1024 && index < units.length - 1) {
    value /= 1024
    index += 1
  }
  return `${value.toFixed(1)} ${units[index]}`
}

export function formatNumber(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—'
  return new Intl.NumberFormat().format(value)
}

const PERCENT_METRICS = new Set([
  'accuracy',
  'precision',
  'recall',
  'f1',
  'f1_score',
  'gmean',
  'g_mean',
  'auc',
])

export function formatMetric(key: string, value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return 'n/a'
  if (PERCENT_METRICS.has(key)) return `${(value * 100).toFixed(2)}%`
  return value.toFixed(4)
}

export function describeError(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 0) {
      return `${error.message} Check that the API is running and that the base URL in Settings is correct.`
    }
    return error.message
  }
  if (error instanceof Error) return error.message
  return 'An unexpected error occurred.'
}

export function isActiveStatus(status: string): boolean {
  return status === 'queued' || status === 'running' || status === 'cancellation_requested'
}

export type Tone = 'success' | 'warning' | 'danger' | 'info' | 'neutral'

export function statusTone(status: string): Tone {
  switch (status) {
    case 'succeeded':
    case 'ok':
    case 'valid':
    case 'enabled':
      return 'success'
    case 'running':
    case 'queued':
      return 'info'
    case 'cancellation_requested':
    case 'configured':
    case 'degraded':
      return 'warning'
    case 'failed':
    case 'invalid':
    case 'error':
      return 'danger'
    default:
      return 'neutral'
  }
}

export function firstName(keys: string[]): string | null {
  return keys.length > 0 ? keys[0] : null
}
