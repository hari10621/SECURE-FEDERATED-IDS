import { Activity, RefreshCw, ScanSearch } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { Alert } from '../components/ui/Alert'
import { Button } from '../components/ui/Button'
import { Card, CardBody, CardHeader } from '../components/ui/Card'
import { Field, TextArea } from '../components/ui/Field'
import { MetricCard } from '../components/ui/MetricCard'
import { PageHeader } from '../components/ui/PageHeader'
import { ErrorState, LoadingState, UnavailableState } from '../components/ui/States'
import { StatusBadge } from '../components/ui/StatusBadge'
import { useApi } from '../hooks/useApi'
import { api } from '../lib/api'
import { describeError } from '../lib/format'

export function IntrusionPage() {
  const status = useApi(() => api.predictionStatus(), [])
  const [raw, setRaw] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const available = status.data?.available ?? false

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    setError(null)
    setNotice(null)
    const features = raw
      .split(/[\s,;]+/)
      .filter(Boolean)
      .map(Number)
    if (features.length === 0 || features.some((value) => !Number.isFinite(value))) {
      setError('Enter numeric feature values separated by commas or whitespace.')
      return
    }
    setBusy(true)
    try {
      await api.predict(features)
      setNotice(
        `Request completed with ${features.length} features. The backend returned no prediction payload.`,
      )
    } catch (cause) {
      setError(describeError(cause))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div>
      <PageHeader
        eyebrow="Security"
        title="Intrusion Detection"
        description="Inference is fail-closed until a verified model and a matching preprocessing manifest are admitted. No predictions are generated in the browser."
        actions={
          <Button
            variant="secondary"
            size="sm"
            onClick={status.reload}
            icon={<RefreshCw className="size-3.5" aria-hidden="true" />}
          >
            Refresh
          </Button>
        }
      />

      {status.loading && !status.data ? (
        <LoadingState label="Checking model status…" />
      ) : status.error ? (
        <ErrorState message={status.error} onRetry={status.reload} />
      ) : (
        <>
          <div className="grid gap-3 sm:grid-cols-3">
            <MetricCard
              label="Inference"
              value={status.data?.available ? 'Available' : 'Unavailable'}
              hint="Reported by /api/v1/predictions/status."
              icon={<Activity className="size-4" />}
              tone={status.data?.available ? 'success' : 'warning'}
            />
            <MetricCard
              label="Model"
              value={status.data?.model ?? 'None admitted'}
              hint="A verified model artifact is required."
              icon={<ScanSearch className="size-4" />}
              tone="warning"
            />
            <MetricCard
              label="Preprocessing"
              value={status.data?.preprocessing ?? 'Unverified'}
              hint="The scaler and feature order must match the model manifest."
              icon={<ScanSearch className="size-4" />}
              tone="warning"
            />
          </div>

          {!status.data?.available ? (
            <UnavailableState
              title="Prediction endpoint is closed"
              reason={status.data?.reason ?? 'No verified prediction backend is available.'}
              items={[
                'No admitted model artifact and matching preprocessing manifest.',
                'No parity check against the research GRU.',
                'The browser must not approximate a prediction from uploaded data.',
              ]}
              className="mt-4"
            />
          ) : null}

          <Card className="mt-4">
            <CardHeader
              title="Single-sample inference"
              description="Paste numeric features exactly as the model expects. The backend validates the request before any inference."
              actions={
                <StatusBadge
                  tone={available ? 'success' : 'warning'}
                  label={available ? 'Open' : 'Closed'}
                />
              }
            />
            <CardBody>
              <form className="space-y-4" onSubmit={handleSubmit}>
                <Field
                  label="Feature values"
                  htmlFor="prediction-features"
                  hint="Comma- or whitespace-separated numbers. The research schema expects 48 features."
                >
                  <TextArea
                    id="prediction-features"
                    value={raw}
                    onChange={(event) => setRaw(event.target.value)}
                    placeholder="0.12, 0.03, 1.0, …"
                    disabled={!available}
                    spellCheck={false}
                  />
                </Field>
                {error ? <Alert tone="danger" title="Prediction request failed">{error}</Alert> : null}
                {notice ? <Alert tone="success">{notice}</Alert> : null}
                <Button
                  type="submit"
                  loading={busy}
                  disabled={!available}
                  disabledReason={
                    available
                      ? undefined
                      : status.data?.reason ??
                        'A verified model and matching preprocessing manifest are required.'
                  }
                  icon={<Activity className="size-4" aria-hidden="true" />}
                >
                  Request prediction
                </Button>
              </form>
            </CardBody>
          </Card>

          <Alert tone="warning" className="mt-4" title="No inference claim">
            An empty or unavailable result is intentional. Showing a synthetic class label would
            misrepresent the system's verified capability.
          </Alert>
        </>
      )}
    </div>
  )
}
