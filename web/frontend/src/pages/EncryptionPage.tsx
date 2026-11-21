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
        description="Reports the real CKKS backend. When TenSEAL is enabled, each encrypted run performs a per-run Trusted Authority ceremony and keeps the secret context in the client keyring only."
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
              hint="TenSEAL is detected by the backend and can run a per-run TA ceremony."
              icon={<KeyRound className="size-4" />}
              tone={available ? 'success' : 'warning'}
            />
            <MetricCard
              label="Encrypted runs"
              value={available ? 'Enabled' : 'Blocked'}
              hint="Encrypted training is admitted only when the backend reports available."
              icon={<ShieldOff className="size-4" />}
              tone={available ? 'success' : 'warning'}
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
                    title={available ? 'Encrypted execution is admitted' : 'Encrypted execution is not admitted'}
                    reason={
                      available
                        ? 'TenSEAL CKKS is installed. The backend generates a fresh shared keypair for each encrypted run; the aggregation server receives only the public context.'
                        : 'Enable the backend with SECUREFED_ENABLE_CKKS=1 after installing requirements-crypto.txt. Until then every cryptographic operation fails closed.'
                    }
                    items={
                      available
                        ? [
                            'Offline Trusted Authority issues one shared CKKS keypair per run.',
                            'Clients encrypt ΔW with the public context and hash the ciphertext.',
                            'The server homomorphically aggregates ciphertext only; it never receives plaintext weights.',
                            'Clients decrypt the aggregate with the secret context held by the client keyring.',
                          ]
                        : [
                            'Install the optional TenSEAL runtime: requirements-crypto.txt.',
                            'Set SECUREFED_ENABLE_CKKS=1 in the backend environment.',
                            'No placeholder keys or fabricated ciphertext are ever produced.',
                          ]
                    }
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
                  disabledReason="Keys are generated per encrypted training run; the console never receives secret material."
                  icon={<KeyRound className="size-4" aria-hidden="true" />}
                >
                  Generate CKKS keys
                </Button>
                <Alert tone={available ? 'info' : 'warning'} title={available ? 'Real CKKS path' : 'No encryption claim'}>
                  {available
                    ? 'Encrypted runs record encrypted: true only after TenSEAL encryption, homomorphic aggregation, and client-side decryption actually execute.'
                    : 'Results from the plaintext harness are never labelled encrypted. The backend records encrypted: false for those runs.'}
                </Alert>
              </CardBody>
            </Card>
          </div>
        </>
      )}
    </div>
  )
}
