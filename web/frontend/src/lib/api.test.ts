import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError, apiRequest } from './api'
import { saveApiConfig } from './config'

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

beforeEach(() => {
  saveApiConfig({ baseUrl: 'http://127.0.0.1:8000', token: '' })
})

describe('apiRequest', () => {
  it('parses a JSON response', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ status: 'ok' }))
    vi.stubGlobal('fetch', fetchMock)

    await expect(apiRequest<{ status: string }>('/api/v1/health')).resolves.toEqual({
      status: 'ok',
    })
    expect(fetchMock).toHaveBeenCalledWith(
      'http://127.0.0.1:8000/api/v1/health',
      expect.objectContaining({ headers: expect.any(Headers) }),
    )
  })

  it('sends a bearer token when configured', async () => {
    saveApiConfig({ baseUrl: 'http://127.0.0.1:8000', token: 'local-token' })
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ status: 'ok' }))
    vi.stubGlobal('fetch', fetchMock)

    await apiRequest('/api/v1/health')
    const headers = fetchMock.mock.calls[0][1].headers as Headers
    expect(headers.get('Authorization')).toBe('Bearer local-token')
  })

  it('serialises JSON bodies and sets the content type', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ id: 'x' }))
    vi.stubGlobal('fetch', fetchMock)

    await apiRequest('/api/v1/experiments', { method: 'POST', body: { name: 'test' } })
    const init = fetchMock.mock.calls[0][1]
    expect(init.body).toBe(JSON.stringify({ name: 'test' }))
    expect((init.headers as Headers).get('Content-Type')).toBe('application/json')
  })

  it('does not set a JSON content type for FormData', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ valid: true }))
    vi.stubGlobal('fetch', fetchMock)
    const form = new FormData()
    form.append('file', new Blob(['a,b\n1,2']), 'sample.csv')

    await apiRequest('/api/v1/datasets/validate', { method: 'POST', body: form })
    const init = fetchMock.mock.calls[0][1]
    expect((init.headers as Headers).get('Content-Type')).toBeNull()
    expect(init.body).toBe(form)
  })

  it('turns an error envelope into an ApiError', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse(
        { error: { code: 'unavailable', message: 'encryption is unavailable', details: { x: 1 } } },
        503,
      ),
    )
    vi.stubGlobal('fetch', fetchMock)

    await expect(apiRequest('/api/v1/experiments/x/start', { method: 'POST' })).rejects.toMatchObject({
      name: 'ApiError',
      status: 503,
      code: 'unavailable',
      message: 'encryption is unavailable',
      details: { x: 1 },
    })
  })

  it('reports a network failure without leaking an exception', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('failed to fetch')))

    await expect(apiRequest('/api/v1/health')).rejects.toBeInstanceOf(ApiError)
    await expect(apiRequest('/api/v1/health')).rejects.toMatchObject({
      status: 0,
      code: 'network_error',
    })
  })
})
