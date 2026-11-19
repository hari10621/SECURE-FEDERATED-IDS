export type DatasetType = 'insdn' | 'cicids2017' | 'cicids2019'
export type ValidationStatus = 'valid' | 'invalid'
export type ClientStatus = 'configured' | 'enabled' | 'disabled'
export type ExperimentStatus =
  | 'created'
  | 'queued'
  | 'running'
  | 'cancellation_requested'
  | 'succeeded'
  | 'failed'
  | 'cancelled'
export type JobStatus =
  | 'queued'
  | 'running'
  | 'cancellation_requested'
  | 'succeeded'
  | 'failed'
  | 'cancelled'

export interface HealthResponse {
  status: 'ok' | 'degraded'
  version: string
  database: string
  encryption: string
  timestamp: string
}

export interface VersionResponse {
  name: string
  version: string
  api_version: string
  environment: string
  python_version: string
}

export interface EncryptionStatusResponse {
  available: boolean
  backend: string
  reason: string
}

export interface SdnStatusResponse {
  available: boolean
  reason: string
}

export interface PredictionStatusResponse {
  available: boolean
  reason: string
  model: string | null
  preprocessing: string | null
}

export interface DatasetValidationReport {
  valid: boolean
  rows: number
  columns: number
  feature_count: number
  label_column: string
  label_column_index: number
  label_counts: Record<string, number>
  warnings: string[]
  errors: string[]
  research_compatible: boolean
}

export interface DatasetResponse {
  id: string
  name: string
  dataset_type: DatasetType
  original_filename: string
  sha256: string
  size_bytes: number
  rows: number
  columns: number
  feature_count: number
  label_column: string
  label_column_index: number
  label_counts: Record<string, number>
  validation_status: ValidationStatus
  validation_errors: string[]
  warnings: string[]
  research_compatible: boolean
  created_at: string
}

export interface DatasetListResponse {
  items: DatasetResponse[]
  total: number
}

export interface ExperimentResponse {
  id: string
  name: string
  dataset_id: string
  client_count: number
  status: ExperimentStatus
  config: Record<string, unknown>
  result: Record<string, unknown> | null
  error: string | null
  job_id: string | null
  created_at: string
  updated_at: string
  started_at: string | null
  finished_at: string | null
}

export interface ExperimentListResponse {
  items: ExperimentResponse[]
  total: number
}

export interface ExperimentStatusResponse {
  id: string
  status: ExperimentStatus
  execution_available: boolean
  execution_reason: string
  simulation_available: boolean
  simulation_reason: string
  training_available?: boolean
  training_reason?: string
  job: JobResponse | null
}

export interface JobResponse {
  id: string
  job_type: string
  status: JobStatus
  progress: number
  message: string | null
  result: Record<string, unknown> | null
  error: string | null
  cancel_requested: boolean
  experiment_id: string | null
  created_at: string
  started_at: string | null
  finished_at: string | null
}

export interface JobListResponse {
  items: JobResponse[]
  total: number
}

export interface ClientResponse {
  id: string
  name: string
  status: ClientStatus
  config: Record<string, unknown>
  created_at: string
  updated_at: string
}

export interface ClientListResponse {
  items: ClientResponse[]
  total: number
}

export interface ClientStatusResponse {
  id: string
  status: ClientStatus
  runtime_connected: boolean
  detail: string
}

export interface SimulationRequest {
  mode?: 'legacy' | 'clean'
  rounds?: number
  local_epochs?: number
  batch_size?: number
  learning_rate?: number
  weighting?: 'sample' | 'legacy'
  seed?: number
  test_size?: number
  byzantine_check?: boolean
}

export interface TrainingRequest extends SimulationRequest {
  byzantine_threshold?: number
  threshold?: number
  require_encryption?: boolean
  max_rows?: number
}

export type MetricValue = number | null

export interface FederatedRound {
  round: number
  updates: Array<Record<string, unknown>>
  scaling_factors: number[]
  aggregate_digest: string
  aborted: boolean
  reason: string | null
  byzantine_flagged: string[]
  metrics: Record<string, MetricValue> | null
  metrics_note?: string
}

export interface FederatedResult {
  mode: string
  encrypted: boolean
  encryption_claimed?: boolean
  crypto?: EncryptionStatusResponse
  model?: {
    name: string
    research_model: boolean
    parameter_count: number
  }
  parity?: string
  parity_note?: string
  legacy_differences?: string[]
  config?: Record<string, unknown>
  dataset?: Record<string, unknown>
  rounds?: FederatedRound[]
  final_metrics?: Record<string, MetricValue> | null
  final_metrics_note?: string | null
  aggregate_digest?: string
  artifact?: Record<string, unknown>
  [key: string]: unknown
}

export interface ErrorDetail {
  code: string
  message: string
  details?: unknown
}

export interface ErrorEnvelope {
  error: ErrorDetail
}
