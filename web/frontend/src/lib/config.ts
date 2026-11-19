export interface ApiConfig {
  baseUrl: string
  token: string
}

const STORAGE_KEY = 'securefed.console.api.v1'

const ENV_BASE_URL = import.meta.env.VITE_API_BASE_URL as string | undefined

export const DEFAULT_BASE_URL = (ENV_BASE_URL ?? 'http://127.0.0.1:8000').replace(/\/+$/, '')

export function normalizeBaseUrl(raw: string): string {
  const trimmed = raw.trim()
  if (!trimmed) {
    throw new Error('API base URL is required.')
  }
  let url: URL
  try {
    url = new URL(trimmed)
  } catch {
    throw new Error('Enter an absolute URL, for example http://127.0.0.1:8000.')
  }
  if (url.protocol !== 'http:' && url.protocol !== 'https:') {
    throw new Error('API base URL must use http or https.')
  }
  return `${url.origin}${url.pathname}`.replace(/\/+$/, '')
}

export function loadApiConfig(): ApiConfig {
  const fallback: ApiConfig = { baseUrl: DEFAULT_BASE_URL, token: '' }
  if (typeof window === 'undefined') return fallback
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY)
    if (!raw) return fallback
    const parsed = JSON.parse(raw) as Partial<ApiConfig>
    const baseUrl =
      typeof parsed.baseUrl === 'string' && parsed.baseUrl
        ? normalizeBaseUrl(parsed.baseUrl)
        : DEFAULT_BASE_URL
    const token = typeof parsed.token === 'string' ? parsed.token : ''
    return { baseUrl, token }
  } catch {
    return fallback
  }
}

export function saveApiConfig(next: ApiConfig): ApiConfig {
  const normalized: ApiConfig = {
    baseUrl: normalizeBaseUrl(next.baseUrl),
    token: next.token.trim(),
  }
  if (typeof window !== 'undefined') {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(normalized))
  }
  return normalized
}

export function resetApiConfig(): ApiConfig {
  if (typeof window !== 'undefined') {
    window.localStorage.removeItem(STORAGE_KEY)
  }
  return { baseUrl: DEFAULT_BASE_URL, token: '' }
}
