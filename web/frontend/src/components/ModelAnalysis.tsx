import { useState } from 'react'
import {
  BarChart,
  Bar,
  LineChart,
  Line,
  CartesianGrid,
  XAxis,
  YAxis,
  Tooltip,
  Legend,
  ResponsiveContainer,
  Cell,
  ReferenceLine,
  PieChart,
  Pie,
} from 'recharts'
import { apiRequest } from '../lib/api'
import { useApi } from '../hooks/useApi'
import type { Detail, Version } from '../pages/CentralModelPage'
import { Button } from './ui/Button'
import { Card, CardHeader, CardBody } from './ui/Card'
import type { ReactNode } from 'react'

const metrics = [
  ['accuracy', 'Accuracy'],
  ['precision', 'Precision'],
  ['recall', 'Recall'],
  ['f1', 'F1'],
  ['false_positive_rate', 'False-positive rate'],
] as const
const palette = [
  '#38bdf8',
  '#a78bfa',
  '#34d399',
  '#fbbf24',
  '#fb7185',
  '#60a5fa',
]
const tooltip = {
  backgroundColor: '#172333',
  border: '1px solid #475569',
  borderRadius: 8,
  color: '#fff',
}
const good = '#34d399',
  bad = '#fb7185',
  neutral = '#94a3b8'
type Measurement = {
  participants?: string[]
  classes?: Record<string, { benign: number; attack: number }>
  trigger?: string
  metrics: Record<string, number> | null
  protocol: string | null
  source?: string
  reason?: string
  matrix?: Record<string, number> | null
  test_rows: number
  threshold: number
}
const pct = (v: number) => v * 100
const show = (v: number) => pct(v).toFixed(2) + '%'
export const shortHash = (s: string) =>
  s.length > 24 ? s.slice(0, 12) + '…' + s.slice(-8) : s
export function Hash({ value }: { value: string | null }) {
  const [open, setOpen] = useState(false),
    [message, set] = useState('')
  if (!value) return <span>Unavailable</span>
  return (
    <span className="inline-flex flex-wrap items-center gap-2">
      <code className="break-all" title={value}>
        {open ? value : shortHash(value)}
      </code>
      <button
        type="button"
        className="text-cyan-glow underline"
        onClick={() => setOpen(!open)}
      >
        {open ? 'Hide' : 'View full hash'}
      </button>
      <button
        type="button"
        className="text-cyan-glow underline"
        onClick={async () => {
          try {
            await navigator.clipboard.writeText(value)
            set('Copied')
          } catch {
            set('Copy unavailable')
          }
        }}
      >
        Copy full hash
      </button>
      <small role="status">{message}</small>
    </span>
  )
}
function Panel({ title, children }: { title: string; children: ReactNode }) {
  return (
    <Card>
      <CardHeader title={title} />
      <CardBody className="min-w-0 space-y-3 text-sm">{children}</CardBody>
    </Card>
  )
}
function Plot({ children }: { children: React.ReactElement }) {
  return (
    <div className="min-w-0 h-72">
      <ResponsiveContainer width="100%" height="100%">
        {children}
      </ResponsiveContainer>
    </div>
  )
}
const date = (ts: number) => new Date(ts * 1000).toLocaleString()
export function ModelAnalysis({
  d,
  v,
  base,
  inspect,
  registered,
}: {
  registered?: number
  d: Detail
  v: Version
  base?: Version
  inspect: (s: string) => void
}) {
  const path = '/api/v1/central-models/' + d.id
  const history = useApi(
    () => apiRequest<Record<string, Measurement>>(path + '/evaluations'),
    [path, d.versions.map((x) => x.version).join(',')],
  )
  const [extra, setExtra] = useState<Record<string, Measurement>>({}),
    [verified, setVerified] = useState<Record<string, string>>({}),
    [section, setSection] = useState(''),
    [busy, setBusy] = useState(false),
    [error, setError] = useState('')
  const [hidden, setHidden] = useState<string[]>([]),
    [round, setRound] = useState('')
  const data = { ...history.data }
  for (const [id, m] of Object.entries(extra)) data[id] = { ...data[id], ...m }
  const a = base ? data[base.version] : undefined,
    b = data[v.version]
  const compatible = Boolean(
    a?.metrics && b?.metrics && a.protocol && a.protocol === b.protocol,
  )
  const bars = compatible
    ? metrics.map(([key, name]) => {
        const left = a!.metrics![key],
          right = b!.metrics![key]
        const diff = pct(right - left)
        return {
          key,
          name,
          baseline: pct(left),
          candidate: pct(right),
          diff,
          color:
            diff === 0
              ? neutral
              : (key === 'false_positive_rate' ? diff < 0 : diff > 0)
                ? good
                : bad,
        }
      })
    : []
  const name = (id: string | null) => {
    const found = d.versions.find((x) => x.version === id)
    return found ? 'V' + found.number : 'Unrecorded'
  }
  const selected = base && base.version !== v.version ? [base, v] : [v]
  const timeline = [...d.versions].sort((x, y) => x.number - y.number)
  const evolution = timeline.map((x) => {
    const m = data[x.version]
    return Object.fromEntries([
      ['name', 'V' + x.number],
      ['ts', date(x.ts)],
      ...metrics.map(([k]) => [
        k,
        m?.metrics && m.protocol === b?.protocol ? pct(m.metrics[k]) : null,
      ]),
    ])
  })
  const all = d.contributions.filter(
    (x) => x.version === v.version && x.state === 'aggregated',
  )
  const rounds = [...new Set(all.map((u) => u.round_number ?? 1))].sort(
    (x, y) => x - y,
  )
  const currentRound = rounds.includes(Number(round))
    ? Number(round)
    : rounds.at(-1)
  const updates = all.filter((u) => (u.round_number ?? 1) === currentRound)
  const total = updates.reduce((s, u) => s + u.count, 0)
  const clients = updates.map((u) => ({
    ...u,
    ...history.data?.[v.version]?.classes?.[u.id],
    name: d.clients.find((c) => c.client === u.client)?.name ?? u.client,
    weight: total ? (100 * u.count) / total : 0,
  }))
  async function operation(section: string, fn: () => Promise<void>) {
    setBusy(true)
    setSection(section)
    setError('')
    try {
      await fn()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }
  const reason = !base
    ? 'Choose a baseline version.'
    : history.loading && !history.data
      ? 'Loading evaluation evidence…'
      : history.error ||
        a?.reason ||
        b?.reason ||
        'The selected evaluations have different holdout or preprocessing provenance.'
  return (
    <div className="space-y-4">
      <Panel title="Model performance comparison">
        {compatible ? (
          <>
            <p>
              {a!.source} → {b!.source} · {b!.test_rows} held-out records ·
              threshold {b!.threshold}
            </p>
            <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-5">
              {bars.map((m) => (
                <div key={m.key} className="rounded-lg border border-line p-3">
                  <h4>{m.name}</h4>
                  <p>
                    V{base!.number} {m.baseline.toFixed(2)}% → V{v.number}{' '}
                    {m.candidate.toFixed(2)}%
                  </p>
                  <strong style={{ color: m.color }}>
                    {m.diff > 0 ? '+' : ''}
                    {m.diff.toFixed(2)} pp ·{' '}
                    {m.diff === 0
                      ? 'Unchanged'
                      : m.color === good
                        ? 'Improved'
                        : 'Regressed'}
                  </strong>
                </div>
              ))}
            </div>
            <h4>Held-out performance (%)</h4>
            <Plot>
              <BarChart data={bars}>
                <CartesianGrid vertical={false} stroke="#334155" />
                <XAxis dataKey="name" tick={{ fill: neutral, fontSize: 11 }} />
                <YAxis domain={[0, 100]} unit="%" />
                <Tooltip
                  contentStyle={tooltip}
                  formatter={(n) => Number(n).toFixed(2) + '%'}
                />
                <Legend />
                <Bar
                  dataKey="baseline"
                  name={'Baseline V' + base!.number}
                  fill={palette[0]}
                />
                <Bar
                  dataKey="candidate"
                  name={'Candidate V' + v.number}
                  fill={palette[1]}
                />
              </BarChart>
            </Plot>
            <h4>Change from baseline (percentage points)</h4>
            <Plot>
              <BarChart data={bars}>
                <XAxis dataKey="name" tick={{ fill: neutral, fontSize: 11 }} />
                <YAxis />
                <ReferenceLine y={0} stroke={neutral} />
                <Tooltip
                  contentStyle={tooltip}
                  formatter={(n) => Number(n).toFixed(2) + ' pp'}
                />
                <Bar dataKey="diff" name="Candidate minus baseline">
                  {bars.map((m) => (
                    <Cell key={m.key} fill={m.color} />
                  ))}
                </Bar>
              </BarChart>
            </Plot>
          </>
        ) : (
          <p role="status">{reason}</p>
        )}
      </Panel>
      <Panel title="Model evolution">
        <div className="flex flex-wrap gap-3">
          {metrics.map(([k, n], i) => (
            <label key={k} style={{ color: palette[i] }}>
              <input
                type="checkbox"
                checked={!hidden.includes(k)}
                onChange={() =>
                  setHidden(
                    hidden.includes(k)
                      ? hidden.filter((x) => x !== k)
                      : [...hidden, k],
                  )
                }
              />{' '}
              {n}
            </label>
          ))}
        </div>
        <Plot>
          <LineChart data={evolution}>
            <CartesianGrid stroke="#334155" />
            <XAxis dataKey="name" />
            <YAxis domain={[0, 100]} unit="%" />
            <Tooltip
              contentStyle={tooltip}
              labelFormatter={(label, payload) =>
                label + ' · ' + (payload[0]?.payload.ts ?? '')
              }
              formatter={(n) => Number(n).toFixed(2) + '%'}
            />
            {metrics.map(
              ([k, n], i) =>
                !hidden.includes(k) && (
                  <Line
                    key={k}
                    type="linear"
                    dataKey={k}
                    name={n}
                    stroke={palette[i]}
                    connectNulls={false}
                    dot
                  />
                ),
            )}
          </LineChart>
        </Plot>
      </Panel>
      <Panel title="Confusion matrix">
        {section === 'evaluation' && (
          <p role="status">{busy ? 'Evaluating saved model…' : error}</p>
        )}
        <div className="grid gap-3 md:grid-cols-2">
          {selected.map((x) => (
            <div key={x.version}>
              <h4>V{x.number}</h4>
              {data[x.version]?.matrix ? (
                <div className="grid grid-cols-2 gap-1">
                  {[
                    ['tp', 'True positives'],
                    ['fp', 'False positives'],
                    ['fn', 'False negatives'],
                    ['tn', 'True negatives'],
                  ].map(([k, n]) => (
                    <p className="rounded bg-navy-800 p-2" key={k}>
                      {n} · {data[x.version].matrix![k]}
                    </p>
                  ))}
                </div>
              ) : (
                <>
                  <p>Prediction counts unavailable.</p>
                  <Button
                    disabled={busy}
                    onClick={() =>
                      operation('evaluation', async () => {
                        const result = await apiRequest<Measurement>(
                          path + '/versions/' + x.version + '/evaluate-heldout',
                          { method: 'POST', timeoutMs: 240000 },
                        )
                        setExtra((prev) => ({ ...prev, [x.version]: result }))
                      })
                    }
                  >
                    Evaluate V{x.number} on holdout
                  </Button>
                </>
              )}
            </div>
          ))}
        </div>
      </Panel>
      <Panel title="Model integrity verification">
        {section === 'integrity' && (
          <p role="status">{busy ? 'Checking artifact…' : error}</p>
        )}
        <p>
          {!base?.weight_hash || !v.weight_hash
            ? 'Hash unavailable'
            : base.weight_hash === v.weight_hash
              ? 'Weight hash unchanged'
              : 'Weight hash changed'}
        </p>
        <div className="grid gap-4 md:grid-cols-2">
          {selected.map((x) => (
            <div key={x.version}>
              <h4>
                {x.version === base?.version ? 'Baseline' : 'Candidate'} V
                {x.number}
              </h4>
              <p>Weight digest</p>
              <Hash value={x.weight_hash} />
              <p>Artifact SHA-256</p>
              <Hash value={x.sha256} />
              <details>
                <summary>Technical details</summary>
                <p>Training duration · {x.training_seconds != null ? x.training_seconds.toFixed(1) + ' seconds' : x.parent ? 'Unavailable' : 'Initialized'}</p>
                <p>Sample contributions across rounds · {d.contributions.filter(u=>u.version===x.version && u.state==='aggregated').reduce((n,u)=>n+u.count,0)}</p>
                <p className="break-all">Version ID · {x.version}</p>
                <p>
                  Parent · {x.parent ? name(x.parent) : 'None'} · {date(x.ts)}
                </p>
                <p>
                  {d.config.architecture} · {x.rounds} rounds ·{' '}
                  {
                    new Set(
                      d.contributions
                        .filter(
                          (u) =>
                            u.version === x.version && u.state === 'aggregated',
                        )
                        .map((u) => u.client),
                    ).size
                  }{' '}
                  contributors
                </p>
              </details>
              <Button
                disabled={busy}
                onClick={() =>
                  operation('integrity', async () => {
                    setVerified((prev) => ({ ...prev, [x.version]: '' }))
                    const r = await apiRequest<{
                      artifact_verified: boolean
                      weight_matches: boolean
                    }>(path + '/versions/' + x.version + '/integrity')
                    setVerified((prev) => ({
                      ...prev,
                      [x.version]: r.artifact_verified
                        ? 'Artifact checksum verified · ' +
                          (r.weight_matches
                            ? 'weight digest matches'
                            : 'weight digest mismatch')
                        : 'Verification failed',
                    }))
                  })
                }
              >
                Verify artifact
              </Button>
              <p role="status">{verified[x.version]}</p>
            </div>
          ))}
        </div>
      </Panel>
      <Panel title="Client contributions">
        <p>
          {registered ?? 'Unknown'} registered workers · {d.clients.length}{' '}
          assigned to model · {d.clients.filter((c) => c.pid).length} connected
          ·{' '}
          {history.data?.[v.version]?.participants?.length ??
            (v.parent ? 'Unrecorded' : 0)}{' '}
          participated in V{v.number} · {clients.length} aggregated in selected
          round
        </p>
        {rounds.length > 0 ? (
          <>
            <label>
              Round{' '}
              <select
                className="bg-navy-800"
                value={currentRound}
                onChange={(e) => setRound(e.target.value)}
              >
                {rounds.map((n) => (
                  <option key={n}>{n}</option>
                ))}
              </select>
            </label>
            <Plot>
              <PieChart>
                <Pie
                  data={clients}
                  dataKey="weight"
                  nameKey="name"
                  innerRadius="45%"
                  outerRadius="75%"
                >
                  {clients.map((c, i) => (
                    <Cell key={c.client} fill={palette[i % palette.length]} />
                  ))}
                </Pie>
                <Legend />
                <Tooltip
                  contentStyle={tooltip}
                  formatter={(n) => Number(n).toFixed(2) + '%'}
                />
              </PieChart>
            </Plot>
            {clients.some((u) => u.benign != null && u.attack != null) ? (
              <Plot>
                <BarChart
                  data={clients.filter(
                    (u) => u.benign != null && u.attack != null,
                  )}
                >
                  <XAxis dataKey="name" />
                  <YAxis allowDecimals={false} />
                  <Legend />
                  <Tooltip contentStyle={tooltip} />
                  <Bar dataKey="benign" stackId="samples" fill={good} />
                  <Bar dataKey="attack" stackId="samples" fill={bad} />
                </BarChart>
              </Plot>
            ) : (
              <p>
                Class counts could not be established from this round’s records.
              </p>
            )}
            {clients.map((u) => (
              <details key={u.id} className="rounded border border-line p-2">
                <summary>
                  {u.name} · {u.organization || 'Unassigned'} at training ·{' '}
                  {u.count} samples · {u.weight.toFixed(2)}%
                </summary>
                {u.benign != null && (
                  <p>
                    {u.benign} benign · {u.attack} attack
                  </p>
                )}
                <p>
                  Current organization ·{' '}
                  {d.clients.find((c) => c.client === u.client)?.organization ||
                    'Unavailable'}
                </p>
                <p className="break-all">
                  Worker {u.client} · {name(u.base)} → {name(u.version)} · Local
                  training completed in {u.duration.toFixed(2)} s · {u.state}
                </p>
                <p>
                  Local weights <Hash value={u.local_hash} />
                </p>
                <p>
                  Update <Hash value={u.digest} />
                </p>
              </details>
            ))}
          </>
        ) : (
          <p>No aggregated updates for this version.</p>
        )}
      </Panel>
      <Panel title="Model lineage">
        {d.round_jobs.map((j) => (
          <p key={j.job} className="rounded border border-line p-3 break-words">
            Round from {name(j.base)} · {j.state} ·{' '}
            {Math.round(j.progress * 100)}% · {j.message}
            <small className="block">
              {new Date(j.created).toLocaleString()} · Job {j.job}
            </small>
          </p>
        ))}
        <ol className="grid gap-2 md:grid-cols-2">
          {timeline.map((x) => {
            const u = d.contributions.filter(
              (c) => c.version === x.version && c.state === 'aggregated',
            )
            const m = data[x.version]?.metrics
            return (
              <li key={x.version}>
                <button
                  aria-pressed={v.version === x.version}
                  className={
                    'w-full rounded-lg border p-3 text-left ' +
                    (v.version === x.version
                      ? 'border-cyan-glow'
                      : 'border-line')
                  }
                  onClick={() => inspect(x.version)}
                >
                  <strong>
                    {x.parent ? name(x.parent) + ' → ' : ''}V{x.number}
                  </strong>{' '}
                  ·{' '}
                  {x.parent
                    ? (data[x.version]?.trigger ?? 'Training')
                    : 'Initialization'}{' '}
                  · {date(x.ts)}
                  <br />
                  {x.state} · {x.version === d.deployed ? 'Active' : 'Inactive'}{' '}
                  · {new Set(u.map((c) => c.client)).size} contributors ·{' '}
                  {u.reduce((s, c) => s + c.count, 0)} sample contributions
                  across rounds
                  <br />
                  {m
                    ? 'Accuracy ' + show(m.accuracy) + ' · F1 ' + show(m.f1)
                    : 'Metrics unavailable'}{' '}
                  · <code>{x.weight_hash ? shortHash(x.weight_hash) : 'Hash unavailable'}</code>
                </button>
              </li>
            )
          })}
        </ol>
      </Panel>
      <Panel title="Automatic retraining history">
        {!d.retraining.length && <p>No automatic runs for this model.</p>}
        {d.retraining.map((r) => (
          <details key={r.id}>
            <summary>
              {name(r.parent)} → {name(r.candidate)} · {r.state}
            </summary>
            <p>
              Job {r.job ?? 'Unrecorded'} · started {r.started ?? 'Unrecorded'}{' '}
              · finished {r.finished ?? 'Unrecorded'}
            </p>
            <p>
              Validation{' '}
              {r.validation
                ? r.validation.passed
                  ? 'passed'
                  : 'rejected'
                : 'unrecorded'}{' '}
              · {r.detail || r.state}
            </p>
            {r.experiment && (
              <a
                className="underline"
                href={'/history?experiment=' + r.experiment}
              >
                Experiment {r.experiment}
              </a>
            )}
            {r.events.map((e) => (
              <p key={e.id}>
                <a className="underline" href={'/security?event=' + e.id}>
                  Event {e.id}
                </a>{' '}
                · {e.client} · {e.organization} ·{' '}
                {e.label === 1
                  ? 'Verified attack'
                  : e.label === 0
                    ? 'Verified benign'
                    : 'Unverified'}{' '}
                ·{' '}
                {e.verified
                  ? date(e.verified)
                  : 'Verification time unavailable'}
              </p>
            ))}
            {d.acks
              .filter((a) => a.run === r.id && a.version === r.candidate)
              .map((a) => (
                <p key={a.client}>
                  {a.client} acknowledged · {date(a.ts)}
                </p>
              ))}
          </details>
        ))}
      </Panel>
    </div>
  )
}
