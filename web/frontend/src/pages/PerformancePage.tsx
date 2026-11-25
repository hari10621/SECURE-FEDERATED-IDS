import { TrainingEvidence } from '../components/TrainingEvidence'
import { useState } from 'react'
import { Field, Select } from '../components/ui/Field'
import { BarChart3, RefreshCw } from 'lucide-react'
import { Link } from 'react-router-dom'
import { Button, buttonStyles } from '../components/ui/Button'
import { Card, CardBody, CardHeader } from '../components/ui/Card'
import { DataTable, type Column } from '../components/ui/DataTable'
import {
  CommunicationOverheadChart,
  ComputationTimeChart,
  MetricBarChart,
  RoundComparisonChart,
  RoundLineChart,
} from '../components/ui/Charts'
import { MetricCard } from '../components/ui/MetricCard'
import { PageHeader } from '../components/ui/PageHeader'
import { EmptyState, ErrorState, LoadingState } from '../components/ui/States'
import { StatusBadge } from '../components/ui/StatusBadge'
import { useApi } from '../hooks/useApi'
import { api } from '../lib/api'
import { formatDate, formatMetric, humanize } from '../lib/format'
import type { ExperimentResponse, FederatedResult, RoundMetric } from '../lib/types'

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
  const [selectedId, setSelectedId] = useState('')
  const latest = completed.find(experiment => experiment.id === selectedId) ?? completed[0]
  const latestResult = latest ? completedResult(latest) : null
  const rounds = latestResult?.rounds ?? []
  const roundMetric = rounds.some((round) => typeof round.metrics?.accuracy === 'number')
    ? 'accuracy'
    : 'f1'

  const standardExperiment = completed.find((experiment) => !completedResult(experiment)?.encrypted)
  const heExperiment = completed.find((experiment) => Boolean(completedResult(experiment)?.encrypted))
  const standardId = standardExperiment?.id ?? null
  const heId = heExperiment?.id ?? null

  const metrics = useApi(async () => {
    const empty: RoundMetric[] = []
    const [standard, he] = await Promise.all([
      standardId ? api.experimentMetrics(standardId) : Promise.resolve({ round_metrics: empty }),
      heId ? api.experimentMetrics(heId) : Promise.resolve({ round_metrics: empty }),
    ])
    return { standard: standard.round_metrics, he: he.round_metrics }
  }, [standardId, heId])

  const standardRounds = metrics.data?.standard ?? []
  const heRounds = metrics.data?.he ?? []
  const timedRounds = heRounds.length > 0 ? heRounds : standardRounds

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
        title="Performance Evaluation"
        actions={
          <Button
            variant="secondary"
            size="sm"
            onClick={() => {
              experiments.reload()
              datasets.reload()
              metrics.reload()
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
            description="Select a completed training run to view metrics."
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
          <Field label="Completed experiment" htmlFor="evaluated-run">
            <Select id="evaluated-run" value={latest?.id ?? ''} onChange={event => setSelectedId(event.target.value)}>
              {completed.map(experiment => <option key={experiment.id} value={experiment.id}>{experiment.name}</option>)}
            </Select>
          </Field>
          {latest && <TrainingEvidence experiment={latest} />}

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

          <div className="mt-4 grid gap-4 xl:grid-cols-2">
            <Card>
              <CardHeader
                title="Accuracy: standard FL vs HE-FL"
                description={
                  metrics.loading
                    ? 'Loading per-round metrics…'
                    : metrics.error ??
                      'Per-round accuracy from the latest plaintext and encrypted experiments.'
                }
              />
              <CardBody>
                {standardRounds.length > 0 || heRounds.length > 0 ? (
                  <RoundComparisonChart
                    standard={standardRounds}
                    he={heRounds}
                    metric="accuracy"
                    label="Standard FL (plaintext) vs HE-FL (CKKS)"
                  />
                ) : (
                  <p className="py-10 text-center text-sm text-muted">
                    No per-round accuracy records were returned by the metrics endpoint.
                  </p>
                )}
              </CardBody>
            </Card>
            <Card>
              <CardHeader
                title="Loss convergence"
              />
              <CardBody>
                {standardRounds.length > 0 || heRounds.length > 0 ? (
                  <RoundComparisonChart
                    standard={standardRounds}
                    he={heRounds}
                    metric="loss"
                    label="Lower is better"
                  />
                ) : (
                  <p className="py-10 text-center text-sm text-muted">
                    No per-round loss records were returned by the metrics endpoint.
                  </p>
                )}
              </CardBody>
            </Card>
          </div>

          <div className="mt-4 grid gap-4 xl:grid-cols-2">
            <Card>
              <CardHeader
                title="Computation time breakdown"
              />
              <CardBody>
                {timedRounds.length > 0 ? (
                  <ComputationTimeChart rounds={timedRounds} />
                ) : (
                  <p className="py-10 text-center text-sm text-muted">
                    Timing fields are not present in this result. Enable timed training runs.
                  </p>
                )}
              </CardBody>
            </Card>
            <Card>
              <CardHeader
                title="Communication overhead"
              />
              <CardBody>
                {standardRounds.length > 0 || heRounds.length > 0 ? (
                  <CommunicationOverheadChart standard={standardRounds} he={heRounds} />
                ) : (
                  <p className="py-10 text-center text-sm text-muted">
                    No communication-size records were returned by the metrics endpoint.
                  </p>
                )}
              </CardBody>
            </Card>
          </div>

          <Card className="mt-4">
            <CardHeader
              title="Completed experiment records"
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
