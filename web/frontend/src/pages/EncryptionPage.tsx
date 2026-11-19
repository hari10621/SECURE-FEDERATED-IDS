import { KeyRound, Lock, RefreshCw, ShieldOff } from 'lucide-react'
import { Alert } from '../components/ui/Alert'
import { Button } from '../components/ui/Button'
import { Card, CardBody, CardHeader } from '../components/ui/Card'
import { PageHeader } from '../components/ui/PageHeader'
import { ErrorState, LoadingState, UnavailableState } from '../components/ui/States'
import { StatusBadge } from '../components/ui/StatusBadge'
import { MetricCard } from '../components/ui/MetricCard'
import { useApi } from '../hooks/useApi'
import { api } from '../lib/api'

export function EncryptionPage() {
  const encryption = useApi(() => api.encryptionStatus(), [])
  const available = encryption.data?.available ?? false

  return (
    <div>
      <PageHeader
        eyebrow="Security"
        title="Homomorphic Encryption"
        description="The encrypted research path is fail-closed. This page reports the actual backend status and does not generate keys or ciphertext."
        actions={
          <Button
            variant="secondary"
            size="sm"
            onClick={encryption.reload}
            icon={<RefreshCw className="size-3.5" aria-hidden="true" />}
          >
            Refresh
          </Button>
        }
      />

      {encryption.loading && !encryption.data ? (
        <LoadingState label="Checking encryption backend…" />
      ) : encryption.error ? (
        <ErrorState message={encryption.error} onRetry={encryption.reload} />
      ) : (
        <>
          <div className="grid gap-3 sm:grid-cols-3">
            <MetricCard
              label="CKKS backend"
              value={encryption.data?.backend ?? '—'}
              hint="Reported by /api/v1/encryption/status."
              icon={<Lock className="size-4" />}
              tone={available ? 'success' : 'warning'}
            />
            <MetricCard
              label="Availability"
              value={available ? 'Available' : 'Unavailable'}
              hint="Encrypted execution requires a verified backend before it can start."
              icon={<KeyRound className="size-4" />}
              tone={available ? 'success' : 'warning'}
            />
            <MetricCard
              label="Encrypted runs"
              value={available ? 'Requires review' : 'Blocked'}
              hint="The start endpoint remains unavailable until verification is complete."
              icon={<ShieldOff className="size-4" />}
              tone="warning"
            />
          </div>

          <div className="mt-4 grid gap-4 xl:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)]">
            <Card>
              <CardHeader
                title="Current backend reason"
                actions={
                  <StatusBadge tone={available ? 'success' : 'warning'} label={available ? 'Available' : 'Unavailable'} />
                }
              />
              <CardBody>
                <p className="rounded-lg border border-line bg-navy-950/60 px-4 py-3 text-sm leading-6 text-muted">
                  {encryption.data?.reason ?? 'No status reason was reported.'}
                </p>
                <div className="mt-4">
                  <UnavailableState
                    title="Encrypted execution is not admitted"
                    reason="The console will not enable key generation, encryption, or the research start endpoint until a verified native CKKS backend is present."
                    items={[
                      'Native CKKS library compatible with the backend ABI (the legacy artifact targets Linux CPython 3.8 / OpenFHE).',
                      'Distributed key generation and threshold decryption wired into the federated round harness.',
                      'Verified key lifecycle, context parameters, serialization, and failure handling.',
                      'A reproducible parity check against the approved reference behaviour.',
                    ]}
                  />
                </div>
              </CardBody>
            </Card>

            <Card>
              <CardHeader title="What this console will not do" />
              <CardBody className="space-y-4 text-sm leading-6 text-muted">
                <p>
                  There are no placeholder keys, no fabricated ciphertext, and no browser-side
                  cryptographic simulation. Every encrypted-run control is disabled and explains
                  why.
                </p>
                <Button
                  variant="secondary"
                  disabledReason="Key generation requires a verified CKKS backend and an approved key lifecycle."
                  icon={<KeyRound className="size-4" aria-hidden="true" />}
                >
                  Generate CKKS keys
                </Button>
                <Alert tone="warning" title="No encryption claim">
                  Results from the plaintext harness are never labelled encrypted. The backend
                  records <code className="rounded bg-navy-950 px-1 py-0.5 font-mono text-[11px]">encrypted: false</code>{' '}
                  for those runs.
                </Alert>
              </CardBody>
            </Card>
          </div>
        </>
      )}
    </div>
  )
}
