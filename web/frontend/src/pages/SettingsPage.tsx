import { RotateCcw, Save, Wifi } from 'lucide-react'
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
      setNotice('API settings saved.')
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
        title="Settings"
      />

      <div className="max-w-2xl">
        <Card>
          <CardHeader
            title="API connection"
          />
          <CardBody>
            <form className="space-y-4" onSubmit={handleSave}>
              <Field
                label="API base URL"
                htmlFor="api-base-url"
                required
                hint={`Default: ${DEFAULT_BASE_URL}`}
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
                hint="Optional. Saved in this browser."
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


      </div>
    </div>
  )
}
