import { Cpu, Lock, Play, Plus, RefreshCw, Square } from 'lucide-react'
import { useEffect, useState, type FormEvent } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { Alert } from '../components/ui/Alert'
import { Button, buttonStyles } from '../components/ui/Button'
import { Card, CardBody, CardHeader } from '../components/ui/Card'
import { DataTable, type Column } from '../components/ui/DataTable'
import { Field, Select, TextInput } from '../components/ui/Field'
import { PageHeader } from '../components/ui/PageHeader'
import { ProgressBar } from '../components/ui/ProgressBar'
import { EmptyState, ErrorState, LoadingState } from '../components/ui/States'
import { StatusBadge } from '../components/ui/StatusBadge'
import { MetricBarChart, RoundLineChart } from '../components/ui/Charts'
import { MetricCard } from '../components/ui/MetricCard'
import { useApi } from '../hooks/useApi'
import { api } from '../lib/api'
import {
  describeError,
  formatDate,
  formatMetric,
  formatNumber,
  humanize,
  isActiveStatus,
} from '../lib/format'
import type {
  ExperimentResponse,
  FederatedResult,
  JobResponse,
} from '../lib/types'

export function TrainingPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const selectedId = searchParams.get('experiment')

  const experiments = useApi(() => api.listExperiments({ limit: 100 }), [])
  const datasets = useApi(() => api.listDatasets({ limit: 100 }), [])
  const status = useApi(
    () => (selectedId ? api.experimentStatus(selectedId) : Promise.resolve(null)),
    [selectedId],
  )
  const experiment = useApi(
    () => (selectedId ? api.getExperiment(selectedId) : Promise.resolve(null)),
    [selectedId],
  )

  const currentStatus = status.data && status.data.id === selectedId ? status.data : null
  const currentExperiment =
    experiment.data && experiment.data.id === selectedId ? experiment.data : null

  const [job, setJob] = useState<JobResponse | null>(null)
  const [name, setName] = useState('')
  const [datasetId, setDatasetId] = useState('')
  const [clientCount, setClientCount] = useState(4)
  const [paperSchedule, setPaperSchedule] = useState(false)
  const [creating, setCreating] = useState(false)
  const [action, setAction] = useState<'simulate' | 'train' | 'cancel' | null>(null)
  const [deleting, setDeleting] = useState<string | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  useEffect(() => {
    setJob(currentStatus?.job ?? null)
  }, [selectedId, currentStatus?.job?.id, currentStatus?.job?.status])

  useEffect(() => {
    if (!job || !isActiveStatus(job.status)) return
    let active = true
    const timer = window.setInterval(() => {
      api.getJob(job.id).then(
        (next) => {
          if (!active) return
          setJob(next)
          if (!isActiveStatus(next.status)) {
            status.reload()
            experiment.reload()
            experiments.reload()
          }
        },
        () => {
          // Keep the last known progress; the page-level error state covers
          // connection failures when the user retries.
        },
      )
    }, 1_500)
    return () => {
      active = false
      window.clearInterval(timer)
    }
  }, [job?.id, job?.status])

  const validDatasets = (datasets.data?.items ?? []).filter(
    (dataset) => dataset.validation_status === 'valid' && dataset.research_compatible,
  )
  const effectiveDatasetId = datasetId || validDatasets[0]?.id || ''
  const selectedExperiment =
    experiments.data?.items.find((item) => item.id === selectedId) ?? currentExperiment

  async function handleCreate(event: FormEvent) {
    event.preventDefault()
    setActionError(null)
    setNotice(null)
    if (!name.trim()) {
      setActionError('Experiment name is required.')
      return
    }
    if (!effectiveDatasetId) {
      setActionError('Upload and validate a research-compatible dataset first.')
      return
    }
    setCreating(true)
    try {
      const created = await api.createExperiment({
        name: name.trim(),
        dataset_id: effectiveDatasetId,
        client_count: clientCount,
      })
      setName('')
      setDatasetId('')
      setNotice(`Created experiment "${created.name}". Configure and start a run below.`)
      experiments.reload()
      setSearchParams({ experiment: created.id })
    } catch (error) {
      setActionError(describeError(error))
    } finally {
      setCreating(false)
    }
  }

  async function handleSimulate() {
    if (!selectedId) return
    setAction('simulate')
    setActionError(null)
    setNotice(null)
    try {
      const started = await api.simulateExperiment(selectedId)
      setJob(started)
      setNotice('Plaintext simulation queued. Progress updates automatically.')
      status.reload()
      experiments.reload()
    } catch (error) {
      setActionError(describeError(error))
    } finally {
      setAction(null)
    }
  }

  async function handleTrain() {
    if (!selectedId) return
    setAction('train')
    setActionError(null)
    setNotice(null)
    try {
      const started = await api.trainExperiment(selectedId, { rounds: paperSchedule ? 15 : 1, local_epochs: paperSchedule ? 5 : 1 })
      setJob(started)
      setNotice('Federated training job queued. Progress updates automatically.')
      status.reload()
      experiments.reload()
    } catch (error) {
      setActionError(describeError(error))
    } finally {
      setAction(null)
    }
  }

  async function handleCancel() {
    if (!selectedId) return
    setAction('cancel')
    setActionError(null)
    try {
      const updated = await api.cancelExperiment(selectedId)
      setJob(updated)
      setNotice('Cancellation requested. The worker stops between rounds or clients.')
      status.reload()
    } catch (error) {
      setActionError(describeError(error))
    } finally {
      setAction(null)
    }
  }

  async function handleDeleteExperiment(id: string) {
    setDeleting(id)
    setNotice(null)
    if (
      !window.confirm(
        `Are you sure you want to delete experiment "${id}"?\nThis will remove the experiment record and associated job data.`
      )
    ) {
      setDeleting(null)
      return
    }
    try {
      await api.deleteExperiment(id)
      setNotice(`Experiment ${id} has been deleted.`)
      experiments.reload()
      setDeleting(null)
    } catch (error) {
      setActionError(describeError(error))
      setDeleting(null)
    }
  }

  const columns: Column<ExperimentResponse>[] = [
    {
      key: 'name',
      header: 'Experiment',
      render: (row) => (
        <div className="min-w-0">
          <p className="truncate font-medium text-ink">{row.name}</p>
          <p className="mt-0.5 font-mono text-[11px] text-faint">{row.id}</p>
        </div>
      ),
    },
    {
      key: 'status',
      header: 'Status',
      render: (row) => <StatusBadge status={row.status} />,
    },
    {
      key: 'dataset',
      header: 'Dataset',
      render: (row) => (
        <span className="text-xs text-muted" title={row.dataset_id}>
          {datasets.data?.items.find((item) => item.id === row.dataset_id)?.name ?? row.dataset_id}
        </span>
      ),
    },
    {
      key: 'clients',
      header: 'Clients',
      render: (row) => <span className="font-mono text-xs">{row.client_count}</span>,
    },
    {
      key: 'updated',
      header: 'Updated',
      render: (row) => <span className="text-xs text-muted">{formatDate(row.updated_at)}</span>,
    },
    {
      key: 'action',
      header: '',
      headerClassName: 'text-right',
      className: 'text-right',
      render: (row) => (
        <div className="flex gap-1">
          <Button
            variant={row.id === selectedId ? 'secondary' : 'ghost'}
            size="sm"
            onClick={() => setSearchParams({ experiment: row.id })}
          >
            {row.id === selectedId ? 'Selected' : 'Select'}
          </Button>
          <Button
            variant="danger"
            size="sm"
            loading={deleting === row.id}
            onClick={() => handleDeleteExperiment(row.id)}
          >
            Delete
          </Button>
        </div>
      ),
    },
  ]

  const result =
    (job?.result as FederatedResult | null | undefined) ??
    (currentExperiment?.result as FederatedResult | null | undefined) ??
    null

  return (
    <div>
      <PageHeader
        eyebrow="Operations"
        title="Federated Training"
        description="Create experiments, run plaintext simulation or GRU training, and inspect results. Encrypted execution is admitted only when the backend reports TenSEAL CKKS available."
        actions={
          <Button
            variant="secondary"
            size="sm"
            onClick={() => {
              experiments.reload()
              datasets.reload()
              status.reload()
              experiment.reload()
            }}
            icon={<RefreshCw className="size-3.5" aria-hidden="true" />}
          >
            Refresh
          </Button>
        }
      />

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.5fr)]">
        <Card>
          <CardHeader
            title="Create an experiment"
            description="Only validated datasets with the 48-feature research schema are offered."
          />
          <CardBody>
            <form className="space-y-4" onSubmit={handleCreate}>
              <Field label="Experiment name" htmlFor="experiment-name" required>
                <TextInput
                  id="experiment-name"
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                  placeholder="e.g. InSDN 4-client baseline"
                  maxLength={120}
                />
              </Field>
              <Field
                label="Dataset"
                htmlFor="experiment-dataset"
                required
                hint={
                  datasets.error
                    ? datasets.error
                    : validDatasets.length === 0
                      ? 'No validated research-compatible dataset is available.'
                      : 'Only datasets marked valid and research compatible are listed.'
                }
              >
                <Select
                  id="experiment-dataset"
                  value={effectiveDatasetId}
                  onChange={(event) => setDatasetId(event.target.value)}
                  disabled={validDatasets.length === 0}
                >
                  {validDatasets.length === 0 ? (
                    <option value="">No eligible datasets</option>
                  ) : null}
                  {validDatasets.map((dataset) => (
                    <option key={dataset.id} value={dataset.id}>
                      {dataset.name} ({formatNumber(dataset.rows)} rows)
                    </option>
                  ))}
                </Select>
              </Field>
              <Field label="Clients" htmlFor="experiment-clients" required hint="Supported sizes: 2, 3, 4, 8, or 12.">
                <Select
                  id="experiment-clients"
                  value={clientCount}
                  onChange={(event) => setClientCount(Number(event.target.value))}
                >
                  <option value={2}>2 clients</option>
                  <option value={3}>3 clients</option>
                  <option value={4}>4 clients</option>
                  <option value={8}>8 clients</option>
                  <option value={12}>12 clients</option>
                </Select>
              </Field>

              {actionError ? <Alert tone="danger" title="Action failed">{actionError}</Alert> : null}
              {notice ? <Alert tone="success">{notice}</Alert> : null}

              <Button
                type="submit"
                loading={creating}
                disabledReason={
                  validDatasets.length === 0
                    ? 'Upload and validate a research-compatible dataset before creating an experiment.'
                    : undefined
                }
                icon={<Plus className="size-4" aria-hidden="true" />}
              >
                Create experiment
              </Button>
              {validDatasets.length === 0 ? (
                <Link to="/datasets" className={buttonStyles('ghost', 'sm')}>
                  Open datasets
                </Link>
              ) : null}
            </form>
          </CardBody>
        </Card>

        <Card>
          <CardHeader
            title="Experiment records"
            description={
              experiments.data
                ? `${formatNumber(experiments.data.total)} experiment record${experiments.data.total === 1 ? '' : 's'}.`
                : 'Loading experiment records.'
            }
          />
          {experiments.loading && !experiments.data ? (
            <LoadingState label="Loading experiments…" />
          ) : experiments.error ? (
            <CardBody>
              <ErrorState message={experiments.error} onRetry={experiments.reload} />
            </CardBody>
          ) : (experiments.data?.items.length ?? 0) === 0 ? (
            <EmptyState
              title="No experiments"
              description="Create an experiment to select it for a local run."
            />
          ) : (
            <DataTable
              columns={columns}
              rows={experiments.data?.items ?? []}
              rowKey={(row) => row.id}
              caption="Experiment records"
            />
          )}
        </Card>
      </div>

      <Card className="mt-6">
        <CardHeader
          title={selectedExperiment ? selectedExperiment.name : 'Experiment detail'}
          description={
            selectedId
              ? `Experiment ${selectedId}. Results appear only after a backend job completes.`
              : 'Select an experiment from the list to inspect its status and run controls.'
          }
          actions={
            selectedExperiment ? (
              <div className="flex items-center gap-2">
                <StatusBadge status={selectedExperiment.status} />
                <span className="text-xs text-faint">{selectedExperiment.client_count} clients</span>
              </div>
            ) : null
          }
        />
        {!selectedId ? (
          <EmptyState
            title="No experiment selected"
            description="Choose an experiment record to view its backend status, start controls, and results."
          />
        ) : status.error ? (
          <CardBody>
            <ErrorState message={status.error} onRetry={status.reload} />
          </CardBody>
        ) : (status.loading && !currentStatus) || (experiment.loading && !currentExperiment) ? (
          <LoadingState label="Loading experiment status…" />
        ) : currentStatus ? (
          <CardBody className="space-y-5">
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
              <MetricCard
                label="Execution"
                value={currentStatus.execution_available ? 'Available' : 'Unavailable'}
                hint={currentStatus.execution_reason}
                icon={<Lock className="size-4" />}
                tone={currentStatus.execution_available ? 'success' : 'warning'}
              />
              <MetricCard
                label="Simulation"
                value={currentStatus.simulation_available ? 'Available' : 'Unavailable'}
                hint={currentStatus.simulation_reason}
                icon={<Play className="size-4" />}
                tone={currentStatus.simulation_available ? 'success' : 'warning'}
              />
              <MetricCard
                label="GRU training"
                value={currentStatus.training_available ? 'Available' : 'Unavailable'}
                hint={
                  currentStatus.training_reason ??
                  'This backend build does not report a training backend.'
                }
                icon={<Cpu className="size-4" />}
                tone={currentStatus.training_available ? 'success' : 'warning'}
              />
              <MetricCard
                label="Dataset"
                value={
                  datasets.data?.items.find((item) => item.id === selectedExperiment?.dataset_id)
                    ?.name ?? '—'
                }
                hint={selectedExperiment?.dataset_id}
                icon={<Cpu className="size-4" />}
              />
            </div>

            <Field label="GRU training schedule" htmlFor="gru-schedule">
              <Select id="gru-schedule" value={paperSchedule ? 'paper' : 'short'}
                onChange={(event) => setPaperSchedule(event.target.value === 'paper')}>
                <option value="short">Quick check (1 round, 1 local epoch)</option>
                <option value="paper">Paper schedule (15 rounds, 5 local epochs)</option>
              </Select>
            </Field>

            <div className="flex flex-wrap items-start gap-2">
              <Button
                variant="secondary"
                disabledReason={
                  currentStatus.execution_reason || 'Encrypted execution is unavailable.'
                }
                icon={<Lock className="size-4" aria-hidden="true" />}
              >
                Start encrypted run
              </Button>
              <Button
                variant="primary"
                loading={action === 'train'}
                disabled={action !== null}
                disabledReason={
                  currentStatus.training_available
                    ? undefined
                    : currentStatus.training_reason ??
                      'The backend does not report a training backend for this experiment.'
                }
                onClick={handleTrain}
                icon={<Cpu className="size-4" aria-hidden="true" />}
              >
                Run GRU smoke training
              </Button>
              <Button
                variant="secondary"
                loading={action === 'simulate'}
                disabled={action !== null}
                disabledReason={
                  currentStatus.simulation_available
                    ? undefined
                    : currentStatus.simulation_reason || 'Plaintext simulation is unavailable.'
                }
                onClick={handleSimulate}
                icon={<Play className="size-4" aria-hidden="true" />}
              >
                Run plaintext simulation
              </Button>
              <Button
                variant="danger"
                loading={action === 'cancel'}
                disabled={action !== null}
                disabledReason={
                  job && isActiveStatus(job.status)
                    ? undefined
                    : 'There is no active job to cancel for this experiment.'
                }
                onClick={handleCancel}
                icon={<Square className="size-3.5" aria-hidden="true" />}
              >
                Cancel job
              </Button>
            </div>

            {actionError ? <Alert tone="danger" title="Run action failed">{actionError}</Alert> : null}
            {notice ? <Alert tone="success">{notice}</Alert> : null}

            <JobPanel job={job} onCancel={handleCancel} cancelBusy={action === 'cancel'} />

            {result ? (
              <ExperimentResult result={result} />
            ) : (
              <Alert tone="info" title="No result yet">
                A result is displayed only when the backend returns a completed job result or the
                experiment record already contains one. Nothing is generated in the browser.
              </Alert>
            )}
          </CardBody>
        ) : (
          <EmptyState
            title="Experiment status unavailable"
            description="The backend did not return a status record for the selected experiment."
          />
        )}
      </Card>
    </div>
  )
}

function JobPanel({
  job,
  onCancel,
  cancelBusy,
}: {
  job: JobResponse | null
  onCancel: () => void
  cancelBusy: boolean
}) {
  if (!job) {
    return (
      <div className="rounded-lg border border-line bg-navy-950/50 px-4 py-3">
        <p className="text-sm font-medium text-ink">No background job</p>
        <p className="mt-1 text-xs text-muted">
          Start a run to create a queued job. Progress is read from the job endpoint.
        </p>
      </div>
    )
  }

  return (
    <div className="rounded-lg border border-line bg-navy-950/50 p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-sm font-semibold text-ink">Background job</p>
            <StatusBadge status={job.status} />
            <span className="font-mono text-[11px] text-faint">{job.job_type}</span>
          </div>
          <p className="mt-1 font-mono text-[11px] text-faint">{job.id}</p>
        </div>
        <Button
          variant="danger"
          size="sm"
          loading={cancelBusy}
          disabled={!isActiveStatus(job.status)}
          disabledReason={
            isActiveStatus(job.status) ? undefined : 'Only queued or running jobs can be cancelled.'
          }
          onClick={onCancel}
        >
          Cancel
        </Button>
      </div>
      <div className="mt-3">
        <ProgressBar value={job.progress} label={job.message ?? humanize(job.status)} />
      </div>
      {job.error ? (
        <Alert tone="danger" className="mt-3" title="Job error">
          {job.error}
        </Alert>
      ) : null}
      <p className="mt-2 text-[11px] text-faint">
        Created {formatDate(job.created_at)} · finished {formatDate(job.finished_at)}
      </p>
    </div>
  )
}

function ExperimentResult({ result }: { result: FederatedResult }) {
  const metrics = result.final_metrics ?? null
  const rounds = result.rounds ?? []
  const metricEntries = metrics
    ? Object.entries(metrics).filter(([, value]) => typeof value === 'number')
    : []
  const roundMetric = rounds.some((round) => typeof round.metrics?.accuracy === 'number')
    ? 'accuracy'
    : 'f1_score'
  const roundRows = rounds.filter((round) => round.metrics && Object.keys(round.metrics).length > 0)

  return (
    <div className="space-y-4">
      <Alert
        tone={result.encrypted ? 'success' : 'warning'}
        title={result.encrypted ? 'Encrypted result reported' : 'Plaintext result — not encrypted federated learning'}
      >
        Mode: {humanize(result.mode)} · encrypted: {String(Boolean(result.encrypted))} · parity:{' '}
        {result.parity ?? 'unverified'}.{' '}
        {result.encrypted
          ? 'TenSEAL CKKS encryption, homomorphic aggregation, and client-side decryption executed for this run. Metric parity with the paper is still unverified.'
          : 'No CKKS encryption was performed. This is not a legacy-parity claim.'}
      </Alert>

      <div className="flex flex-wrap items-center gap-2 text-xs text-muted">
        <StatusBadge
          tone={result.model?.research_model ? 'info' : 'warning'}
          label={result.model?.name ?? 'unknown model'}
        />
        <span>{formatNumber(result.model?.parameter_count ?? 0)} parameters</span>
        {result.aggregate_digest ? (
          <span className="font-mono text-faint">
            aggregate {result.aggregate_digest.slice(0, 20)}…
          </span>
        ) : null}
      </div>

      {metricEntries.length > 0 ? (
        <>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {metricEntries.slice(0, 8).map(([key, value]) => (
              <MetricCard key={key} label={humanize(key)} value={formatMetric(key, value)} />
            ))}
          </div>
          <div className="rounded-lg border border-line bg-navy-950/40 p-4">
            <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-faint">
              Final metrics
            </p>
            <MetricBarChart metrics={metrics} />
            {metricEntries.every(([key]) => !['accuracy', 'precision', 'recall', 'f1'].includes(key)) ? (
              <p className="text-xs text-muted">No core classification metrics were returned.</p>
            ) : null}
          </div>
        </>
      ) : (
        <Alert tone="info">The backend returned no final metrics for this run.</Alert>
      )}

      {roundRows.length > 0 ? (
        <div className="rounded-lg border border-line bg-navy-950/40 p-4">
          <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
            <p className="text-xs font-semibold uppercase tracking-wider text-faint">
              Evaluation by round
            </p>
            <span className="text-[11px] text-faint">
              {roundRows.length} round{roundRows.length === 1 ? '' : 's'}
            </span>
          </div>
          <RoundLineChart rounds={rounds} metric={roundMetric} />
          <div className="mt-4 overflow-x-auto">
            <table className="w-full min-w-[640px] border-collapse text-left text-sm">
              <caption className="sr-only">Per-round aggregation and metrics</caption>
              <thead>
                <tr className="border-b border-line text-[11px] uppercase tracking-wider text-faint">
                  <th scope="col" className="px-3 py-2">Round</th>
                  <th scope="col" className="px-3 py-2">Aggregation</th>
                  <th scope="col" className="px-3 py-2">Digest</th>
                  <th scope="col" className="px-3 py-2">Accuracy</th>
                  <th scope="col" className="px-3 py-2">F1</th>
                  <th scope="col" className="px-3 py-2">Note</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line/70">
                {roundRows.map((round) => (
                  <tr key={round.round}>
                    <td className="px-3 py-2 font-mono text-xs">{round.round + 1}</td>
                    <td className="px-3 py-2">
                      <StatusBadge
                        tone={round.aborted ? 'warning' : 'success'}
                        label={round.aborted ? 'Aborted' : 'Aggregated'}
                      />
                    </td>
                    <td className="px-3 py-2 font-mono text-[11px] text-muted">
                      {round.aggregate_digest ? `${round.aggregate_digest.slice(0, 16)}…` : '—'}
                    </td>
                    <td className="px-3 py-2 font-mono text-xs">
                      {formatMetric('accuracy', round.metrics?.accuracy)}
                    </td>
                    <td className="px-3 py-2 font-mono text-xs">
                      {formatMetric('f1', round.metrics?.f1_score ?? round.metrics?.f1)}
                    </td>
                    <td className="px-3 py-2 text-xs text-muted">
                      {round.reason ?? round.metrics_note ?? '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : (
        <Alert tone="info">No per-round metrics were returned. Only the final metrics are shown.</Alert>
      )}

      {result.artifact ? (
        <details className="rounded-lg border border-line bg-navy-950/40 p-4">
          <summary className="cursor-pointer text-xs font-semibold uppercase tracking-wider text-faint">
            Artifact metadata
          </summary>
          <pre className="mt-3 max-h-64 overflow-auto rounded-md bg-navy-950 p-3 font-mono text-[11px] leading-5 text-muted">
            {JSON.stringify(result.artifact, null, 2)}
          </pre>
        </details>
      ) : null}

      {result.legacy_differences && result.legacy_differences.length > 0 ? (
        <details className="rounded-lg border border-line bg-navy-950/40 p-4">
          <summary className="cursor-pointer text-xs font-semibold uppercase tracking-wider text-faint">
            Known differences from the research scripts
          </summary>
          <ul className="mt-3 space-y-1.5 text-xs leading-5 text-muted">
            {result.legacy_differences.map((difference) => (
              <li key={difference} className="flex gap-2">
                <span className="mt-2 size-1 shrink-0 rounded-full bg-faint" aria-hidden="true" />
                <span>{difference}</span>
              </li>
            ))}
          </ul>
        </details>
      ) : null}
    </div>
  )
}
