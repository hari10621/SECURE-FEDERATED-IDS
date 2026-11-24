import { loadApiConfig } from './config'
import type {
  ClientListResponse,
  ClientResponse,
  ClientStatus,
  ClientStatusResponse,
  DatasetListResponse,
  DatasetResponse,
  DatasetType,
  DatasetValidationReport,
  EncryptionStatusResponse,
  ErrorEnvelope,
  ExperimentListResponse,
  ExperimentMetricsResponse,
  ExperimentResponse,
  ExperimentStatusResponse,
  HealthResponse,
  JobListResponse,
  JobResponse,
  PredictionStatusResponse,
  SdnStatusResponse,
  SimulationRequest,
  TrainingRequest,
  VersionResponse,
} from './types'

export class ApiError extends Error {
  readonly status: number
  readonly code: string
  readonly details: unknown

  constructor(message: string, options: { status?: number; code?: string; details?: unknown } = {}) {
    super(message)
    this.name = 'ApiError'
    this.status = options.status ?? 0
    this.code = options.code ?? 'request_failed'
    this.details = options.details
  }
}

export interface RequestOptions extends Omit<RequestInit, 'body'> {
  body?: unknown
  timeoutMs?: number
}

function isFormData(value: unknown): value is FormData {
  return typeof FormData !== 'undefined' && value instanceof FormData
}

function parseEnvelope(raw: string, status: number): ApiError {
  try {
    const payload = JSON.parse(raw) as Partial<ErrorEnvelope>
    const detail = payload.error
    if (detail && typeof detail.message === 'string') {
      return new ApiError(detail.message, {
        status,
        code: detail.code ?? 'request_failed',
        details: detail.details,
      })
    }
  } catch {
    // Fall through to a generic message below.
  }
  return new ApiError(raw.trim() || `Request failed with status ${status}.`, {
    status,
    code: 'request_failed',
  })
}

export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const config = loadApiConfig()
  const { body, timeoutMs = 30_000, headers: rawHeaders, signal, ...rest } = options
  const headers = new Headers(rawHeaders)

  let requestBody: BodyInit | undefined
  if (body !== undefined) {
    if (isFormData(body)) {
      requestBody = body
    } else {
      headers.set('Content-Type', 'application/json')
      requestBody = JSON.stringify(body)
    }
  }
  if (config.token) {
    headers.set('Authorization', `Bearer ${config.token}`)
  }
  headers.set('Accept', 'application/json')

  const controller = new AbortController()
  const timer = window.setTimeout(() => controller.abort(), timeoutMs)
  if (signal) {
    if (signal.aborted) controller.abort()
    else signal.addEventListener('abort', () => controller.abort(), { once: true })
  }

  let response: Response
  try {
    response = await fetch(`${config.baseUrl}${path}`, {
      ...rest,
      headers,
      body: requestBody,
      signal: controller.signal,
    })
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw new ApiError('The request timed out or was cancelled.', {
        status: 0,
        code: 'timeout',
      })
    }
    throw new ApiError(
      'Could not reach the backend. Start the local API and check the base URL in Settings.',
      { status: 0, code: 'network_error' },
    )
  } finally {
    window.clearTimeout(timer)
  }

  const raw = await response.text()
  if (!response.ok) {
    throw parseEnvelope(raw, response.status)
  }
  if (!raw) {
    return undefined as T
  }
  try {
    return JSON.parse(raw) as T
  } catch {
    throw new ApiError('The backend returned a response that was not valid JSON.', {
      status: response.status,
      code: 'invalid_response',
    })
  }
}

function query(params: Record<string, string | number | undefined>): string {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== '') search.set(key, String(value))
  }
  const text = search.toString()
  return text ? `?${text}` : ''
}

export interface UploadDatasetInput {
  file: File
  datasetType: DatasetType
  name?: string
  labelColumn?: string
}

export const api = {
  health: () => apiRequest<HealthResponse>('/api/v1/health'),
  version: () => apiRequest<VersionResponse>('/api/v1/version'),
  encryptionStatus: () => apiRequest<EncryptionStatusResponse>('/api/v1/encryption/status'),
  sdnStatus: () => apiRequest<SdnStatusResponse>('/api/v1/sdn/status'),
  predictionStatus: () =>
    apiRequest<PredictionStatusResponse>('/api/v1/predictions/status'),

  listDatasets: (params: { limit?: number; offset?: number } = {}) =>
    apiRequest<DatasetListResponse>(`/api/v1/datasets${query(params)}`),
  getDataset: (id: string) => apiRequest<DatasetResponse>(`/api/v1/datasets/${id}`),
  validateDataset: (file: File, labelColumn?: string) => {
    const form = new FormData()
    form.append('file', file)
    if (labelColumn) form.append('label_column', labelColumn)
    return apiRequest<DatasetValidationReport>('/api/v1/datasets/validate', {
      method: 'POST',
      body: form,
      timeoutMs: 300_000,
    })
  },
  uploadDataset: ({ file, datasetType, name, labelColumn }: UploadDatasetInput) => {
    const form = new FormData()
    form.append('file', file)
    form.append('dataset_type', datasetType)
    if (name) form.append('name', name)
    if (labelColumn) form.append('label_column', labelColumn)
    return apiRequest<DatasetResponse>('/api/v1/datasets', {
      method: 'POST',
      body: form,
      timeoutMs: 300_000,
    })
  },
  revalidateDataset: (id: string) =>
    apiRequest<DatasetValidationReport>(`/api/v1/datasets/${id}/validate`, { method: 'POST' }),

  listExperiments: (params: { limit?: number; offset?: number } = {}) =>
    apiRequest<ExperimentListResponse>(`/api/v1/experiments${query(params)}`),
  getExperiment: (id: string) => apiRequest<ExperimentResponse>(`/api/v1/experiments/${id}`),
  experimentStatus: (id: string) =>
    apiRequest<ExperimentStatusResponse>(`/api/v1/experiments/${id}/status`),
  experimentMetrics: (id: string) =>
    apiRequest<ExperimentMetricsResponse>(`/api/v1/experiments/${id}/metrics`),
  createExperiment: (payload: {
    name: string
    dataset_id: string
    client_count: number
    config?: Record<string, unknown>
  }) =>
    apiRequest<ExperimentResponse>('/api/v1/experiments', {
      method: 'POST',
      body: { config: {}, ...payload },
    }),
  startExperiment: (id: string) =>
    apiRequest<JobResponse>(`/api/v1/experiments/${id}/start`, { method: 'POST' }),
  simulateExperiment: (id: string, payload: SimulationRequest = {}) =>
    apiRequest<JobResponse>(`/api/v1/experiments/${id}/simulate`, {
      method: 'POST',
      body: payload,
    }),
  trainExperiment: (id: string, payload: TrainingRequest = {}) =>
    apiRequest<JobResponse>(`/api/v1/experiments/${id}/train`, {
      method: 'POST',
      body: payload,
      timeoutMs: 60_000,
    }),
  cancelExperiment: (id: string) =>
    apiRequest<JobResponse>(`/api/v1/experiments/${id}/cancel`, { method: 'POST' }),

  listJobs: (params: { experimentId?: string; limit?: number } = {}) =>
    apiRequest<JobListResponse>(
      `/api/v1/jobs${query({ experiment_id: params.experimentId, limit: params.limit })}`,
    ),
  getJob: (id: string) => apiRequest<JobResponse>(`/api/v1/jobs/${id}`),
  cancelJob: (id: string) =>
    apiRequest<JobResponse>(`/api/v1/jobs/${id}/cancel`, { method: 'POST' }),

  listClients: (params: { limit?: number; offset?: number } = {}) =>
    apiRequest<ClientListResponse>(`/api/v1/clients${query(params)}`),
  getClient: (id: string) => apiRequest<ClientResponse>(`/api/v1/clients/${id}`),
  createClient: (payload: { name: string; config?: Record<string, unknown> }) =>
    apiRequest<ClientResponse>('/api/v1/clients', { method: 'POST', body: payload }),
  updateClient: (id: string, payload: { status?: ClientStatus; config?: Record<string, unknown> }) =>
    apiRequest<ClientResponse>(`/api/v1/clients/${id}`, { method: 'PATCH', body: payload }),
  clientStatus: (id: string) =>
    apiRequest<ClientStatusResponse>(`/api/v1/clients/${id}/status`),

  predict: (features: number[]) =>
    apiRequest<void>('/api/v1/predictions', { method: 'POST', body: { features } }),
}
