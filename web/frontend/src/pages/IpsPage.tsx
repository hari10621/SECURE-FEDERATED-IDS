import { ShieldAlert, ShieldOff } from 'lucide-react'
import { Alert } from '../components/ui/Alert'
import { Button } from '../components/ui/Button'
import { Card, CardBody, CardHeader } from '../components/ui/Card'
import { PageHeader } from '../components/ui/PageHeader'
import { UnavailableState } from '../components/ui/States'

export function IpsPage() {
  return (
    <div>
      <PageHeader
        eyebrow="Security"
        title="IPS & Prevention"
        description="Prevention is not implemented. The console does not expose blocking or quarantine controls without a controller, a lab, and an explicit safety case."
      />

      <UnavailableState
        title="No intrusion-prevention capability"
        reason="There is no SDN controller integration, no network lab, and no verified detection model admitted for action. Any blocking control would be unsafe and misleading."
        items={[
          'No controller connection or flow-rule writer.',
          'No verified model-to-action policy.',
          'No lab scope, rollback procedure, or safety review.',
          'No audit trail for enforcement decisions.',
        ]}
        className="mb-4"
      />

      <div className="grid gap-4 xl:grid-cols-2">
        <Card>
          <CardHeader title="Prevention controls" />
          <CardBody className="space-y-4">
            <p className="text-sm leading-6 text-muted">
              The following control is intentionally disabled. It has no backend implementation and
              must not be presented as operational.
            </p>
            <Button
              variant="danger"
              disabledReason="IPS enforcement requires a controller adapter, a lab network, a verified model policy, rollback, and audit logging."
              icon={<ShieldOff className="size-4" aria-hidden="true" />}
            >
              Enable prevention
            </Button>
            <Alert tone="warning" title="No blocking claim">
              A dashboard button is not an IPS. No packets are dropped, no hosts are quarantined,
              and no flow rules are installed by this build.
            </Alert>
          </CardBody>
        </Card>

        <Card>
          <CardHeader title="Prerequisites before any action" />
          <CardBody className="space-y-3 text-sm leading-6 text-muted">
            <div className="flex items-start gap-3">
              <ShieldAlert className="mt-0.5 size-4 shrink-0 text-amber-300" aria-hidden="true" />
              <div>
                <p className="font-medium text-ink">Lab and controller</p>
                <p className="mt-0.5">
                  A reversible lab topology, a read-only controller path, and an approved policy for
                  when a rule may be written.
                </p>
              </div>
            </div>
            <div className="flex items-start gap-3">
              <ShieldAlert className="mt-0.5 size-4 shrink-0 text-amber-300" aria-hidden="true" />
              <div>
                <p className="font-medium text-ink">Detection evidence</p>
                <p className="mt-0.5">
                  A verified model, calibrated thresholds, false-positive review, and a human
                  override path.
                </p>
              </div>
            </div>
            <div className="flex items-start gap-3">
              <ShieldAlert className="mt-0.5 size-4 shrink-0 text-amber-300" aria-hidden="true" />
              <div>
                <p className="font-medium text-ink">Auditability</p>
                <p className="mt-0.5">
                  An immutable record of every enforcement decision and its rollback.
                </p>
              </div>
            </div>
          </CardBody>
        </Card>
      </div>
    </div>
  )
}
