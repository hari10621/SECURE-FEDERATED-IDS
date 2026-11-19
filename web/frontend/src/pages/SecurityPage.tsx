import { EyeOff, FileWarning, KeyRound, ShieldCheck } from 'lucide-react'
import { Alert } from '../components/ui/Alert'
import { Card, CardBody, CardHeader } from '../components/ui/Card'
import { PageHeader } from '../components/ui/PageHeader'
import { UnavailableState } from '../components/ui/States'

export function SecurityPage() {
  return (
    <div>
      <PageHeader
        eyebrow="Security"
        title="Security Monitoring"
        description="There is no security monitoring subsystem in this local build. This page describes the current posture and the missing capabilities instead of showing invented events."
      />

      <UnavailableState
        title="No monitoring data source"
        reason="The backend exposes health, dataset, experiment, client, and job records. It does not emit a security event stream, authentication audit log, or alert feed for this console."
        items={[
          'No per-client authenticated sessions or request signing.',
          'No audit event store or query API.',
          'No replay protection, rate-limit telemetry, or anomaly detector.',
          'No alerting or incident timeline.',
        ]}
        className="mb-4"
      />

      <div className="grid gap-4 xl:grid-cols-2">
        <Card>
          <CardHeader title="Current local posture" />
          <CardBody className="space-y-4 text-sm leading-6 text-muted">
            <div className="flex items-start gap-3">
              <KeyRound className="mt-0.5 size-4 shrink-0 text-cyan-glow" aria-hidden="true" />
              <div>
                <p className="font-medium text-ink">Optional shared bearer token</p>
                <p className="mt-0.5">
                  The backend supports a shared local token. It is not a per-client identity and
                  does not provide authorization scopes.
                </p>
              </div>
            </div>
            <div className="flex items-start gap-3">
              <ShieldCheck className="mt-0.5 size-4 shrink-0 text-cyan-glow" aria-hidden="true" />
              <div>
                <p className="font-medium text-ink">Loopback-first deployment</p>
                <p className="mt-0.5">
                  The default API base is 127.0.0.1. Exposing the backend on a network interface
                  requires a separate review.
                </p>
              </div>
            </div>
            <div className="flex items-start gap-3">
              <EyeOff className="mt-0.5 size-4 shrink-0 text-faint" aria-hidden="true" />
              <div>
                <p className="font-medium text-ink">No fabricated telemetry</p>
                <p className="mt-0.5">
                  This console does not display synthetic logins, threats, or traffic charts. The
                  empty state is the accurate state.
                </p>
              </div>
            </div>
          </CardBody>
        </Card>

        <Card>
          <CardHeader title="Required before security claims" />
          <CardBody className="space-y-3 text-sm leading-6 text-muted">
            <div className="flex items-start gap-3">
              <FileWarning className="mt-0.5 size-4 shrink-0 text-amber-300" aria-hidden="true" />
              <div>
                <p className="font-medium text-ink">Audit and identity</p>
                <p className="mt-0.5">
                  Authenticated client sessions, signed requests, immutable audit events, and a
                  retention policy.
                </p>
              </div>
            </div>
            <Alert tone="warning" title="No production security claim">
              A local loopback console with an optional shared token is not a production security
              architecture. Do not present it as one.
            </Alert>
          </CardBody>
        </Card>
      </div>
    </div>
  )
}
