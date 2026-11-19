import { describe, expect, it } from 'vitest'
import {
  DEFAULT_BASE_URL,
  loadApiConfig,
  normalizeBaseUrl,
  resetApiConfig,
  saveApiConfig,
} from './config'

describe('normalizeBaseUrl', () => {
  it('removes trailing slashes', () => {
    expect(normalizeBaseUrl('http://127.0.0.1:8000///')).toBe('http://127.0.0.1:8000')
  })

  it('keeps a path prefix without a trailing slash', () => {
    expect(normalizeBaseUrl('https://example.test/securefed/')).toBe(
      'https://example.test/securefed',
    )
  })

  it('rejects empty input', () => {
    expect(() => normalizeBaseUrl('   ')).toThrow(/required/i)
  })

  it('rejects non-http protocols', () => {
    expect(() => normalizeBaseUrl('ftp://127.0.0.1')).toThrow(/http/i)
  })
})

describe('local API config', () => {
  it('falls back to defaults when storage is empty', () => {
    expect(loadApiConfig()).toEqual({ baseUrl: DEFAULT_BASE_URL, token: '' })
  })

  it('round-trips a saved configuration', () => {
    saveApiConfig({ baseUrl: 'http://localhost:9000/', token: '  abc  ' })
    expect(loadApiConfig()).toEqual({ baseUrl: 'http://localhost:9000', token: 'abc' })
  })

  it('resets to defaults', () => {
    saveApiConfig({ baseUrl: 'http://localhost:9000', token: 'abc' })
    expect(resetApiConfig()).toEqual({ baseUrl: DEFAULT_BASE_URL, token: '' })
    expect(loadApiConfig()).toEqual({ baseUrl: DEFAULT_BASE_URL, token: '' })
  })
})
