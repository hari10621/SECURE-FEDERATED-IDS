import {
  ArrowRight,
  Cpu,
  Database,
  Lock,
  Network,
  RefreshCw,
  Server,
  Users,
} from 'lucide-react'
import { Link } from 'react-router-dom'
import { Alert } from '../components/ui/Alert'
import { Button, buttonStyles } from '../components/ui/Button'
import { Card, CardBody, CardHeader } from '../components/ui/Card'
import { DataTable, type Column } from '../components/ui/DataTable'
import { EmptyState, ErrorState, InlineLoading, LoadingState } from '../components/ui/States'
import { MetricCard } from '../components/ui/MetricCard'
import { PageHeader } from '../components/ui/PageHeader'
import { StatusBadge } from '../components/ui/StatusBadge'
import { useApi } from '../hooks/useApi'
import { api, apiRequest } from '../lib/api'
import { formatDate, formatNumber } from '../lib/format'
import type { ExperimentResponse } from '../lib/types'

export function OverviewPage() {
  const health = useApi(() => api.health(), [])
  const version = useApi(() => api.version(), [])
  const encryption = useApi(() => api.encryptionStatus(), [])
  const sdn = useApi(() => api.sdnStatus(), [])
  const native = useApi(()=>apiRequest<{network:null|{state:string}}>('/api/v1/native-network'),[])
  const predictions = useApi(() => api.predictionStatus(), [])
  const datasets = useApi(() => api.listDatasets({ limit: 1 }), [])
  const experiments = useApi(() => api.listExperiments({ limit: 5 }), [])
  const jobs = useApi(() => api.listJobs({ limit: 1 }), [])
  const clients = useApi(() => api.listClients({ limit: 200 }))

  if (health.loading && !health.data) {
    return <LoadingState label="Connecting to the local backend…" />
  }

  if (health.error) {
    return (
      <div>
        <PageHeader
          title="Overview"
        />
        <ErrorState
          message={health.error}
          onRetry={health.reload}
          hint="Start the backend with uvicorn from web/backend, then confirm the API base URL under Settings."
        />
      </div>
    )
  }

  const recent = experiments.data?.items ?? []
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
        <Link
          to={`/training?experiment=${encodeURIComponent(row.id)}`}
          className={buttonStyles('ghost', 'sm')}
        >
          Open
          <ArrowRight className="size-3.5" aria-hidden="true" />
        </Link>
      ),
    },
  ]

  return (
    <div>
      <PageHeader
        title="Overview"
        actions={
          <Button
            variant="secondary"
            size="sm"
            onClick={() => {
              health.reload()
              datasets.reload()
              experiments.reload()
              jobs.reload()
              encryption.reload()
              sdn.reload()
              native.reload()
              predictions.reload()
              clients.reload()
            }}
            icon={<RefreshCw className="size-3.5" aria-hidden="true" />}
          >
            Refresh
          </Button>
        }
      />

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <MetricCard
          label="API status"
          value={health.data ? (health.data.status === 'ok' ? 'Healthy' : 'Degraded') : '—'}
          hint={version.data ? `${version.data.name} · API ${version.data.api_version}` : 'Version pending'}
          icon={<Server className="size-4" />}
          tone={health.data?.status === 'ok' ? 'success' : 'warning'}
        />
        <MetricCard label="Connected clients" value={clients.data ? clients.data.items.filter(c=>c.runtime_connected).length : '—'} hint={clients.error} icon={<Users className="size-4"/>}/>
        <MetricCard label="Datasets" value={datasets.data ? formatNumber(datasets.data.total) : '—'} hint={datasets.error} icon={<Database className="size-4"/>}/>
        <MetricCard label="Jobs" value={jobs.data ? formatNumber(jobs.data.total) : '—'} hint={jobs.error} icon={<Cpu className="size-4"/>}/>
      </div>
      <Card className="mt-4">
        <CardHeader title="Client connections to the central model" />
        <CardBody className="space-y-3">
          <p className="break-all text-sm text-ink"><Server className="mr-2 inline size-4 text-cyan-glow" />Central coordinator · {predictions.data?.version ?? predictions.error ?? predictions.data?.reason ?? 'Checking model…'}</p>
          {clients.error && <Alert tone="warning">{clients.error}</Alert>}
          {clients.data?.total === 0 && <Link to="/clients">Create a federated client</Link>}
          {clients.data?.items.map(client => <div key={client.id} className="grid gap-1 border-l-2 border-line pl-3 text-sm sm:grid-cols-3">
            <span className="text-ink">{client.name}</span>
            <span>{client.runtime_connected ? `Connected · PID ${client.worker_pid}` : 'Disconnected'}</span>
            <span className="text-muted">{!predictions.data?.available || predictions.error ? 'Participation unknown' : predictions.data.participants?.includes(client.id) ? 'Contributed' : 'No update for this version'}</span>
          </div>)}
        </CardBody>
      </Card>


      <div className="mt-6 grid gap-4 xl:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
        <Card>
          <CardHeader
            title="Recent experiments"
            actions={
              <Link to="/history" className={buttonStyles('ghost', 'sm')}>
                History
                <ArrowRight className="size-3.5" aria-hidden="true" />
              </Link>
            }
          />
          {experiments.loading && !experiments.data ? (
            <LoadingState label="Loading experiments…" />
          ) : experiments.error ? (
            <CardBody>
              <ErrorState message={experiments.error} onRetry={experiments.reload} />
            </CardBody>
          ) : recent.length === 0 ? (
            <EmptyState
              title="No experiments yet"
              description="Create an experiment after uploading and validating a research-compatible dataset."
              action={
                <Link to="/training" className={buttonStyles('primary', 'sm')}>
                  Open federated training
                </Link>
              }
            />
          ) : (
            <DataTable
              columns={columns}
              rows={recent}
              rowKey={(row) => row.id}
              caption="Recent experiments"
            />
          )}
        </Card>

        <div className="space-y-4">
          <Card>
            <CardHeader title="Capability status" />
            <CardBody className="space-y-4">
              <CapabilityRow
                icon={<Lock className="size-4" />}
                label="CKKS encryption"
                status={encryption}
                available={encryption.data?.available}
                reason={encryption.data?.reason}
              />
              <CapabilityRow
                icon={<Network className="size-4" />}
                label="Windows network simulator"
                status={native}
                available={Boolean(native.data)}
                reason={native.data?.network?.state ?? 'No virtual network created'}
              />
              <CapabilityRow
                icon={<Network className="size-4" />}
                label="Optional Mininet controller"
                status={sdn}
                available={sdn.data?.available}
                reason={sdn.data?.reason}
              />
              <CapabilityRow
                icon={<Cpu className="size-4" />}
                label="Model inference"
                status={predictions}
                available={predictions.data?.available}
                reason={predictions.data?.reason}
              />
            </CardBody>
          </Card>

          <Card>
            <CardHeader title="Local environment" />
            <CardBody className="space-y-2 text-xs">
              <div className="flex justify-between gap-3">
                <span className="text-muted">Backend version</span>
                <span className="font-mono text-ink">{version.data?.version ?? '—'}</span>
              </div>
              <div className="flex justify-between gap-3">
                <span className="text-muted">Environment</span>
                <span className="font-mono text-ink">{version.data?.environment ?? '—'}</span>
              </div>
              <div className="flex justify-between gap-3">
                <span className="text-muted">Python</span>
                <span className="font-mono text-ink">{version.data?.python_version ?? '—'}</span>
              </div>
              {version.error ? <p className="pt-1 text-red-300">{version.error}</p> : null}
            </CardBody>
          </Card>
        </div>
      </div>


    </div>
  )
}

function CapabilityRow({
  icon,
  label,
  status,
  available,
  reason,
}: {
  icon: React.ReactNode
  label: string
  status: { loading: boolean; error: string | null }
  available?: boolean
  reason?: string
}) {
  return (
    <div>
      <div className="flex items-center justify-between gap-3">
        <span className="flex items-center gap-2 text-sm text-ink">
          <span className="text-faint" aria-hidden="true">
            {icon}
          </span>
          {label}
        </span>
        {status.loading ? (
          <InlineLoading label="Checking" />
        ) : status.error ? (
          <StatusBadge tone="danger" label="Status unavailable" />
        ) : (
          <StatusBadge
            tone={available ? 'success' : 'warning'}
            label={available ? 'Available' : 'Unavailable'}
          />
        )}
      </div>
      <p className="mt-1 text-xs leading-5 text-muted">
        {status.error ?? reason ?? 'No status reported.'}
      </p>
    </div>
  )
}
