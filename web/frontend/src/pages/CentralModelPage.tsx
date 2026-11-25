import { useEffect, useState, type ReactNode } from 'react'
import { ModelAnalysis, Hash } from '../components/ModelAnalysis'
import { ApiError, api, apiRequest } from '../lib/api'
import { snapshot } from '../lib/sdn'
import { useApi } from '../hooks/useApi'
import { describeError } from '../lib/format'
import { PageHeader } from '../components/ui/PageHeader'
import { Card, CardHeader, CardBody } from '../components/ui/Card'
import { Button } from '../components/ui/Button'
import { TextInput, Select } from '../components/ui/Field'

const request = <T,>(path: string, body?: unknown) =>
  apiRequest<T>('/api/v1/central-models' + path, {
    method: body === undefined ? 'GET' : 'POST',
    body,
    timeoutMs: 300000,
  })
type Model = { id: string; name: string; reference: string; head: string }
export type Version = {
  training_seconds?: number | null
  version: string
  number: number
  rounds: number
  parent: string | null
  state: string
  sha256: string | null
  weight_hash: string | null
  ts: number
  experiment: string | null
  validation: {
    before: Record<string, number>
    after: Record<string, number>
    test_rows: number
    passed: boolean
  } | null
}
type Member = {
  client: string
  name: string
  organization: string
  total: number
  benign: number
  attack: number
  pid: number | null
  status: string
  job: string | null
  message: string | null
}
export type Detail = Model & {
  deployed: string | null
  config: { architecture: string; algorithm: string; method: string }
  versions: Version[]
  clients: Member[]
  contributions: {
    id: string
    client: string
    organization: string
    base: string
    base_hash: string | null
    round_number: number | null
    benign: number | null
    attack: number | null
    count: number
    duration: number
    digest: string
    local_hash: string
    state: string
    version: string | null
  }[]
  acks: {
    run: string
    client: string
    version: string
    pid: number
    ts: number
  }[]
  round_jobs: {
    job: string
    base: string
    state: string
    progress: number
    message: string | null
    created: string
  }[]
  retraining: {
    detail: string
    id: string
    state: string
    parent: string
    candidate: string | null
    job: string | null
    experiment: string | null
    started: string | null
    finished: string | null
    validation: { passed: boolean } | null
    events: {
      id: string
      client: string
      organization: string
      label: number | null
      verified: number | null
    }[]
  }[]
}
function Choices({
  label,
  value,
  onChange,
  options,
  empty,
}: {
  label: string
  value: string
  onChange: (v: string) => void
  options: [string, string][]
  empty?: string
}) {
  return (
    <label className="block text-sm">
      {label}
      <Select
        aria-label={label}
        value={value}
        onChange={(e) => onChange(e.target.value)}
      >
        {empty && <option value="">{empty}</option>}
        {options.map(([v, n]) => (
          <option value={v} key={v}>
            {n}
          </option>
        ))}
      </Select>
    </label>
  )
}
function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="block text-sm">
      {label}
      {children}
    </label>
  )
}
const grid = 'grid gap-3 sm:grid-cols-2 lg:grid-cols-3'
function Table({ headers, rows }: { headers: string[]; rows: ReactNode[][] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-sm">
        <thead>
          <tr>
            {headers.map((h) => (
              <th className="p-2 text-muted" key={h}>
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className="border-t border-line">
              {r.map((v, j) => (
                <td key={j} className="max-w-56 break-all p-2">
                  {v}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
export function CentralConsole({
  mode,
}: {
  mode: 'models' | 'clients' | 'rounds'
}) {
  const models = useApi(() => request<Model[]>(''))
  const datasets = useApi(() => api.listDatasets({ limit: 200 }))
  const registered = useApi(() => api.listClients({ limit: 200 }))
  const restored = useApi(() =>
    apiRequest<string[]>('/api/v1/predictions/versions'),
  )
  const hosts = useApi(
    async () => (mode === 'clients' ? (await snapshot()).hosts : []),
    [mode],
  )
  const [selected, setSelected] = useState('')
  const mid = selected || models.data?.[0]?.id || ''
  const detail = useApi(
    async () => (mid ? request<Detail>('/' + mid) : null),
    [mid],
  )
  const d = detail.data?.id === mid ? detail.data : null
  useEffect(() => {
    if (!mid) return
    const t = setInterval(detail.reload, 5000)
    return () => clearInterval(t)
  }, [mid, detail.reload])
  const [busy, setBusy] = useState(false),
    [message, setMessage] = useState(''),
    [job, setJob] = useState('')
  const jobState = useApi(async () => (job ? api.getJob(job) : null), [job])
  useEffect(() => {
    if (
      !job ||
      ['succeeded', 'failed', 'cancelled'].includes(jobState.data?.status ?? '')
    )
      return
    const t = setInterval(jobState.reload, 2500)
    return () => clearInterval(t)
  }, [job, jobState.data?.status, jobState.reload])
  async function act(fn: () => Promise<string>) {
    setBusy(true)
    setMessage('')
    try {
      setMessage(await fn())
      models.reload()
      detail.reload()
      registered.reload()
    } catch (e) {
      const conflict = e instanceof ApiError && e.status === 409
      const existing = conflict
        ? (e.details as { job_id?: string } | null)?.job_id
        : null
      if (existing) {
        setJob(existing)
        jobState.reload()
        setMessage('This job is already queued or running.')
      } else if (
        conflict &&
        mode === 'clients' &&
        !client &&
        (e.details as { client_id?: string } | null)?.client_id
      ) {
        const match = e.details as { client_id: string; organization: string }
        setClient(match.client_id)
        setOrg(match.organization)
        registered.reload()
        setMessage('Client already exists. Its record is selected.')
      } else setMessage(describeError(e))
    } finally {
      setBusy(false)
    }
  }
  const [name, setName] = useState(''),
    [method, setMethod] = useState('random'),
    [dataset, setDataset] = useState(''),
    [source, setSource] = useState('')
  const [learning, setLearning] = useState('0.0001'),
    [batch, setBatch] = useState('512'),
    [seed, setSeed] = useState('42'),
    [holdout, setHoldout] = useState('0.3'),
    [shards, setShards] = useState('2'),
    [weightFile, setWeights] = useState<File | null>(null),
    [sideFile, setSide] = useState<File | null>(null)
  const [client, setClient] = useState(''),
    [org, setOrg] = useState(''),
    [host, setHost] = useState(''),
    [epochs, setEpochs] = useState('1'),
    [train, setTrain] = useState(true),
    [csv, setCsv] = useState<File | null>(null)
  const [ids, setIds] = useState<string[]>([]),
    [strategy, setStrategy] = useState('stored'),
    [encrypted, setEncrypted] = useState(false),
    [base, setBase] = useState('')
  const [version, setVersion] = useState(''),
    [compare, setCompare] = useState('')
  const v = d?.versions.find((x) => x.version === version) ?? d?.versions[0]
  const other =
    d?.versions.find((x) => x.version === compare) ??
    d?.versions.find((x) => x.version === v?.parent)
  const dsOptions: [string, string][] = (datasets.data?.items ?? [])
    .filter((x) => x.validation_status === 'valid' && x.feature_count === 48)
    .map((x) => [x.id, x.name])
  const datasetId =
    dataset ||
    (mode === 'clients' ? d?.reference : '') ||
    dsOptions[0]?.[0] ||
    ''
  const verOptions: [string, string][] = (d?.versions ?? []).map((x) => [
    x.version,
    'V' + x.number + ' · ' + x.state + ' · ' + x.version,
  ])
  const label = (id: string | null) => {
    const found = d?.versions.find((x) => x.version === id)
    return found ? 'V' + found.number : '—'
  }
  const picker = (
    <Choices
      label="Central model"
      value={mid}
      options={(models.data ?? []).map((m) => [m.id, m.name])}
      empty="Select a model"
      onChange={(k) => {
        setSelected(k)
        setIds([])
        setBase('')
        setVersion('')
        setCompare('')
        setDataset('')
      }}
    />
  )
  const contributions = d?.contributions ?? []
  const activeMemberJob = d?.clients.find(
    (c) =>
      ids.includes(c.client) &&
      ['running', 'queued', 'cancellation_requested'].includes(c.status),
  )?.job
  useEffect(() => {
    if (mode === 'rounds' && activeMemberJob && activeMemberJob !== job)
      setJob(activeMemberJob)
  }, [mode, activeMemberJob, job])
  const jobInfo = jobState.data
  return (
    <div className="space-y-4">
      {mode === 'models' && (
        <Card>
          <CardHeader title="Create Central Model" />
          <CardBody className="space-y-3">
            <div className={grid}>
              <Field label="Model name">
                <TextInput
                  maxLength={90}
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                />
              </Field>
              <Choices
                label="Reference dataset"
                value={datasetId}
                options={dsOptions}
                onChange={setDataset}
              />
              <Choices
                label="Initialization"
                value={method}
                options={[
                  ['random', 'Random weights'],
                  ['import', 'Import pretrained artifacts'],
                  ['restore', 'Restore registered global model'],
                ]}
                onChange={setMethod}
              />
              {method === 'restore' && (
                <Choices
                  label="Source version"
                  empty="Choose version"
                  value={source}
                  options={(restored.data ?? []).map((k) => [k, k])}
                  onChange={setSource}
                />
              )}
              {method === 'import' && (
                <>
                  <Field label="GRU weight artifact">
                    <input
                      type="file"
                      accept=".json"
                      onChange={(e) => setWeights(e.target.files?.[0] ?? null)}
                    />
                  </Field>
                  <Field label="Preprocessing sidecar">
                    <input
                      type="file"
                      accept=".json"
                      onChange={(e) => setSide(e.target.files?.[0] ?? null)}
                    />
                  </Field>
                </>
              )}
            </div>
            <details className="rounded-lg border border-line px-3 py-2">
              <summary className="cursor-pointer text-sm font-medium text-muted">
                Model configuration
              </summary>
              <div className={grid + ' mt-3'}>
                {' '}
                <Field label="Architecture">
                  <TextInput
                    readOnly
                    value="GRU 256 → 128 → 64 · 48 input features"
                  />
                </Field>
                <Field label="Aggregation algorithm">
                  <TextInput readOnly value="Sample-weighted FedAvg" />
                </Field>
                <Field label="Learning rate">
                  <TextInput
                    type="number"
                    step="0.0001"
                    value={learning}
                    onChange={(e) => setLearning(e.target.value)}
                  />
                </Field>
                <Field label="Batch size">
                  <TextInput
                    type="number"
                    value={batch}
                    onChange={(e) => setBatch(e.target.value)}
                  />
                </Field>
                <Field label="Reference training shards">
                  <TextInput
                    type="number"
                    min="2"
                    max="12"
                    value={shards}
                    onChange={(e) => setShards(e.target.value)}
                  />
                </Field>
                <Field label="Split seed">
                  <TextInput
                    type="number"
                    min="0"
                    value={seed}
                    onChange={(e) => setSeed(e.target.value)}
                  />
                </Field>
                <Field label="Holdout fraction">
                  <TextInput
                    type="number"
                    step="0.01"
                    min="0.01"
                    max="0.99"
                    value={holdout}
                    onChange={(e) => setHoldout(e.target.value)}
                  />
                </Field>
              </div>
            </details>
            <Button
              disabled={
                busy ||
                !name.trim() ||
                !datasetId ||
                (method === 'restore' && !source) ||
                (method === 'import' && (!weightFile || !sideFile))
              }
              onClick={() =>
                act(async () => {
                  const r = await request<{ id: string }>('', {
                    name,
                    dataset: datasetId,
                    method,
                    source,
                    learning_rate: Number(learning),
                    batch_size: Number(batch),
                    shards: Number(shards),
                    seed: Number(seed),
                    test_size: Number(holdout),
                    ...(method === 'import'
                      ? {
                          weights: JSON.parse(await weightFile!.text()),
                          preprocessing: JSON.parse(await sideFile!.text()),
                        }
                      : {}),
                  })
                  setSelected(r.id)
                  setName('')
                  return 'V0 initialized.'
                })
              }
            >
              Create V0
            </Button>
          </CardBody>
        </Card>
      )}
      <Card>
        <CardHeader
          title={
            mode === 'models'
              ? 'Model versions'
              : mode === 'clients'
                ? 'Central model client assignment'
                : 'Central federated round'
          }
        />
        <CardBody className="space-y-3">
          {picker}
          {!d && (
            <p className="text-sm">
              {detail.error ||
                models.error ||
                'Create or select a central model to continue.'}
            </p>
          )}
          {d && mode === 'clients' && (
            <>
              <div className={grid}>
                <Choices
                  label="Registered client"
                  value={client}
                  onChange={(id) => {
                    setClient(id)
                    setOrg(
                      String(
                        registered.data?.items.find((c) => c.id === id)?.config
                          .organization ?? '',
                      ),
                    )
                  }}
                  empty="Create new client"
                  options={(registered.data?.items ?? []).map((c) => [
                    c.id,
                    c.name + ' · ' + c.id,
                  ])}
                />
                {!client && (
                  <Field label="New client name">
                    <TextInput
                      value={name}
                      onChange={(e) => setName(e.target.value)}
                    />
                  </Field>
                )}
                <Field label="Organization">
                  <TextInput
                    value={org}
                    onChange={(e) => setOrg(e.target.value)}
                  />
                </Field>
                <Choices
                  label="SDN host"
                  value={host}
                  onChange={setHost}
                  empty="Keep current mapping"
                  options={(hosts.data ?? [])
                    .filter((h) => !h.client || h.client === client)
                    .map((h) => [h.name, h.name + ' · ' + h.ip])}
                />
                <Choices
                  label="Assign local dataset"
                  value={datasetId}
                  options={dsOptions}
                  onChange={setDataset}
                />
                <Field label="Or upload client CSV">
                  <input
                    type="file"
                    accept=".csv"
                    onChange={(e) => setCsv(e.target.files?.[0] ?? null)}
                  />
                </Field>
                <Field label="Local epochs">
                  <TextInput
                    type="number"
                    min="1"
                    max="50"
                    value={epochs}
                    onChange={(e) => setEpochs(e.target.value)}
                  />
                </Field>
              </div>
              <label className="block text-sm">
                <input
                  type="checkbox"
                  checked={train}
                  onChange={(e) => setTrain(e.target.checked)}
                />{' '}
                Train on assignment
              </label>
              <Button
                disabled={
                  busy || (!client && !name.trim()) || (!datasetId && !csv)
                }
                onClick={() =>
                  act(async () => {
                    const local = csv
                      ? (
                          await api.uploadDataset({
                            file: csv,
                            datasetType: 'insdn',
                          })
                        ).id
                      : datasetId
                    const r = await request<{ client: string; job?: string }>(
                      '/' + mid + '/members',
                      {
                        name,
                        client: client || null,
                        organization: org,
                        dataset: local,
                        host: host || null,
                        epochs: Number(epochs),
                        train,
                      },
                    )
                    setJob(r.job ?? '')
                    if (!client) {
                      setName('')
                      setOrg('')
                      setHost('')
                    }
                    datasets.reload()
                    hosts.reload()
                    return 'Assigned worker ' + r.client
                  })
                }
              >
                Save client assignment
              </Button>
            </>
          )}
          {d && mode === 'rounds' && (
            <>
              <div className={grid}>
                <Choices
                  label="Base version"
                  value={base || d.head}
                  options={verOptions}
                  onChange={setBase}
                />
                <Choices
                  label="Round operation"
                  value={strategy}
                  onChange={(k) => {
                    setStrategy(k)
                    setEncrypted(false)
                  }}
                  options={[
                    ['stored', 'Aggregate stored local updates'],
                    ['fresh', 'Train fresh and aggregate'],
                    ['local', 'Train and store local updates'],
                  ]}
                />
              </div>
              <fieldset>
                <legend className="text-sm">Participating workers</legend>
                {d.clients.map((c) => (
                  <label className="block text-sm" key={c.client}>
                    <input
                      type="checkbox"
                      disabled={!c.pid}
                      checked={ids.includes(c.client)}
                      onChange={(e) =>
                        setIds(
                          e.target.checked
                            ? [...ids, c.client]
                            : ids.filter((k) => k !== c.client),
                        )
                      }
                    />{' '}
                    {c.name} · {c.organization} · {c.client} ·{' '}
                    {c.pid ? 'Connected' : 'Disconnected'}
                  </label>
                ))}
              </fieldset>
              {strategy === 'fresh' && (
                <label className="block">
                  <input
                    type="checkbox"
                    checked={encrypted}
                    onChange={(e) => setEncrypted(e.target.checked)}
                  />{' '}
                  Require CKKS encryption
                </label>
              )}
              <Button
                disabled={
                  busy ||
                  Boolean(activeMemberJob) ||
                  (jobInfo &&
                    ['running', 'queued', 'cancellation_requested'].includes(
                      jobInfo.status,
                    )) === true ||
                  ids.length < (strategy === 'local' ? 1 : 2) ||
                  (base || d.head) !== d.head
                }
                onClick={() =>
                  act(async () => {
                    const r = await request<{ job: string }>(
                      '/' + mid + '/rounds',
                      {
                        action: strategy,
                        base: base || d.head,
                        clients: ids,
                        encrypted,
                      },
                    )
                    setJob(r.job)
                    return 'Round submitted.'
                  })
                }
              >
                Run selected operation
              </Button>
            </>
          )}
          {d && mode === 'models' && v && (
            <>
              <div className="grid gap-3 sm:grid-cols-3">
                <div className="rounded-lg bg-navy-950 p-3">
                  <p className="text-sm font-medium">
                    Deployed · {label(d.deployed)}
                  </p>
                  <p className="text-xs text-muted">{d.config.architecture}</p>
                </div>
                <div className="rounded-lg bg-navy-950 p-3">
                  <p className="text-xs text-muted">Connected workers</p>
                  <p className="text-lg font-semibold">
                    {d.clients.filter((c) => c.pid).length}
                  </p>
                </div>
                <div className="rounded-lg bg-navy-950 p-3">
                  <p className="text-xs text-muted">
                    Contributors to V{v.number}
                  </p>
                  <p className="text-lg font-semibold">
                    {
                      new Set(
                        contributions
                          .filter((u) => u.version === v.version)
                          .map((u) => u.client),
                      ).size
                    }
                  </p>
                </div>
              </div>
              <div className={grid}>
                <Choices
                  label="Inspect version"
                  value={v.version}
                  options={verOptions}
                  onChange={setVersion}
                />
                <Choices
                  label="Compare with"
                  value={other?.version ?? ''}
                  empty="Choose version"
                  options={verOptions}
                  onChange={setCompare}
                />
              </div>
              <ModelAnalysis
                registered={registered.data?.total}
                key={d.id}
                d={d}
                v={v}
                base={other}
                inspect={setVersion}
              />
              <h3 className="text-base font-semibold">
                Deployment and synchronization
              </h3>
              <div className="flex flex-wrap gap-2">
                {(['deploy', 'rollback', 'sync'] as const).map((op) => (
                  <Button
                    key={op}
                    disabled={
                      busy ||
                      (op === 'sync'
                        ? v.version !== d.deployed
                        : op === 'rollback'
                          ? v.state !== 'deployed' || v.version === d.deployed
                          : v.state !== 'validated' || v.parent !== d.head)
                    }
                    onClick={() =>
                      act(async () => {
                        await request(
                          '/' + mid + '/versions/' + v.version + '/' + op,
                          {},
                        )
                        return 'Completed ' + op + ' for V' + v.number
                      })
                    }
                  >
                    {op === 'deploy'
                      ? 'Deploy validated version'
                      : op === 'rollback'
                        ? 'Roll back to version'
                        : 'Synchronize workers'}
                  </Button>
                ))}
              </div>
              {d.acks.length > 0 && (
                <Table
                  headers={[
                    'Synchronized version',
                    'Client',
                    'Worker PID',
                    'Acknowledged',
                  ]}
                  rows={d.acks.map((a) => [
                    label(a.version),
                    a.client,
                    a.pid,
                    new Date(a.ts * 1000).toLocaleString(),
                  ])}
                />
              )}
            </>
          )}
          {d && d.clients.length > 0 && (
            <Table
              headers={[
                'Client / organization',
                'Dataset rows',
                'Eligible benign / attack',
                'Connection',
                'Local job',
              ]}
              rows={d.clients.map((c) => [
                c.name + ' · ' + c.organization + ' · ' + c.client,
                c.total,
                c.benign + ' / ' + c.attack,
                c.pid ? 'PID ' + c.pid : 'Disconnected',
                c.status + (c.message ? ' · ' + c.message : ''),
              ])}
            />
          )}
          {mode !== 'models' && d && contributions.length > 0 && (
            <Table
              headers={[
                'Client / organization',
                'Base → candidate',
                'Round / starting weight hash',
                'Samples',
                'Local seconds',
                'Local weight hash',
                'Update hash',
                'Status',
              ]}
              rows={contributions.map((u) => [
                u.client + ' · ' + u.organization,
                label(u.base) + ' → ' + label(u.version),
                <span>
                  {u.round_number} · <Hash value={u.base_hash} />
                </span>,
                u.count,
                u.duration.toFixed(2),
                <Hash value={u.local_hash} />,
                <Hash value={u.digest} />,
                u.state,
              ])}
            />
          )}
          <p role="status" className="break-all text-sm">
            {message || detail.error || models.error || datasets.error}
            {jobInfo &&
              ' · ' +
                jobInfo.status +
                ' · ' +
                Math.round(jobInfo.progress * 100) +
                '% · ' +
                (jobInfo.error || jobInfo.message || '')}
          </p>
        </CardBody>
      </Card>
    </div>
  )
}
export function CentralModelPage() {
  return (
    <>
      <PageHeader title="Central Model" />
      <CentralConsole mode="models" />
    </>
  )
}
