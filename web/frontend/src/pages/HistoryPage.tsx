import { History, RefreshCw } from 'lucide-react'
import { useState } from 'react'
import { Alert } from '../components/ui/Alert'
import { Button } from '../components/ui/Button'
import { Card, CardBody, CardHeader } from '../components/ui/Card'
import { DataTable, type Column } from '../components/ui/DataTable'
import { Select } from '../components/ui/Field'
import { PageHeader } from '../components/ui/PageHeader'
import { ProgressBar } from '../components/ui/ProgressBar'
import { EmptyState, ErrorState, LoadingState } from '../components/ui/States'
import { StatusBadge } from '../components/ui/StatusBadge'
import { useApi } from '../hooks/useApi'
import { api } from '../lib/api'
import { formatDate, humanize, isActiveStatus } from '../lib/format'
import type { ExperimentResponse, JobResponse } from '../lib/types'

type Filter = 'all' | 'active' | 'succeeded' | 'failed'

export function HistoryPage() {
  const experiments = useApi(() => api.listExperiments({ limit: 200 }), [])
  const datasets = useApi(() => api.listDatasets({ limit: 100 }), [])
  const jobs = useApi(() => api.listJobs({ limit: 200 }), [])
  const [filter, setFilter] = useState<Filter>('all')
  const [selectedId, setSelectedId] = useState<string | null>(null)

  const rows = experiments.data?.items ?? []
  const filtered = rows.filter((experiment) => {
    if (filter === 'all') return true
    if (filter === 'active') return isActiveStatus(experiment.status)
    return experiment.status === filter
  })
  const selected = rows.find((experiment) => experiment.id === selectedId) ?? null

  const experimentColumns: Column<ExperimentResponse>[] = [
    {
      key: 'name',
      header: 'Experiment',
      render: (row) => (
        <div className="min-w-0">
          <p className="truncate font-medium text-ink">{row.name}</p>
          <p className="mt-0.5 font-mono text-[11px] text-faint">
            {datasets.data?.items.find((item) => item.id === row.dataset_id)?.name ?? row.dataset_id}
          </p>
        </div>
      ),
    },
    {
      key: 'status',
      header: 'Status',
      render: (row) => <StatusBadge status={row.status} />,
    },
    {
      key: 'clients',
      header: 'Clients',
      render: (row) => <span className="font-mono text-xs">{row.client_count}</span>,
    },
    {
      key: 'created',
      header: 'Created',
      render: (row) => <span className="text-xs text-muted">{formatDate(row.created_at)}</span>,
    },
    {
      key: 'finished',
      header: 'Finished',
      render: (row) => <span className="text-xs text-muted">{formatDate(row.finished_at)}</span>,
    },
    {
      key: 'job',
      header: 'Job',
      render: (row) =>
        row.job_id ? (
          <code className="font-mono text-[11px] text-muted">{row.job_id.slice(0, 12)}…</code>
        ) : (
          <span className="text-xs text-faint">—</span>
        ),
    },
    {
      key: 'action',
      header: '',
      headerClassName: 'text-right',
      className: 'text-right',
      render: (row) => (
        <Button
          variant={row.id === selectedId ? 'secondary' : 'ghost'}
          size="sm"
          onClick={() => setSelectedId(row.id === selectedId ? null : row.id)}
        >
          {row.id === selectedId ? 'Hide' : 'Details'}
        </Button>
      ),
    },
  ]

  const jobColumns: Column<JobResponse>[] = [
    {
      key: 'job',
      header: 'Job',
      render: (row) => (
        <div className="min-w-0">
          <p className="font-mono text-xs text-ink">{row.job_type}</p>
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
      key: 'progress',
      header: 'Progress',
      render: (row) => (
        <div className="min-w-[120px] max-w-[180px]">
          <ProgressBar value={row.progress} />
        </div>
      ),
    },
    {
      key: 'message',
      header: 'Message',
      render: (row) => (
        <span className="text-xs text-muted" title={row.error ?? row.message ?? undefined}>
          {row.error ?? row.message ?? '—'}
        </span>
      ),
    },
    {
      key: 'experiment',
      header: 'Experiment',
      render: (row) =>
        row.experiment_id ? (
          <button
            type="button"
            className="font-mono text-[11px] text-cyan-300 hover:underline"
            onClick={() => setSelectedId(row.experiment_id)}
          >
            {row.experiment_id.slice(0, 12)}…
          </button>
        ) : (
          <span className="text-xs text-faint">—</span>
        ),
    },
    {
      key: 'created',
      header: 'Created',
      render: (row) => <span className="text-xs text-muted">{formatDate(row.created_at)}</span>,
    },
  ]

  return (
    <div>
      <PageHeader
        eyebrow="Operations"
        title="Experiment History"
        description="Persisted experiment and job records. Detail panels show the stored configuration, error, and result without recomputing anything."
        actions={
          <Button
            variant="secondary"
            size="sm"
            onClick={() => {
              experiments.reload()
              datasets.reload()
              jobs.reload()
            }}
            icon={<RefreshCw className="size-3.5" aria-hidden="true" />}
          >
            Refresh
          </Button>
        }
      />

      <Card>
        <CardHeader
          title="Experiments"
          description={
            experiments.data
              ? `${filtered.length} of ${experiments.data.total} experiment record${experiments.data.total === 1 ? '' : 's'} shown.`
              : 'Loading experiment records.'
          }
          actions={
            <div className="flex items-center gap-2">
              <label htmlFor="history-filter" className="text-xs text-muted">
                Filter
              </label>
              <Select
                id="history-filter"
                value={filter}
                onChange={(event) => setFilter(event.target.value as Filter)}
                className="h-8 w-36 py-1 text-xs"
              >
                <option value="all">All</option>
                <option value="active">Active</option>
                <option value="succeeded">Succeeded</option>
                <option value="failed">Failed</option>
              </Select>
            </div>
          }
        />
        {experiments.loading && !experiments.data ? (
          <LoadingState label="Loading history…" />
        ) : experiments.error ? (
          <CardBody>
            <ErrorState message={experiments.error} onRetry={experiments.reload} />
          </CardBody>
        ) : filtered.length === 0 ? (
          <EmptyState
            title="No matching experiments"
            description="Change the filter or create a new experiment from Federated Training."
            icon={<History className="size-5" aria-hidden="true" />}
          />
        ) : (
          <DataTable
            columns={experimentColumns}
            rows={filtered}
            rowKey={(row) => row.id}
            caption="Experiment history"
          />
        )}
      </Card>

      {selected ? (
        <Card className="mt-4">
          <CardHeader
            title={`Details: ${selected.name}`}
            description={`Experiment ${selected.id}`}
            actions={<StatusBadge status={selected.status} />}
          />
          <CardBody className="space-y-4">
            {selected.error ? (
              <Alert tone="danger" title="Stored experiment error">
                {selected.error}
              </Alert>
            ) : null}
            <div className="grid gap-4 lg:grid-cols-2">
              <div>
                <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-faint">
                  Configuration
                </p>
                <pre className="max-h-72 overflow-auto rounded-lg bg-navy-950 p-3 font-mono text-[11px] leading-5 text-muted">
                  {JSON.stringify(selected.config, null, 2)}
                </pre>
              </div>
              <div>
                <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-faint">
                  Result
                </p>
                {selected.result ? (
                  <pre className="max-h-72 overflow-auto rounded-lg bg-navy-950 p-3 font-mono text-[11px] leading-5 text-muted">
                    {JSON.stringify(selected.result, null, 2)}
                  </pre>
                ) : (
                  <p className="rounded-lg border border-line bg-navy-950/60 px-3 py-4 text-xs text-muted">
                    No result stored for this experiment.
                  </p>
                )}
              </div>
            </div>
            <dl className="grid gap-3 text-xs sm:grid-cols-3">
              <div>
                <dt className="text-faint">Created</dt>
                <dd className="mt-0.5 text-ink">{formatDate(selected.created_at)}</dd>
              </div>
              <div>
                <dt className="text-faint">Started</dt>
                <dd className="mt-0.5 text-ink">{formatDate(selected.started_at)}</dd>
              </div>
              <div>
                <dt className="text-faint">Finished</dt>
                <dd className="mt-0.5 text-ink">{formatDate(selected.finished_at)}</dd>
              </div>
            </dl>
          </CardBody>
        </Card>
      ) : null}

      <Card className="mt-4">
        <CardHeader
          title="Background jobs"
          description={
            jobs.data
              ? `${jobs.data.total} job record${jobs.data.total === 1 ? '' : 's'}, newest first.`
              : 'Loading job records.'
          }
        />
        {jobs.loading && !jobs.data ? (
          <LoadingState label="Loading jobs…" />
        ) : jobs.error ? (
          <CardBody>
            <ErrorState message={jobs.error} onRetry={jobs.reload} />
          </CardBody>
        ) : (jobs.data?.items.length ?? 0) === 0 ? (
          <EmptyState
            title="No background jobs"
            description="Jobs appear after a simulation or training run is queued."
          />
        ) : (
          <DataTable
            columns={jobColumns}
            rows={jobs.data?.items ?? []}
            rowKey={(row) => row.id}
            caption="Background job history"
          />
        )}
      </Card>

      <p className="mt-4 text-[11px] text-faint">
        Status values come directly from stored enums; {humanize('cancellation_requested')} is shown
        until the worker observes cancellation.
      </p>
    </div>
  )
}
