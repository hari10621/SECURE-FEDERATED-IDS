import { Network, RefreshCw, Router } from 'lucide-react'
import { Alert } from '../components/ui/Alert'
import { Button } from '../components/ui/Button'
import { Card, CardBody, CardHeader } from '../components/ui/Card'
import { MetricCard } from '../components/ui/MetricCard'
import { PageHeader } from '../components/ui/PageHeader'
import { ErrorState, LoadingState, UnavailableState } from '../components/ui/States'
import { useApi } from '../hooks/useApi'
import { api } from '../lib/api'

export function SdnPage() {
  const sdn = useApi(() => api.sdnStatus(), [])

  return (
    <div>
      <PageHeader
        eyebrow="Security"
        title="SDN Network"
        description="There is no SDN controller integration in this build. The console reports that fact and does not draw a synthetic topology."
        actions={
          <Button
            variant="secondary"
            size="sm"
            onClick={sdn.reload}
            icon={<RefreshCw className="size-3.5" aria-hidden="true" />}
          >
            Refresh
          </Button>
        }
      />

      {sdn.loading && !sdn.data ? (
        <LoadingState label="Checking SDN status…" />
      ) : sdn.error ? (
        <ErrorState message={sdn.error} onRetry={sdn.reload} />
      ) : (
        <>
          <div className="grid gap-3 sm:grid-cols-2">
            <MetricCard
              label="Controller"
              value={sdn.data?.available ? 'Connected' : 'Unavailable'}
              hint={sdn.data?.reason ?? 'No status reason reported.'}
              icon={<Network className="size-4" />}
              tone={sdn.data?.available ? 'success' : 'warning'}
            />
            <MetricCard
              label="Topology"
              value="Not loaded"
              hint="No controller adapter or switch inventory is configured."
              icon={<Router className="size-4" />}
              tone="warning"
            />
          </div>

          <UnavailableState
            title="No SDN control plane is available"
            reason={sdn.data?.reason ?? 'The backend has no SDN controller adapter.'}
            items={[
              'No controller endpoint, credentials, or TLS configuration.',
              'No switch, port, link, or flow-table inventory.',
              'No topology snapshot or live telemetry feed.',
              'No flow-rule or policy operations.',
            ]}
            className="mt-4"
          />

          <div className="mt-4 grid gap-4 xl:grid-cols-2">
            <Card>
              <CardHeader title="Integration contract required" />
              <CardBody className="space-y-3 text-sm leading-6 text-muted">
                <p>
                  A future SDN adapter must define how the controller is reached, how inventory is
                  discovered, how changes are authorized, and how failures are rolled back.
                </p>
                <ul className="space-y-1.5 text-xs leading-5">
                  <li>Explicit controller type, version, and API transport.</li>
                  <li>Read-only inventory before any write capability.</li>
                  <li>Dry-run and rollback for every proposed rule change.</li>
                  <li>A lab scope separate from any production network.</li>
                </ul>
              </CardBody>
            </Card>
            <Card>
              <CardHeader title="No network actions" />
              <CardBody>
                <Alert tone="warning" title="No topology or traffic claims">
                  This page does not estimate link utilization, switch health, or flow counts. Those
                  numbers would be fabricated without a controller connection.
                </Alert>
              </CardBody>
            </Card>
          </div>
        </>
      )}
    </div>
  )
}
