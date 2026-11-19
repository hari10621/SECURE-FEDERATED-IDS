import { KeyRound, RotateCcw, Save, Wifi } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { Alert } from '../components/ui/Alert'
import { Button } from '../components/ui/Button'
import { Card, CardBody, CardHeader } from '../components/ui/Card'
import { Field, TextInput } from '../components/ui/Field'
import { PageHeader } from '../components/ui/PageHeader'
import { api } from '../lib/api'
import {
  DEFAULT_BASE_URL,
  loadApiConfig,
  resetApiConfig,
  saveApiConfig,
} from '../lib/config'
import { describeError } from '../lib/format'

export function SettingsPage() {
  const initial = loadApiConfig()
  const [baseUrl, setBaseUrl] = useState(initial.baseUrl)
  const [token, setToken] = useState(initial.token)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [testing, setTesting] = useState(false)
  const [testResult, setTestResult] = useState<{ ok: boolean; message: string } | null>(null)

  function persist(): boolean {
    setError(null)
    setNotice(null)
    try {
      const saved = saveApiConfig({ baseUrl, token })
      setBaseUrl(saved.baseUrl)
      setToken(saved.token)
      setNotice('API settings saved in this browser. The client reads them before each request.')
      return true
    } catch (cause) {
      setError(describeError(cause))
      return false
    }
  }

  function handleSave(event: FormEvent) {
    event.preventDefault()
    persist()
  }

  async function handleTest() {
    setTestResult(null)
    if (!persist()) return
    setTesting(true)
    const started = performance.now()
    try {
      const health = await api.health()
      const elapsed = Math.round(performance.now() - started)
      setTestResult({
        ok: true,
        message: `Connected in ${elapsed} ms. Status: ${health.status}; database: ${health.database}; encryption: ${health.encryption}.`,
      })
    } catch (cause) {
      setTestResult({ ok: false, message: describeError(cause) })
    } finally {
      setTesting(false)
    }
  }

  function handleReset() {
    const defaults = resetApiConfig()
    setBaseUrl(defaults.baseUrl)
    setToken(defaults.token)
    setTestResult(null)
    setError(null)
    setNotice('API settings reset to defaults. The shared token was removed from this browser.')
  }

  return (
    <div>
      <PageHeader
        eyebrow="System"
        title="Settings"
        description="Configure the local API connection. These values live in browser storage only and are never embedded in the build."
      />

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)]">
        <Card>
          <CardHeader
            title="API connection"
            description="Use the backend origin without an /api/v1 suffix. The console appends API paths itself."
          />
          <CardBody>
            <form className="space-y-4" onSubmit={handleSave}>
              <Field
                label="API base URL"
                htmlFor="api-base-url"
                required
                hint={`Default: ${DEFAULT_BASE_URL}. Loopback is expected for local use.`}
              >
                <TextInput
                  id="api-base-url"
                  value={baseUrl}
                  onChange={(event) => setBaseUrl(event.target.value)}
                  placeholder={DEFAULT_BASE_URL}
                  autoComplete="off"
                  spellCheck={false}
                />
              </Field>
              <Field
                label="Shared bearer token"
                htmlFor="api-token"
                hint="Optional. Stored in localStorage and sent only as the Authorization header. Leave blank when the backend has no token configured."
              >
                <TextInput
                  id="api-token"
                  type="password"
                  value={token}
                  onChange={(event) => setToken(event.target.value)}
                  placeholder="Optional local token"
                  autoComplete="off"
                  spellCheck={false}
                />
              </Field>

              {error ? <Alert tone="danger" title="Could not save settings">{error}</Alert> : null}
              {notice ? <Alert tone="success">{notice}</Alert> : null}
              {testResult ? (
                <Alert tone={testResult.ok ? 'success' : 'danger'} title={testResult.ok ? 'Connection succeeded' : 'Connection failed'}>
                  {testResult.message}
                </Alert>
              ) : null}

              <div className="flex flex-wrap gap-2">
                <Button type="submit" icon={<Save className="size-4" aria-hidden="true" />}>
                  Save
                </Button>
                <Button
                  variant="secondary"
                  loading={testing}
                  onClick={handleTest}
                  icon={<Wifi className="size-4" aria-hidden="true" />}
                >
                  Save and test
                </Button>
                <Button
                  variant="ghost"
                  onClick={handleReset}
                  icon={<RotateCcw className="size-4" aria-hidden="true" />}
                >
                  Reset
                </Button>
              </div>
            </form>
          </CardBody>
        </Card>

        <div className="space-y-4">
          <Card>
            <CardHeader title="Browser storage" />
            <CardBody className="space-y-3 text-sm leading-6 text-muted">
              <div className="flex items-start gap-3">
                <KeyRound className="mt-0.5 size-4 shrink-0 text-cyan-glow" aria-hidden="true" />
                <div>
                  <p className="font-medium text-ink">Local only</p>
                  <p className="mt-0.5">
                    The base URL and optional token are stored under a single namespaced
                    localStorage key. They are not included in source control or the build output.
                  </p>
                </div>
              </div>
              <p className="rounded-lg border border-line bg-navy-950/60 px-3 py-3 font-mono text-[11px] text-muted">
                key: securefed.console.api.v1
              </p>
              <Alert tone="warning" title="Shared token scope">
                A bearer token authenticates requests to this local backend. It is not a per-user
                identity, and the console does not log it.
              </Alert>
            </CardBody>
          </Card>

          <Card>
            <CardHeader title="Runtime expectations" />
            <CardBody className="space-y-2 text-xs leading-5 text-muted">
              <p>
                The browser never loads TensorFlow, NumPy, Pandas, or CKKS libraries. Training and
                simulation jobs run in the Python backend.
              </p>
              <p>
                If the API is offline, start uvicorn in web/backend and verify the health endpoint
                before saving a new URL.
              </p>
              <p>
                The console does not enable demo or sample data by default. Every metric, status,
                and record shown comes from the backend.
              </p>
            </CardBody>
          </Card>
        </div>
      </div>
    </div>
  )
}
