import { useEffect, useState } from 'react'
import { Bell } from 'lucide-react'
import { ApiError, api, apiRequest } from '../lib/api'
import { describeError } from '../lib/format'
import { useApi } from '../hooks/useApi'
import { Card, CardBody, CardHeader } from './ui/Card'
import { Button } from './ui/Button'
import { Select, TextInput } from './ui/Field'

const request = <T,>(path: string, body?: unknown) =>
  apiRequest<T>('/api/v1/automation/' + path, {
    method: body === undefined ? 'GET' : 'POST',
    body,
    timeoutMs: 90000,
  })
function usePoll<T>(loader: () => Promise<T>, key = '') {
  const state = useApi(loader, [key])
  useEffect(() => {
    const id = setInterval(state.reload, 5000)
    return () => clearInterval(id)
  }, [state.reload])
  return state
}
type Policy = {
  enabled: boolean
  minimum_new_samples: number
  minimum_clients: number
  minimum: number
  rounds: number
  epochs: number
  cooldown: number
  encrypted: boolean
  auto_deploy: boolean
  minimum_accuracy_gain: number
  minimum_f1: number
  maximum_fpr: number
  allowed_f1_drop: number
}
type Run = {
  id: string
  state: string
  detail: string
  events: string[]
  clients: string[]
  parent: string
  candidate: string
  experiment: string
  progress?: number
  message?: string
  validation: Record<string, unknown> | null
  acks: { client: string; pid: number; version: string }[]
}
type State = { policy: Policy; pending: number; runs: Run[] }
type Event = {
  id: string
  client: string
  organization: string
  host: string
  host_ip: string
  src: string
  dst: string
  ts: number
  origin: string
  version: string
  probability: number | null
  prediction: number | null
  severity: string
  label: number | null
  truth: number | null
  evidence: string
  status: string
  run: string
  row_index: number | null
}
function useAction(reload: () => void) {
  const [message, set] = useState('')
  const [busy, setBusy] = useState(false)
  async function act(fn: () => Promise<unknown>, success: string) {
    setBusy(true)
    set('')
    try {
      await fn()
      set(success)
      reload()
    } catch (e) {
      set(describeError(e))
    } finally {
      setBusy(false)
    }
  }
  return { message, busy, act }
}

export function NotificationBell() {
  const [before, setBefore] = useState(0)
  const feed = usePoll(
    () =>
      request<{
        unread: number
        items: { id: number; ts: number; message: string; seen: number }[]
      }>('notifications?before=' + before),
    String(before),
  )
  const [open, setOpen] = useState(false)
  const action = useAction(feed.reload)
  return (
    <div className="relative">
      <button
        aria-label="Notifications"
        aria-expanded={open}
        onClick={() => setOpen(!open)}
        className="flex items-center gap-1 p-2 text-ink"
      >
        <Bell size={18} />
        {feed.data?.unread ?? '—'}
      </button>
      {open && (
        <section className="absolute right-0 z-50 max-h-96 w-80 overflow-auto rounded border border-line bg-navy-950 p-3 text-sm shadow-xl">
          <strong>Notifications</strong>
          {before > 0 && <Button onClick={() => setBefore(0)}>Latest</Button>}
          {feed.data?.items.length === 50 && (
            <Button onClick={() => setBefore(feed.data!.items[49].id)}>
              Older
            </Button>
          )}
          <Button
            disabled={!feed.data?.unread || action.busy}
            onClick={() =>
              action.act(
                () => request('notifications/0/read', {}),
                'Marked all as read',
              )
            }
          >
            Mark all read
          </Button>
          <p role="status">{feed.error || action.message}</p>
          {feed.data?.items.length === 0 && <p>No notifications yet.</p>}
          {feed.data?.items.map((n) => (
            <div key={n.id} className="border-t border-line py-2">
              <small>{new Date(n.ts * 1000).toLocaleString()}</small>
              <p>{n.message}</p>
              {!n.seen && (
                <button
                  className="underline"
                  onClick={() =>
                    action.act(
                      () => request('notifications/' + n.id + '/read', {}),
                      'Marked as read',
                    )
                  }
                >
                  Mark read
                </button>
              )}
            </div>
          ))}
        </section>
      )}
    </div>
  )
}

export function RunDetails({ run }: { run: Run }) {
  return (
    <details className="break-all border-t border-line py-2">
      <summary>
        {run.state} · {run.id.slice(0, 10)} ·{' '}
        {Math.round(100 * (run.progress ?? 0))}%
      </summary>
      <p>{run.detail || run.message}</p>
      <p>Participants · {run.clients.join(', ')}</p>
      <p>
        Triggering events ·{' '}
        {run.events.map((id) => (
          <a key={id} href={'/security?event=' + id} className="mr-2 underline">
            {id}
          </a>
        ))}
      </p>
      <p>
        Parent · {run.parent} · Candidate · {run.candidate ?? 'Pending'}
      </p>
      {run.validation && (
        <pre className="overflow-auto">
          {JSON.stringify(run.validation, null, 2)}
        </pre>
      )}
      <p>
        Worker acknowledgements · {run.acks.length}/{run.clients.length}
      </p>
      {run.acks.map((a) => (
        <p key={a.client}>
          {a.client} · PID {a.pid} · {a.version}
        </p>
      ))}
    </details>
  )
}
export function AutomaticHistory({ id }: { id: string }) {
  const data = usePoll(() => request<Run>('runs/' + id), id)
  return data.data ? <RunDetails run={data.data} /> : <p>{data.error}</p>
}
export function PolicyPanel() {
  const state = usePoll(() => request<State>('status'))
  const [draft, setDraft] = useState<Policy | null>(null)
  const [serverErrors, setServerErrors] = useState<Record<string, string>>({})
  const p = draft ?? state.data?.policy
  const action = useAction(state.reload)
  const numeric = {
    minimum: 'Verified attack threshold',
    minimum_new_samples: 'Minimum new eligible samples',
    minimum_clients: 'Minimum participating clients',
    rounds: 'Rounds',
    epochs: 'Local epochs',
    cooldown: 'Cooldown (seconds)',
    minimum_accuracy_gain: 'Minimum accuracy change',
    minimum_f1: 'Minimum candidate F1',
    maximum_fpr: 'Maximum false-positive rate',
    allowed_f1_drop: 'Allowed F1 decrease',
  }
  const limits = {
    minimum: [1, 1000],
    minimum_new_samples:[1,1000],
    minimum_clients:[2,12],
    rounds: [1, 100],
    epochs: [1, 50],
    cooldown: [0, 604800],
    minimum_accuracy_gain: [-1, 1],
    minimum_f1: [0, 1],
    maximum_fpr: [0, 1],
    allowed_f1_drop: [0, 1],
  }
  function fieldError(k: keyof typeof numeric, value: number) {
    const [lo, hi] = limits[k]
    return (
      serverErrors[k] ||
      (!Number.isFinite(value) ||
      value < lo ||
      value > hi ||
      (hi > 1 && !Number.isInteger(value))
        ? `Enter ${hi > 1 ? 'a whole number' : 'a fraction'} from ${lo} to ${hi}.`
        : '')
    )
  }
  const invalid =
    p &&
    (Object.keys(numeric) as (keyof typeof numeric)[]).some((k) =>
      fieldError(k, p[k]),
    )
  return (
    <Card className="mb-4">
      <CardHeader title="Automatic Retraining Policy" />
      <CardBody className="space-y-3 text-sm">
        {p && (
          <>
            <div className="flex flex-wrap gap-4">
              {(
                [
                  ['enabled', 'Enable automatic retraining'],
                  ['encrypted', 'Require CKKS'],
                  ['auto_deploy', 'Deploy after validation'],
                ] as const
              ).map(([key, title]) => (
                <label key={key}>
                  <input
                    type="checkbox"
                    checked={p[key]}
                    onChange={(e) =>
                      setDraft({ ...p, [key]: e.target.checked })
                    }
                  />{' '}
                  {title}
                </label>
              ))}
            </div>
            <div className="grid gap-3 sm:grid-cols-3">
              {(Object.keys(numeric) as (keyof typeof numeric)[]).map((k) => (
                <label key={k}>
                  {numeric[k]}
                  <TextInput
                    type="number"
                    step={
                      [
                        'minimum_accuracy_gain',
                        'minimum_f1',
                        'maximum_fpr',
                        'allowed_f1_drop',
                      ].includes(k)
                        ? 0.01
                        : 1
                    }
                    min={limits[k][0]}
                    max={limits[k][1]}
                    aria-invalid={Boolean(fieldError(k, p[k]))}
                    value={Number.isFinite(p[k]) ? p[k] : ''}
                    onChange={(e) => {
                      setServerErrors((prev) => ({ ...prev, [k]: '' }))
                      setDraft({ ...p, [k]: e.target.valueAsNumber })
                    }}
                  />
                  {fieldError(k, p[k]) && (
                    <small className="block text-red-300">
                      {fieldError(k, p[k])}
                    </small>
                  )}
                </label>
              ))}
            </div>
            <Button
              disabled={action.busy || !draft || Boolean(invalid)}
              onClick={() =>
                action.act(async () => {
                  try {
                    await request('policy', p)
                  } catch (e) {
                    if (
                      e instanceof ApiError &&
                      e.status === 422 &&
                      Array.isArray(e.details)
                    ) {
                      setServerErrors(
                        Object.fromEntries(
                          e.details
                            .filter(
                              (i) =>
                                Array.isArray(i.loc) &&
                                typeof i.msg === 'string',
                            )
                            .map((i) => [i.loc.at(-1), i.msg]),
                        ),
                      )
                    }
                    throw e
                  }
                  const saved = (await request<State>('status')).policy
                  if (
                    (Object.keys(p) as (keyof Policy)[]).some(
                      (k) => p[k] !== saved[k],
                    )
                  )
                    throw Error('Saved values changed. Refresh the policy.')
                  setDraft(null)
                }, 'Policy saved')
              }
            >
              Save policy
            </Button>
          </>
        )}
        <p role="status">{state.error || action.message}</p>
        <p>
          Verified attacks awaiting assignment · {state.data?.pending ?? '—'}
        </p>
        {state.data?.runs.map((r) => (
          <div key={r.id}>
            <RunDetails run={r} />
            {r.state === 'failed' && (
              <Button
                disabled={action.busy}
                onClick={() =>
                  action.act(
                    () => request('runs/' + r.id + '/retry', {}),
                    'Released samples for retry',
                  )
                }
              >
                Retry failed run
              </Button>
            )}
            {r.state === 'deployed' && r.acks.length < r.clients.length && (
              <Button
                disabled={action.busy}
                onClick={() =>
                  action.act(
                    () => request('runs/' + r.id + '/sync', {}),
                    'Checked connected workers',
                  )
                }
              >
                Synchronize deployed version
              </Button>
            )}
          </div>
        ))}
      </CardBody>
    </Card>
  )
}

export function OrganizationForm() {
  const clients = useApi(() => api.listClients({ limit: 200 }))
  const [id, setId] = useState(''),
    [name, setName] = useState('')
  const action = useAction(clients.reload)
  return (
    <Card className="mb-4">
      <CardHeader title="Client organization" />
      <CardBody className="space-y-2">
        <label>
          Registered worker
          <Select
            value={id}
            onChange={(e) => {
              setId(e.target.value)
              setName(
                String(
                  clients.data?.items.find((c) => c.id === e.target.value)
                    ?.config.organization ?? '',
                ),
              )
            }}
          >
            <option value="">Select a worker</option>
            {clients.data?.items.map((c) => (
              <option value={c.id} key={c.id}>
                {c.name} · {c.id} ·{' '}
                {String(c.config.organization ?? 'Unassigned')}
              </option>
            ))}
          </Select>
        </label>
        <label>
          Organization name
          <TextInput
            maxLength={120}
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        </label>
        <Button
          disabled={!id || action.busy}
          onClick={() =>
            action.act(
              () => request('clients/' + id + '/organization', { name }),
              'Organization saved',
            )
          }
        >
          Save organization
        </Button>
        <p>{clients.error || action.message}</p>
      </CardBody>
    </Card>
  )
}

export function EventHistory({ clientId }: { clientId: string }) {
  const [origin, setOrigin] = useState(''),
    [organization, setOrg] = useState(''),
    [status, setStatus] = useState(''),
    [only, setOnly] = useState(false),
    [offset, setOffset] = useState(0)
  const [selected, select] = useState(
      new URLSearchParams(location.search).get('event') ?? '',
    ),
    [label, setLabel] = useState(''),
    [evidence, setEvidence] = useState('')
  const [sampleOffset, setSampleOffset] = useState(0)
  const qs = new URLSearchParams({
    origin,
    organization,
    status,
    offset: String(offset),
    client: only ? clientId : '',
  }).toString()
  const history = usePoll(() => request<Event[]>('events?' + qs), qs)
  const detail = useApi(
    async () => (selected ? request<Event>('events/' + selected) : null),
    [selected],
  )
  const action = useAction(() => {
    history.reload()
    detail.reload()
  })
  function replay() {
    action.act(async () => {
      const r = await request<{ event_id: string }>(
        'clients/' + clientId + '/training-sample?offset=' + sampleOffset,
        {},
      )
      setSampleOffset(sampleOffset + 1)
      select(r.event_id)
      setEvidence('')
      setLabel('')
    }, 'Training-partition sample scored. Review its stored CSV label.')
  }
  const e = detail.data
  return (
    <Card>
      <CardHeader title="Security event history" />
      <CardBody className="space-y-3 text-sm">
        <Button disabled={!clientId || action.busy} onClick={replay}>
          Score training-partition attack sample
        </Button>
        <div className="grid gap-2 sm:grid-cols-4">
          <label>
            Origin
            <Select
              value={origin}
              onChange={(v) => {
                setOrigin(v.target.value)
                setOffset(0)
              }}
            >
              <option value="">All origins</option>
              {[
                'dataset evaluation',
                'dataset replay',
                'dataset training',
                'live traffic',
                'manual input',
              ].map((v) => (
                <option key={v}>{v}</option>
              ))}
            </Select>
          </label>
          <label>
            Organization filter
            <TextInput
              value={organization}
              onChange={(v) => {
                setOrg(v.target.value)
                setOffset(0)
              }}
            />
          </label>
          <label>
            Retraining status
            <Select
              value={status}
              onChange={(v) => {
                setStatus(v.target.value)
                setOffset(0)
              }}
            >
              <option value="">All statuses</option>
              {[
                'unreviewed',
                'held-out',
                'verified',
                'queued',
                'training',
                'ineligible',
                'deployed',
                'validated',
                'rejected',
                'failed',
                'historical',
              ].map((v) => (
                <option key={v}>{v}</option>
              ))}
            </Select>
          </label>
          <label>
            <input
              type="checkbox"
              checked={only}
              onChange={(v) => {
                setOnly(v.target.checked)
                setOffset(0)
              }}
            />{' '}
            Selected client only
          </label>
        </div>
        {history.data?.map((row) => (
          <button
            key={row.id}
            className="block w-full border-t border-line py-2 text-left"
            onClick={() => {
              select(row.id)
              setEvidence('')
              setLabel('')
            }}
          >
            {new Date(row.ts * 1000).toLocaleString()} ·{' '}
            {row.organization || 'Unassigned'} · {row.origin} · {row.severity} ·{' '}
            {row.status}
          </button>
        ))}
        {!history.data?.length && <p>No matching events.</p>}
        <Button disabled={!offset} onClick={() => setOffset(offset - 100)}>
          Previous
        </Button>
        <Button
          disabled={history.data?.length !== 100}
          onClick={() => setOffset(offset + 100)}
        >
          Next
        </Button>
        {e && (
          <section className="space-y-2 break-all rounded border border-line p-3">
            <p>
              Event {e.id} · {e.organization || 'Unassigned'} · client{' '}
              {e.client ?? 'Unknown'} · {e.host ?? 'No mapped host'} {e.host_ip}
            </p>
            <p>
              {e.origin} · source {e.src ?? 'Unknown'} · destination{' '}
              {e.dst ?? 'Unknown'} · model {e.version || 'Unscored'}
            </p>
            <p>
              Prediction ·{' '}
              {e.prediction === null
                ? 'Unscored'
                : e.prediction
                  ? 'Attack'
                  : 'Benign'}{' '}
              · attack probability{' '}
              {e.probability === null
                ? '—'
                : (e.probability * 100).toFixed(2) + '%'}{' '}
              · verified label{' '}
              {e.label === null ? 'Pending' : e.label ? 'Attack' : 'Benign'}
            </p>
            <p>
              Retraining · {e.status} · {e.run ?? 'No run'} · {e.evidence}
            </p>
            {e.truth !== null && (
              <p>
                Source CSV row {(e.row_index ?? 0) + 2} · recorded label{' '}
                {e.truth ? 'Attack' : 'Benign'}
              </p>
            )}
            {['unreviewed', 'verified', 'held-out'].includes(e.status) && (
              <>
                <label>
                  Reviewed label
                  <Select
                    value={label}
                    onChange={(v) => setLabel(v.target.value)}
                  >
                    <option value="">Select verified label</option>
                    <option value="0">Benign</option>
                    <option value="1">Attack</option>
                  </Select>
                </label>
                <label>
                  Independent label evidence
                  <TextInput
                    value={evidence}
                    onChange={(v) => setEvidence(v.target.value)}
                    placeholder="CSV annotation or independently confirmed lab observation"
                  />
                </label>
                <Button
                  disabled={label === '' || !evidence.trim() || action.busy}
                  onClick={() =>
                    action.act(
                      () =>
                        request('events/' + e.id + '/review', {
                          label: Number(label),
                          evidence,
                        }),
                      'Review saved',
                    )
                  }
                >
                  Verify sample
                </Button>
                {e.status!=='held-out' && <Button disabled={!evidence.trim()||action.busy} onClick={()=>action.act(()=>request('events/'+e.id+'/reject',{evidence}),'Sample excluded from training')}>Reject sample</Button>}
              </>
            )}
          </section>
        )}
        <p role="status">{history.error || detail.error || action.message}</p>
      </CardBody>
    </Card>
  )
}
