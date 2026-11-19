import { BarChart3, RefreshCw } from 'lucide-react'
import { Link } from 'react-router-dom'
import { Alert } from '../components/ui/Alert'
import { Button, buttonStyles } from '../components/ui/Button'
import { Card, CardBody, CardHeader } from '../components/ui/Card'
import { DataTable, type Column } from '../components/ui/DataTable'
import { MetricBarChart, RoundLineChart } from '../components/ui/Charts'
import { MetricCard } from '../components/ui/MetricCard'
import { PageHeader } from '../components/ui/PageHeader'
import { EmptyState, ErrorState, LoadingState } from '../components/ui/States'
import { StatusBadge } from '../components/ui/StatusBadge'
import { useApi } from '../hooks/useApi'
import { api } from '../lib/api'
import { formatDate, formatMetric, formatNumber, humanize } from '../lib/format'
import type { ExperimentResponse, FederatedResult } from '../lib/types'

function completedResult(experiment: ExperimentResponse): FederatedResult | null {
  if (experiment.status !== 'succeeded' || !experiment.result) return null
  const result = experiment.result as FederatedResult
  if (!result.final_metrics || typeof result.final_metrics !== 'object') return null
  return result
}

export function PerformancePage() {
  const experiments = useApi(() => api.listExperiments({ limit: 200 }), [])
  const datasets = useApi(() => api.listDatasets({ limit: 100 }), [])
  const rows = experiments.data?.items ?? []
  const completed = rows.filter((experiment) => completedResult(experiment) !== null)
  const latest = completed[0]
  const latestResult = latest ? completedResult(latest) : null
  const rounds = latestResult?.rounds ?? []
  const roundMetric = rounds.some((round) => typeof round.metrics?.accuracy === 'number')
    ? 'accuracy'
    : 'f1'

  const columns: Column<ExperimentResponse>[] = [
    {
      key: 'name',
      header: 'Experiment',
      render: (row) => {
        const result = completedResult(row)
        return (
          <div className="min-w-0">
            <p className="truncate font-medium text-ink">{row.name}</p>
            <p className="mt-0.5 font-mono text-[11px] text-faint">
              {datasets.data?.items.find((item) => item.id === row.dataset_id)?.name ?? row.dataset_id}
            </p>
            {result ? null : <span className="text-[11px] text-faint">No result</span>}
          </div>
        )
      },
    },
    {
      key: 'mode',
      header: 'Mode',
      render: (row) => {
        const result = completedResult(row)
        return (
          <div>
            <StatusBadge
              tone={result?.encrypted ? 'success' : 'warning'}
              label={result ? humanize(result.mode) : '—'}
            />
            {result ? (
              <p className="mt-1 text-[11px] text-faint">{result.model?.name ?? 'unknown model'}</p>
            ) : null}
          </div>
        )
      },
    },
    {
      key: 'accuracy',
      header: 'Accuracy',
      render: (row) => (
        <span className="font-mono text-xs">
          {formatMetric('accuracy', completedResult(row)?.final_metrics?.accuracy)}
        </span>
      ),
    },
    {
      key: 'f1',
      header: 'F1',
      render: (row) => (
        <span className="font-mono text-xs">
          {formatMetric('f1', completedResult(row)?.final_metrics?.f1)}
        </span>
      ),
    },
    {
      key: 'encrypted',
      header: 'Encrypted',
      render: (row) => (
        <StatusBadge
          tone={completedResult(row)?.encrypted ? 'success' : 'warning'}
          label={completedResult(row)?.encrypted ? 'Reported' : 'No'}
        />
      ),
    },
    {
      key: 'finished',
      header: 'Finished',
      render: (row) => (
        <span className="text-xs text-muted">{formatDate(row.finished_at ?? row.updated_at)}</span>
      ),
    },
    {
      key: 'action',
      header: '',
      headerClassName: 'text-right',
      className: 'text-right',
      render: (row) => (
        <Link
          to={`/training?experiment=${encodeURIComponent(row.id)}`}
          className={buttonStyles('ghost', 'sm')}
        >
          Open
        </Link>
      ),
    },
  ]

  return (
    <div>
      <PageHeader
        eyebrow="Evaluation"
        title="Performance Evaluation"
        description="Metrics are read from completed experiment records. The console does not compute, estimate, or backfill missing scores."
        actions={
          <Button
            variant="secondary"
            size="sm"
            onClick={() => {
              experiments.reload()
              datasets.reload()
            }}
            icon={<RefreshCw className="size-3.5" aria-hidden="true" />}
          >
            Refresh
          </Button>
        }
      />

      {experiments.loading && !experiments.data ? (
        <LoadingState label="Loading experiment results…" />
      ) : experiments.error ? (
        <ErrorState message={experiments.error} onRetry={experiments.reload} />
      ) : completed.length === 0 ? (
        <Card>
          <EmptyState
            title="No completed metrics"
            description="A metric appears only after a backend job succeeds and stores final_metrics. Run a plaintext simulation or an available GRU training job first."
            icon={<BarChart3 className="size-5" aria-hidden="true" />}
            action={
              <Link to="/training" className={buttonStyles('primary', 'sm')}>
                Open federated training
              </Link>
            }
          />
        </Card>
      ) : (
        <>
          <Alert tone={latestResult?.encrypted ? 'success' : 'warning'} className="mb-4" title="Local result scope">
            Showing the latest of {formatNumber(completed.length)} completed{' '}
            {completed.length === 1 ? 'experiment' : 'experiments'}. Mode:{' '}
            {humanize(latestResult?.mode)} · encrypted: {String(Boolean(latestResult?.encrypted))} ·
            parity: {latestResult?.parity ?? 'unverified'}. These are not paper-level or
            production-performance claims.
          </Alert>

          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            {latestResult?.final_metrics
              ? Object.entries(latestResult.final_metrics)
                  .filter(([, value]) => typeof value === 'number')
                  .slice(0, 8)
                  .map(([key, value]) => (
                    <MetricCard
                      key={key}
                      label={humanize(key)}
                      value={formatMetric(key, value)}
                      hint={latest?.name}
                    />
                  ))
              : null}
          </div>

          <div className="mt-4 grid gap-4 xl:grid-cols-2">
            <Card>
              <CardHeader
                title="Final metric comparison"
                description="Core classification metrics from the latest completed run."
              />
              <CardBody>
                <MetricBarChart metrics={latestResult?.final_metrics ?? null} />
              </CardBody>
            </Card>
            <Card>
              <CardHeader
                title="Accuracy by round"
                description={
                  rounds.length > 0
                    ? `${rounds.length} recorded round${rounds.length === 1 ? '' : 's'}.`
                    : 'No per-round metric records.'
                }
              />
              <CardBody>
                {rounds.length > 0 ? (
                  <RoundLineChart rounds={rounds} metric={roundMetric} />
                ) : (
                  <p className="py-10 text-center text-sm text-muted">
                    This result contains final metrics only.
                  </p>
                )}
              </CardBody>
            </Card>
          </div>

          <Card className="mt-4">
            <CardHeader
              title="Completed experiment records"
              description="Only succeeded experiments with a final_metrics object are listed as evaluated."
            />
            <DataTable
              columns={columns}
              rows={completed}
              rowKey={(row) => row.id}
              caption="Completed experiment metrics"
            />
          </Card>
        </>
      )}
    </div>
  )
}
