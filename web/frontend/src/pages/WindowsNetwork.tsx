import { useEffect, useState, type ReactNode } from 'react'
import { ReactFlow, Background, Controls } from '@xyflow/react'
import { api, apiRequest } from '../lib/api'
import { useApi } from '../hooks/useApi'
import { Button } from '../components/ui/Button'
import { Card, CardHeader, CardBody } from '../components/ui/Card'
import { TextInput, Select } from '../components/ui/Field'
import { PageHeader } from '../components/ui/PageHeader'
import { Hash } from '../components/ModelAnalysis'

const root = '/api/v1/native-network'
const request = <T,>(path: string, body?: unknown) =>
  apiRequest<T>(root + path, {
    method: body === undefined ? 'GET' : 'POST',
    body,
    timeoutMs: 180000,
  })
type N = {
  kind: string
  name: string
  ip?: string
  mac?: string
  client?: string
  organization?: string
  synced_version?: string
  neighbors: string[]
  alerts: number
  connected: boolean
  tx: number
  rx: number
  dataset?: string
  dataset_rows?: number
  training?: string
}
type Job = { id: string; status: string; progress: number; message: string }
type Frame = {
  id: string
  src: string
  dst: string
  event: string | null
  run: string | null
  status: string
  ts: number
  scenario: string
  details: {
    outcome: string
    reason?: string
    probability?: number
    version?: string
    weight_hash?: string
    client?: string
    organization?: string
    partition?: string
    csv_row?: number
    duration_ms?: number
  }
}
type Snapshot = {
  network: null | {
    id: string
    nodes: Record<string, N>
    links: string[][]
    state: string
    subnet: string
  }
  scenarios: string[]
  flows: Record<string, unknown>[]
  link_counters?: Record<string, unknown>[]
  events: Frame[]
  jobs: Job[]
  packets: number
  bytes: number
  bps: number
  verified: number
  retraining: number
}
type Capture = {
  available: boolean
  reason: string
  interfaces: { id: string; name: string }[]
  jobs: (Job & {
    protocols: { protocol: string; packets: number; bytes: number }[]
    flows: {
      src: string
      dst: string
      protocol: string
      packets: number
      bytes: number
    }[]
  })[]
}
function Panel({ title, children }: { title: string; children: ReactNode }) {
  return (
    <Card>
      <CardHeader title={title} />
      <CardBody className="space-y-3 text-sm">{children}</CardBody>
    </Card>
  )
}
function Pick({
  label,
  value,
  items,
  set,
}: {
  label: string
  value: string
  items: (string | [string, string])[]
  set: (v: string) => void
}) {
  return (
    <label>
      {label}
      <Select value={value} onChange={(e) => set(e.target.value)}>
        {items.map((i) => {
          const [id, title] = typeof i === 'string' ? [i, i] : i
          return (
            <option key={id} value={id}>
              {title}
            </option>
          )
        })}
      </Select>
    </label>
  )
}
const grid = 'grid gap-3 sm:grid-cols-2 lg:grid-cols-3'
function Num({
  label,
  value,
  set,
  min = 1,
  max = 120,
}: {
  label: string
  value: number
  set: (n: number) => void
  min?: number
  max?: number
}) {
  return (
    <label>
      {label}
      <TextInput
        type="number"
        value={Number.isFinite(value) ? value : ''}
        min={min}
        max={max}
        onChange={(e) => set(e.target.valueAsNumber)}
      />
    </label>
  )
}
function Evidence({ data }: { data: unknown }) {
  return (
    <pre className="max-h-80 overflow-auto whitespace-pre-wrap break-all rounded bg-navy-950 p-3">
      {JSON.stringify(data, null, 2)}
    </pre>
  )
}
export function WindowsNetwork({ live }: { live: boolean }) {
  const [capturePort, setCapturePort] = useState('')
  const state = useApi(
    async () => (live ? null : request<Snapshot>('')),
    [live],
  )
  const captures = useApi(
    async () => (live ? request<Capture>('/capture') : null),
    [live],
  )
  const clients = useApi(() => api.listClients({ limit: 200 }))
  const datasets = useApi(() => api.listDatasets({ limit: 200 }))
  const models = useApi(() =>
    apiRequest<string[]>('/api/v1/predictions/versions'),
  )
  const [busy, working] = useState(false),
    [message, msg] = useState(''),
    [pattern, topology] = useState('single'),
    [subnet, sub] = useState('10.0.0.0/24'),
    [hosts, hostCount] = useState(3),
    [switches, switchCount] = useState(2)
  const [selected, select] = useState(''),
    [peer, setPeer] = useState(''),
    [client, setClient] = useState(''),
    [source, setSrc] = useState(''),
    [dest, setDst] = useState(''),
    [scenario, setScenario] = useState('Normal ICMP'),
    [duration, seconds] = useState(10),
    [rate, setRate] = useState(1),
    [samples, setSamples] = useState(1),
    [partition, setPartition] = useState('test'),
    [offset, setOffset] = useState(0),
    [label, setLabel] = useState('1'),
    [dataset, setDataset] = useState(''),
    [iface, setIface] = useState('')
  const [record, choose] = useState(''),
    [v0, base] = useState(''),
    [v1, candidate] = useState(''),
    [comparison, compare] = useState<unknown>(null)
  const s = state.data,
    g = s?.network,
    nodes = Object.values(g?.nodes ?? {}),
    hs = nodes.filter((n) => n.kind === 'host'),
    ss = nodes.filter((n) => n.kind === 'switch'),
    names = nodes.map((n) => n.name)
  const n = g?.nodes[selected] ?? nodes[0],
    src = hs.some((h) => h.name === source) ? source : (hs[0]?.name ?? ''),
    dst = hs.some((h) => h.name === dest)
      ? dest
      : (hs.find((h) => h.name !== src)?.name ?? ''),
    event = s?.events.find((e) => e.id === record)
  const trace = useApi(
    async () =>
      record
        ? request<{
            security: { id: string } | null
            run: {
              id: string
              experiment: string
              candidate: string
              state: string
              validation: {
                hash_before: string
                hash_after: string
                passed: boolean
              } | null
              parent: string
              detail: string
            } | null
            job_record?: unknown
            contributions: unknown[]
            acks: unknown[]
          }>('/events/' + record + '/trace')
        : null,
    [record, event?.status],
  )
  const refresh = live ? captures.reload : state.reload
  useEffect(() => {
    const t = setInterval(refresh, 2500)
    return () => clearInterval(t)
  }, [refresh])
  async function act(fn: () => Promise<unknown>, success: string) {
    working(true)
    msg('')
    try {
      await fn()
      msg(success)
      refresh()
    } catch (e) {
      msg(e instanceof Error ? e.message : String(e))
    } finally {
      working(false)
    }
  }
  const op = (path: string, body: unknown = {}, success = 'Saved') =>
    act(() => request(path, body), success)
  const edit = (operation: string, body: unknown = {}) =>
    op('/topology/' + operation, body, 'Topology updated')
  const buttons = (jobs: Job[]) =>
    (jobs ?? []).slice(0, 4).map((j) => (
      <p key={j.id} className="break-all">
        {j.status} · {Math.round(j.progress * 100)}% · {j.message}{' '}
        {['running', 'queued'].includes(j.status) && (
          <Button
            disabled={busy}
            onClick={() => op('/jobs/' + j.id + '/stop', {}, 'Stop requested')}
          >
            Stop job
          </Button>
        )}
      </p>
    ))
  const controls = (list: string[], run: (x: string) => void) =>
    list.map((x) => (
      <Button key={x} disabled={busy} onClick={() => run(x)}>
        {x}
      </Button>
    ))
  const chosenInterface = iface || captures.data?.interfaces[0]?.id || ''
  return (
    <div className="space-y-4">
      <PageHeader
        title={live ? 'Windows live traffic capture' : 'Virtual SDN network'}
        actions={<Button onClick={refresh}>Refresh</Button>}
      />
      <p role="status">{message || state.error || captures.error}</p>
      {!live && <Guide />}
      {live ? (
        <Panel title="Passive interface capture">
          <p>
            {captures.data?.reason ||
              'IPv4 and IPv6 metadata · windows.ip.aggregate.v1'}
          </p>
          <div className={grid}>
            <Pick
              label="Authorized Windows interface"
              value={chosenInterface}
              items={(captures.data?.interfaces ?? []).map((i) => [
                i.id,
                i.name,
              ])}
              set={setIface}
            />
            <Pick
              label="Worker for reviewed capture windows"
              value={client}
              set={setClient}
              items={[
                ['', 'Metadata only'],
                ...(clients.data?.items ?? []).map(
                  (c) => [c.id, c.name] as [string, string],
                ),
              ]}
            />
            <Num label="Capture seconds" value={duration} set={seconds} />
            <label>
              Optional TCP/UDP port
              <TextInput
                type="number"
                min={1}
                max={65535}
                value={capturePort}
                onChange={(e) => setCapturePort(e.target.value)}
              />
            </label>
          </div>
          <Button
            disabled={!captures.data?.available || busy || !chosenInterface}
            onClick={() =>
              op(
                '/capture',
                {
                  interface: chosenInterface,
                  port: capturePort ? Number(capturePort) : null,
                  duration,
                  client: client || null,
                },
                'Capture queued',
              )
            }
          >
            Start capture
          </Button>
          {buttons(captures.data?.jobs ?? [])}
          {captures.data?.jobs.map((j) => (
            <details key={j.id}>
              <summary>
                {j.id} · {j.flows.reduce((a, f) => a + f.packets, 0)} packets ·{' '}
                {j.flows.reduce((a, f) => a + f.bytes, 0)} bytes
              </summary>
              <Evidence data={{ protocols: j.protocols, flows: j.flows }} />
              <Samples engine="capture" scope={j.id} />
            </details>
          ))}
        </Panel>
      ) : (
        <>
          {!g ? (
            <Panel title="Create simulated network">
              <div className={grid}>
                <Pick
                  label="Topology"
                  value={pattern}
                  set={topology}
                  items={['single', 'linear', 'star', 'tree', 'custom']}
                />
                <label>
                  IPv4 subnet
                  <TextInput
                    value={subnet}
                    onChange={(e) => sub(e.target.value)}
                  />
                </label>
                <Num
                  label="Hosts"
                  value={hosts}
                  set={hostCount}
                  min={0}
                  max={32}
                />
                <Num
                  label="Switches"
                  value={switches}
                  set={switchCount}
                  max={8}
                />
              </div>
              <Button
                disabled={busy || !s}
                onClick={() =>
                  edit('create', { topology: pattern, subnet, hosts, switches })
                }
              >
                Create network
              </Button>
            </Panel>
          ) : (
            <>
              <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
                {Object.entries({
                  Engine: 'Windows simulation',
                  'Virtual controller': g.state,
                  'Active switches': ss.filter((n) => n.connected).length,
                  'Connected hosts': hs.filter((n) => n.connected).length,
                  'Active links': g.state === 'running' ? g.links.length : 0,
                  'Flow rules': s!.flows.length,
                  'Packets transmitted': s!.packets,
                  'Packets received': s!.packets,
                  'Throughput (bit/s, 5s)': s!.bps,
                  'IDS alerts': hs.reduce((a, n) => a + n.alerts, 0),
                  'Verified attacks': s!.verified,
                  'Retraining jobs': s!.retraining,
                }).map(([k, v]) => (
                  <div
                    className="rounded border border-line bg-navy-900 p-3"
                    key={k}
                  >
                    <small>{k}</small>
                    <p>{v}</p>
                  </div>
                ))}
              </div>
              <Panel title="Virtual topology">
                <div className="flex flex-wrap gap-2">
                  {controls(g.state === 'running' ? ['stop'] : ['start'], edit)}
                  <Button
                    disabled={busy || g.state === 'running'}
                    onClick={() => {
                      if (
                        window.confirm(
                          'Delete this stopped virtual topology? Its event history is retained.',
                        )
                      )
                        void edit('delete')
                    }}
                  >
                    Delete network
                  </Button>
                </div>
                <div className="h-80 rounded bg-navy-950">
                  <ReactFlow
                    key={g.id + names.join(',')}
                    fitView
                    nodesDraggable={false}
                    nodesConnectable={false}
                    nodes={nodes.map((node) => ({
                      id: node.name,
                      position: {
                        x: (node.kind === 'host' ? hs : ss).indexOf(node) * 155,
                        y: node.kind === 'host' ? 160 : 0,
                      },
                      data: {
                        label:
                          node.name +
                          (node.organization ? ' · ' + node.organization : ''),
                      },
                      style: {
                        background: !node.connected
                          ? '#374151'
                          : s!.events.some(
                                (e) =>
                                  e.dst === node.name &&
                                  ['queued', 'training'].includes(e.status),
                              )
                            ? '#684191'
                            : node.alerts
                              ? '#8a3044'
                              : s!.events.some((e) => e.src === node.name)
                                ? '#6e541e'
                                : '#15526b',
                        color: 'white',
                        borderColor:
                          node.name === n?.name ? 'white' : '#374151',
                      },
                    }))}
                    edges={g.links.map(([a, b]) => ({
                      id: a + '-' + b,
                      source: a,
                      target: b,
                    }))}
                    onNodeClick={(_, node) => {
                      select(node.id)
                      setClient(g.nodes[node.id].client ?? '')
                    }}
                  >
                    <Background />
                    <Controls />
                  </ReactFlow>
                </div>
                <div className={grid}>
                  <Pick
                    label="Inspect node"
                    value={n?.name ?? ''}
                    items={names}
                    set={(v) => {
                      select(v)
                      setClient(g.nodes[v].client ?? '')
                    }}
                  />
                  <Pick
                    label="Link peer"
                    value={peer}
                    set={setPeer}
                    items={['', ...names.filter((v) => v !== n?.name)]}
                  />
                </div>
                <div className="flex flex-wrap gap-2">
                  {controls(
                    [
                      'Add host',
                      'Add switch',
                      'Remove node',
                      'Connect',
                      'Disconnect',
                    ],
                    (v) =>
                      edit(
                        {
                          'Add host': 'host',
                          'Add switch': 'switch',
                          'Remove node': 'remove',
                          Connect: 'connect',
                          Disconnect: 'disconnect',
                        }[v]!,
                        { node: n?.name, peer },
                      ),
                  )}
                </div>
                {n && (
                  <>
                    <p>
                      {n.name} · {n.ip} {n.mac} · links{' '}
                      {n.neighbors.join(', ') || 'none'} · TX {n.tx} / RX {n.rx}
                    </p>
                    {n.kind === 'host' && (
                      <>
                        <Pick
                          label="Assign federated client"
                          value={client}
                          set={setClient}
                          items={[
                            ['', 'Unassigned'],
                            ...(clients.data?.items ?? []).map(
                              (c) =>
                                [
                                  c.id,
                                  c.name +
                                    ' · ' +
                                    (c.config.organization ?? 'Unassigned'),
                                ] as [string, string],
                            ),
                          ]}
                        />
                        <Button
                          disabled={busy}
                          onClick={() => edit('map', { node: n.name, client })}
                        >
                          Save host mapping
                        </Button>
                        <p>
                          Assigned worker · {n.client || 'None'} ·{' '}
                          {n.organization} · synchronized version{' '}
                          {n.synced_version || 'No receipt'}
                        </p>
                        <details>
                          <summary>Host details</summary>
                          <Evidence data={n} />
                        </details>
                      </>
                    )}
                  </>
                )}
                <details>
                  <summary>Virtual flow table and link counters</summary>
                  <Evidence
                    data={{ flows: s!.flows, links: s!.link_counters }}
                  />
                </details>
              </Panel>
              <Panel title="Traffic and attack simulation">
                <div className={grid}>
                  <Pick
                    label="Source host"
                    value={src}
                    set={setSrc}
                    items={hs.map((h) => h.name)}
                  />
                  <Pick
                    label="Destination host / worker"
                    value={dst}
                    set={setDst}
                    items={hs.map((h) => [
                      h.name,
                      h.name +
                        ' · ' +
                        (clients.data?.items.find((c) => c.id === h.client)
                          ?.name ?? 'Unassigned'),
                    ])}
                  />
                  <Pick
                    label="Traffic scenario"
                    value={scenario}
                    set={setScenario}
                    items={s!.scenarios}
                  />
                  <Num
                    label="Duration (seconds)"
                    value={duration}
                    set={seconds}
                  />
                  <Num
                    label="Events per second"
                    value={rate}
                    set={setRate}
                    max={20}
                  />
                  <Num
                    label="Sample limit"
                    value={samples}
                    set={setSamples}
                    max={500}
                  />
                  {scenario === 'Labelled dataset replay' && (
                    <>
                      <Pick
                        label="Dataset source"
                        value={dataset}
                        set={setDataset}
                        items={[
                          ['', 'Deployed model source'],
                          ...(datasets.data?.items ?? []).map(
                            (d) => [d.id, d.name] as [string, string],
                          ),
                        ]}
                      />
                      <Pick
                        label="Sample partition"
                        value={partition}
                        set={setPartition}
                        items={[
                          ['test', 'Held-out evaluation'],
                          ['active_train', 'Training partition for review'],
                        ]}
                      />
                      <Pick
                        label="Source annotation"
                        value={label}
                        set={setLabel}
                        items={[
                          ['1', 'Attack'],
                          ['0', 'Benign'],
                        ]}
                      />
                      <Num
                        label="Row offset within class"
                        value={offset}
                        set={setOffset}
                        min={0}
                        max={1000000}
                      />
                    </>
                  )}
                </div>
                <Button
                  disabled={
                    busy || g.state !== 'running' || !dst || src === dst
                  }
                  onClick={() =>
                    op(
                      '/traffic',
                      {
                        source: src,
                        dest: dst,
                        scenario,
                        duration,
                        rate,
                        samples,
                        partition,
                        label: Number(label),
                        dataset: dataset || null,
                        offset,
                      },
                      'Simulation queued',
                    )
                  }
                >
                  Start simulation
                </Button>
                {buttons(s!.jobs)}
              </Panel>
              <Samples engine="simulation" scope={g.id} />
              <Panel title="Attack learning history">
                <div className="max-h-60 overflow-auto">
                  {s!.events.map((e) => (
                    <button
                      key={e.id}
                      className="block w-full border-b border-line p-2 text-left"
                      onClick={() => {
                        choose(e.id)
                        compare(null)
                        void act(
                          () => request('/events/' + e.id + '/inspect', {}),
                          'Event selected',
                        )
                      }}
                    >
                      {new Date(e.ts * 1000).toLocaleTimeString()} · {e.src} →{' '}
                      {e.dst} · {e.scenario} · {e.details.outcome}
                    </button>
                  ))}
                </div>
                {event && (
                  <>
                    <p>
                      {event.details.reason}{' '}
                      {event.details.probability != null &&
                        'Attack probability ' +
                          (event.details.probability * 100).toFixed(2) +
                          '%'}
                    </p>
                    {event.event && (
                      <a
                        className="underline"
                        href={'/security?event=' + event.event}
                      >
                        Review security event
                      </a>
                    )}{' '}
                    {trace.data?.run?.experiment && (
                      <a
                        className="underline"
                        href={
                          '/history?experiment=' + trace.data.run.experiment
                        }
                      >
                        Inspect retraining experiment
                      </a>
                    )}
                    <details>
                      <summary>Event evidence and training lineage</summary>
                      <Hash value={event.details.weight_hash ?? null} />
                      <Evidence data={event} />
                    </details>
                    {trace.data?.security && (
                      <details>
                        <summary>Verification and assignment</summary>
                        <Evidence data={trace.data.security} />
                      </details>
                    )}
                    {trace.data?.run && (
                      <div className="space-y-2">
                        <details>
                          <summary>Retraining job</summary>
                          <Evidence data={trace.data.job_record} />
                        </details>
                        <details>
                          <summary>
                            Client contributions (
                            {trace.data.contributions.length})
                          </summary>
                          {trace.data.contributions.map((u, i) => (
                            <Evidence key={i} data={u} />
                          ))}
                        </details>
                        <details>
                          <summary>Candidate validation and deployment</summary>
                          <p>{trace.data.run.detail}</p>
                          {trace.data.run.validation && (
                            <>
                              <p>
                                {trace.data.run.validation.hash_after ===
                                trace.data.run.validation.hash_before
                                  ? 'Weights unchanged'
                                  : 'Weights changed'}
                              </p>
                              <Hash
                                value={trace.data.run.validation.hash_before}
                              />
                              <Hash
                                value={trace.data.run.validation.hash_after}
                              />
                            </>
                          )}
                          <Evidence data={trace.data.run} />
                        </details>
                        <details>
                          <summary>
                            Synchronization receipts ({trace.data.acks.length})
                          </summary>
                          <Evidence data={trace.data.acks} />
                        </details>
                      </div>
                    )}
                    {event.details.partition === 'test' && (
                      <>
                        <div className={grid}>
                          <Pick
                            label="Baseline version"
                            items={['', ...(models.data ?? [])]}
                            value={v0}
                            set={base}
                          />
                          <Pick
                            label="Candidate version"
                            items={['', ...(models.data ?? [])]}
                            value={v1}
                            set={candidate}
                          />
                        </div>
                        <Button
                          disabled={busy || !v0 || !v1}
                          onClick={() =>
                            act(
                              async () =>
                                compare(
                                  await request(
                                    '/events/' +
                                      event.id +
                                      '/compare?baseline=' +
                                      encodeURIComponent(v0) +
                                      '&candidate=' +
                                      encodeURIComponent(v1),
                                    {},
                                  ),
                                ),
                              'Held-out sample scored',
                            )
                          }
                        >
                          Compare held-out sample
                        </Button>
                        {comparison != null && <Evidence data={comparison} />}
                      </>
                    )}
                  </>
                )}
              </Panel>
            </>
          )}
        </>
      )}
    </div>
  )
}
function Samples({ engine, scope }: { engine: string; scope: string }) {
  const samples = useApi(
    () =>
      request<
        {
          id: string
          client: string
          outcome: string
          label: number | null
          event: string | null
        }[]
      >('/samples/' + engine + '/' + scope),
    [engine, scope],
  )
  const [selected, choose] = useState(''),
    [evidence, note] = useState(''),
    [label, setLabel] = useState('1'),
    [message, msg] = useState(''),
    [busy, setBusy] = useState(false)
  const row = samples.data?.find((r) => r.id === selected)
  const measured = useApi(
    async () => (row ? request('/sample/' + row.id) : null),
    [row?.id, row?.label],
  )
  async function act(publish: boolean, publishScope = scope) {
    setBusy(true)
    try {
      const result = publish
        ? await request<{ dataset: string }>(
            '/publish/' + engine + '/' + publishScope,
            {},
          )
        : await request<{ id: string }>('/samples/' + selected + '/review', {
            label: Number(label),
            evidence,
          })
      msg(JSON.stringify(result))
      samples.reload()
    } catch (e) {
      msg(String(e))
    } finally {
      setBusy(false)
    }
  }
  return (
    <details
      className="rounded border border-line p-3"
      onToggle={(e) => {
        if (e.currentTarget.open) samples.reload()
      }}
    >
      <summary>Review observation windows and publish dataset</summary>
      <div className="space-y-2 py-2">
        <Button onClick={samples.reload}>Refresh windows</Button>
        <Pick
          label="Observation window"
          value={selected}
          set={choose}
          items={[
            '',
            ...(samples.data ?? []).map(
              (r) =>
                [
                  r.id,
                  r.id +
                    ' · ' +
                    r.outcome +
                    ' · ' +
                    (r.label === null ? 'Unreviewed' : r.label),
                ] as [string, string],
            ),
          ]}
        />
        {row && (
          <>
            <details>
              <summary>Measured features and provenance</summary>
              <Evidence data={measured.data ?? measured.error} />
            </details>
            <Pick
              label="Independent label"
              set={setLabel}
              value={label}
              items={[
                ['1', 'Attack'],
                ['0', 'Benign'],
              ]}
            />
            <label>
              Independent evidence
              <TextInput
                value={evidence}
                onChange={(e) => note(e.target.value)}
              />
            </label>
            <Button
              disabled={busy || row.label !== null || !evidence.trim()}
              onClick={() => act(false)}
            >
              Verify window
            </Button>
          </>
        )}
        <Button disabled={busy} onClick={() => act(true)}>
          Publish reviewed CSV
        </Button>
        {engine === 'capture' && (
          <Button disabled={busy} onClick={() => act(true, 'all-reviewed')}>
            Publish reviewed windows across capture sessions
          </Button>
        )}
        <p role="status">{samples.error || message}</p>
      </div>
    </details>
  )
}
function Guide() {
  const [open, setOpen] = useState(
      () => sessionStorage.getItem('securefed.guide.open') === 'true',
    ),
    [mid, setMid] = useState(
      () => sessionStorage.getItem('securefed.guide.model') ?? '',
    )
  const models = useApi(() =>
    apiRequest<{ id: string; name: string }[]>('/api/v1/central-models'),
  )
  const progress = useApi(
    async () =>
      open && mid
        ? request<
            { step: number; label: string; page: string; complete: boolean }[]
          >('/guide/' + mid)
        : null,
    [open, mid],
  )
  useEffect(() => {
    if (!open || !mid) return
    const t = setInterval(progress.reload, 5000)
    return () => clearInterval(t)
  }, [open, mid, progress.reload])
  return (
    <details
      className="rounded border border-line p-3"
      open={open}
      onToggle={(e) => {
        setOpen(e.currentTarget.open)
        sessionStorage.setItem(
          'securefed.guide.open',
          String(e.currentTarget.open),
        )
        if (e.currentTarget.open) models.reload()
      }}
    >
      <summary>Guided demonstration</summary>
      <Pick
        label="Tutorial model"
        value={mid}
        set={(id) => {
          setMid(id)
          sessionStorage.setItem('securefed.guide.model', id)
        }}
        items={[
          '',
          ...(models.data ?? []).map((m) => [m.id, m.name] as [string, string]),
        ]}
      />
      {!mid && (
        <p>
          Upload a CSV in{' '}
          <a className="underline" href="/datasets">
            Datasets
          </a>
          , then create V0 in{' '}
          <a href="/central-model" className="underline">
            Central Model
          </a>{' '}
          and select it here.
        </p>
      )}
      <ol>
        {progress.data?.map((s) => (
          <li key={s.step}>
            {s.complete ? '✓' : '○'} {s.step}.{' '}
            <a className="underline" href={'/' + s.page}>
              {s.label}
            </a>
          </li>
        ))}
      </ol>
      <p>{progress.error}</p>
    </details>
  )
}
