import { useEffect, useState } from 'react'
import { Background, Controls, ReactFlow, type Node } from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import {
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { Link } from 'react-router-dom'
import { useApi } from '../hooks/useApi'
import { api } from '../lib/api'
import { describeError } from '../lib/format'
import {
  snapshot,
  labRequest,
  type Capture,
  type LabSpec,
  type LabSnapshot,
} from '../lib/sdn'
import { PageHeader } from '../components/ui/PageHeader'
import { Card, CardBody, CardHeader } from '../components/ui/Card'
import { Button } from '../components/ui/Button'
import { Select, TextInput } from '../components/ui/Field'
import type { AttackReplay } from '../lib/types'

const defaults: LabSpec = {
  topology: 'linear',
  switches: 2,
  hosts: 5,
  controller: '127.0.0.1',
  port: 16653,
  subnet: '10.0.0.0/24',
}

function Topology({
  s,
  select,
}: {
  s: LabSnapshot
  select: (id: string) => void
}) {
  const node = (
    id: string,
    label: string,
    x: number,
    y: number,
    highlight = false,
  ): Node => ({
    id,
    position: { x, y },
    data: { label },
    style: {
      background: '#102036',
      borderColor: highlight ? '#fb923c' : '#2a6573',
      color: '#eef6ff',
    },
  })
  const nodes = [
    node('controller', 'OpenFlow controller', 0, 100),
    ...s.switches.map((sw, i) => node(sw.name, sw.name, 220, i * 95)),
    ...s.hosts.map((h, i) =>
      node(
        h.name,
        h.name + ' Â· ' + h.ip + (h.client ? ' Â· FL' : ''),
        460,
        i * 70,
        h.alerts > 0,
      ),
    ),
  ]
  const edges = [
    ...s.switches
      .filter((sw) => sw.connected)
      .map((sw) => ({
        id: 'c' + sw.name,
        source: 'controller',
        target: sw.name,
      })),
    ...s.links.map((l) => ({
      id: l.source_port + '-' + l.target_port,
      source: l.source,
      target: l.target,
      label: l.source_port,
      style: { stroke: l.up ? '#45c5bc' : '#726b78' },
    })),
  ]
  return (
    <div style={{ height: 350 }}>
      <ReactFlow
        className="dark"
        nodes={nodes}
        edges={edges}
        nodesDraggable={false}
        nodesConnectable={false}
        fitView
        onNodeClick={(_, n) => select(n.id)}
      >
        <Controls />
        <Background />
      </ReactFlow>
    </div>
  )
}

export function SdnPage() {
  const network = useApi(snapshot)
  const clients = useApi(() => api.listClients({ limit: 200 }))
  const model = useApi(api.predictionStatus)
  const [spec, setSpec] = useState<LabSpec>(defaults)
  const [node, setNode] = useState('')
  const [host, setHost] = useState('')
  const [client, setClient] = useState('')
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const [normalProbe, setNormalProbe] = useState(false)
  const [capture, setCapture] = useState<Capture | null>(null)
  const [reviewEvidence,setReviewEvidence]=useState<Record<string,string>>({})
  const [activity, setActivity] = useState(0)
  const [trainingReplay,setTrainingReplay]=useState(false)
  const [offset, setOffset] = useState(0)
  const s = network.data
  const selected = s?.hosts.find((h) => h.name === host)
  const samples = useApi(
    async () =>
      selected?.client
        ? labRequest<
            { id: string; features: number[]; label: number | null }[]
          >('hosts/' + host + '/samples')
        : [],
    [host, selected?.client, activity, s?.lab_id],
  )
  const refresh = network.reload
  useEffect(() => {
    if (!s?.running || busy) return
    const timer = setInterval(refresh, 5000)
    return () => clearInterval(timer)
  }, [s?.running, busy, refresh])
  function selectHost(name: string) {
    setHost(name)
    setCapture(null)
    setClient('')
    setOffset(0)
    setMessage('')
  }
  async function run(task: () => Promise<string>) {
    setBusy(true)
    setMessage('')
    try {
      setMessage(await task())
      setActivity((n) => n + 1)
    } catch (e) {
      setMessage(describeError(e))
    } finally {
      setBusy(false)
      refresh()
    }
  }
  const state = network.error ? 'unavailable' : (s?.state ?? 'unavailable')
  const last = s?.history.at(-1)
  const metrics = [
    ['Controller', state],
    ['Active switches', s?.switches.filter((x) => x.connected).length],
    ['Connected hosts', s?.hosts.filter((x) => x.connected).length],
    ['Active links', s?.links.filter((x) => x.up).length],
    ['Flow rules', s?.flows.length],
    ['Host packets sent', s?.packets],
    [
      'Throughput',
      last ? ((last.bps * 8) / 1000).toFixed(2) + ' kbit/s' : null,
    ],
    ['IDS alerts', s?.hosts.reduce((n, h) => n + h.alerts, 0)],
  ]
  const detail =
    node === 'controller'
      ? s?.config
      : (s?.hosts.find((h) => h.name === node) ??
        s?.switches.find((sw) => sw.name === node))
  const hostEvents = s?.events.filter((event) => event.host === node) ?? []
  const locked = busy || !!s?.config
  const options = s?.config ?? spec
  return (
    <div className="space-y-4">
      <PageHeader
        title="SDN Network"
        description={network.error ?? s?.reason ?? 'Checking lab agentâ€¦'}
        actions={<Button onClick={refresh}>Refresh topology</Button>}
      />
      <div className="grid gap-2 sm:grid-cols-4">
        {metrics.map(([name, value], i) => (
          <Card key={name}>
            <CardBody>
              <small>{name}</small>
              <p className="text-xl text-ink">
                {i > 0 && (!s?.running || network.error) ? 'â€”' : (value ?? 'â€”')}
              </p>
            </CardBody>
          </Card>
        ))}
      </div>
      <Card>
        <CardHeader
          title="Mininet lab configuration"
        />
        <CardBody className="space-y-3">
          <div className="grid gap-3 sm:grid-cols-3">
            <label>
              Topology
              <Select
                disabled={locked}
                value={options.topology}
                onChange={(e) =>
                  setSpec({
                    ...spec,
                    topology: e.target.value as LabSpec['topology'],
                    switches: e.target.value === 'single' ? 1 : spec.switches,
                  })
                }
              >
                {['single', 'linear', 'tree'].map((t) => (
                  <option key={t}>{t}</option>
                ))}
              </Select>
            </label>
            {(
              ['switches', 'hosts', 'subnet', 'controller', 'port'] as const
            ).map((k) => (
              <label key={k} className="capitalize">
                {k}
                <TextInput
                  disabled={locked}
                  value={options[k]}
                  type={typeof spec[k] === 'number' ? 'number' : 'text'}
                  onChange={(e) =>
                    setSpec({
                      ...spec,
                      [k]:
                        typeof spec[k] === 'number'
                          ? Number(e.target.value)
                          : e.target.value,
                    })
                  }
                />
              </label>
            ))}
          </div>
          <div className="flex flex-wrap gap-2">
            {(['create', 'start', 'stop', 'delete'] as const).map((a) => (
              <Button
                key={a}
                disabled={
                  busy ||
                  state === 'unavailable' ||
                  (a === 'create'
                    ? !!s?.config
                    : a === 'start' || a === 'delete'
                      ? !s?.config || s.running
                      : !s?.running)
                }
                onClick={() =>
                  run(async () => {
                    await labRequest('lab/' + a, a === 'create' ? spec : {})
                    selectHost('')
                    setNode('')
                    return 'Lab operation completed.'
                  })
                }
              >
                {a[0].toUpperCase() + a.slice(1)} network
              </Button>
            ))}
          </div>
        </CardBody>
      </Card>
      {message && (
        <p
          role="status"
          className="whitespace-pre-wrap rounded border border-line p-3"
        >
          {message}
        </p>
      )}
      {s?.running && (
        <>
          <Card>
            <CardHeader
              title="Network topology"
            />
            <Topology
              s={s}
              select={(id) => {
                setNode(id)
                if (s.hosts.some((h) => h.name === id)) selectHost(id)
              }}
            />
            {detail && (
              <pre className="overflow-auto p-3">
                {JSON.stringify(detail, null, 2)}
              </pre>
            )}
            {hostEvents.slice(0, 5).map((event, i) => (
              <p className="px-3 pb-2" key={i}>
                {event.kind} Â· {event.result.label ? 'Attack' : 'Benign'} Â·{' '}
                {(100 * event.result.prediction).toFixed(2)}% attack probability
              </p>
            ))}
          </Card>
          <Card>
            <CardHeader title="Host inventory" />
            <CardBody className="overflow-auto">
              <table className="w-full text-left text-sm">
                <thead>
                  <tr>
                    {[
                      'Host',
                      'IP / MAC',
                      'Switch port',
                      'State',
                      'TX / RX packets',
                      'Client / worker',
                      'Host model version',
                      'Deployed participation',
                      'Alerts',
                    ].map((v) => (
                      <th key={v}>{v}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {s.hosts.map((h) => {
                    const c = clients.data?.items.find((x) => x.id === h.client)
                    return (
                      <tr key={h.name}>
                        <td>{h.name}</td>
                        <td>
                          {h.ip}
                          <br />
                          {h.mac}
                        </td>
                        <td>
                          {h.switch} / {h.port}
                        </td>
                        <td>{h.connected ? 'Up' : 'Down'}</td>
                        <td>
                          {h.tx_packets} / {h.rx_packets}
                        </td>
                        <td>
                          {c?.name ?? h.client ?? 'Unmapped'}<br/>{h.organization || 'Unassigned organization'}<br/>{h.client}<br/>{h.retraining}
                          <br />
                          {c
                            ? c.runtime_connected
                              ? 'Local PID ' + c.worker_pid
                              : 'Worker offline'
                            : ''}
                        </td>
                        <td>
                          Unreported
                        </td>
                        <td>
                          {h.client &&
                          model.data?.participants?.includes(h.client)
                            ? model.data.version
                            : 'â€”'}
                        </td>
                        <td>{h.alerts}</td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </CardBody>
          </Card>
          <Card>
            <CardHeader
              title="Host testing and reviewed samples"
            />
            <CardBody className="space-y-3">
              <label>
                Lab host
                <Select aria-label="Lab host"
                  disabled={busy}
                  value={host}
                  onChange={(e) => selectHost(e.target.value)}
                >
                  <option value="">Choose host</option>
                  {s.hosts.map((h) => (
                    <option key={h.name}>{h.name}</option>
                  ))}
                </Select>
              </label>
              <label>
                Federated client
                <Select
                  disabled={busy}
                  value={client}
                  onChange={(e) => setClient(e.target.value)}
                >
                  <option value="">Choose client</option>
                  {clients.data?.items.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name}
                    </option>
                  ))}
                </Select>
              </label>
              <div className="flex flex-wrap gap-2">
                <Button
                  disabled={busy || !client || !selected}
                  onClick={() =>
                    run(async () => {
                      await labRequest('hosts/' + host + '/map/' + client, {})
                      return 'Client mapped.'
                    })
                  }
                >
                  Map client
                </Button>
                <Button
                  disabled={busy || !selected || host === s.hosts.at(-1)?.name}
                  onClick={() =>
                    run(async () => {
                      const r = await labRequest<{ output: string }>(
                        'hosts/' + host + '/ping',
                        {},
                      )
                      return r.output
                    })
                  }
                >
                  Send normal ping
                </Button>
                <Button
                  disabled={busy || !selected?.client}
                  onClick={() =>
                    run(async () => {
                      const r = await labRequest<AttackReplay>(
                        'hosts/' + host + '/replay?partition='+(trainingReplay?'active_train':'test')+'&offset=' + offset,
                        {},
                      )
                      setOffset(offset + 1)
                      return (
                        'Recorded attack row ' +
                        r.csv_row +
                        ' Â· ' +
                        (r.label ? 'Detected' : 'Missed') +
                        ' Â· ' +
                        (100 * r.prediction).toFixed(2) +
                        '% attack probability'
                      )
                    })
                  }
                >
                  Replay labeled attack
                </Button><label><input type="checkbox" checked={trainingReplay} onChange={event=>{setTrainingReplay(event.target.checked);setOffset(0)}}/> Replay training partition for independent review</label>
                <label>
                  <input
                    type="checkbox"
                    checked={normalProbe}
                    onChange={(e) => setNormalProbe(e.target.checked)}
                  />{' '}
                  Include normal ICMP during capture
                </label>
                <Button
                  disabled={busy || !selected?.client}
                  onClick={() =>
                    run(async () => {
                      const r = await labRequest<Capture>(
                        'hosts/' +
                          host +
                          '/capture?normal_probe=' +
                          normalProbe,
                        {},
                      )
                      setCapture(r)
                      return r.prediction
                        ? 'Live attack probability ' +
                            (r.prediction.prediction * 100).toFixed(2) +
                            '%'
                        : 'Captured 12 counter intervals. Deploy a model trained on this counter schema to score live windows.'
                    })
                  }
                >
                  Capture host window
                </Button>
                <Button
                  disabled={busy}
                  onClick={() =>
                    run(async () => {
                      const r = await labRequest<{
                        dataset_id: string
                        rows: number
                      }>('dataset', {})
                      return (
                        'Published ' +
                        r.rows +
                        ' reviewed rows Â· dataset ' +
                        r.dataset_id
                      )
                    })
                  }
                >
                  Publish reviewed dataset
                </Button>
              </div>
              {capture && (
                <p>
                  Observed IPv4 flows (up to 100):{' '}
                  {capture.observed_flows.length} Â· Packets by IP protocol:{' '}
                  {Object.entries(
                    capture.observed_flows.reduce<Record<number, number>>(
                      (sum, f) => {
                        sum[f.protocol] = (sum[f.protocol] ?? 0) + f.packets
                        return sum
                      },
                      {},
                    ),
                  )
                    .map(([p, n]) => p + ' = ' + n)
                    .join(', ') || 'None observed'}
                </p>
              )}
              {capture && (
                <pre className="overflow-auto">
                  Observed IPv4 flows during capture{'\n'}
                  {JSON.stringify(capture.observed_flows, null, 2)}
                </pre>
              )}
              {samples.data?.map((r) => (
                <details key={r.id}>
                  <summary>
                    {r.id} Â·{' '}
                    {r.label === null
                      ? 'Awaiting review'
                      : r.label
                        ? 'Approved attack'
                        : 'Approved benign'}
                  </summary>
                  <p className="break-all">{r.features.join(', ')}</p>
                  <label>Independent label evidence<TextInput maxLength={500} value={reviewEvidence[r.id] ?? ''} onChange={e=>setReviewEvidence({...reviewEvidence,[r.id]:e.target.value})}/></label>
                  {[0, 1].map((v) => (
                    <Button
                      key={v}
                      disabled={busy || !reviewEvidence[r.id]?.trim()}
                      onClick={() =>
                        run(async () => {
                          await labRequest(
                            'samples/' + r.id + '/approve?label=' + v + '&evidence=' + encodeURIComponent(reviewEvidence[r.id]),
                            {},
                          )
                          return 'Operator label saved.'
                        })
                      }
                    >
                      Approve {v ? 'attack' : 'benign'}
                    </Button>
                  ))}
                </details>
              ))}
              <Link className="underline" to="/training">
                Train and deploy a reviewed dataset
              </Link>
            </CardBody>
          </Card>
          <Card>
            <CardHeader
              title="Traffic history"
            />
            <CardBody>
              <ResponsiveContainer width="100%" height={190}>
                <LineChart data={s.history}>
                  <XAxis
                    dataKey="time"
                    tickFormatter={(v) =>
                      new Date(v * 1000).toLocaleTimeString()
                    }
                  />
                  <YAxis />
                  <Tooltip />
                  <Line dataKey="bps" name="Bytes/s" stroke="#46d4e6" />
                  <Line dataKey="pps" name="Packets/s" stroke="#ffa94d" />
                </LineChart>
              </ResponsiveContainer>
            </CardBody>
          </Card>
          <Card>
            <CardHeader title="Switch inventory and OpenFlow 1.3 rules" />
            <CardBody>
              {s.switches.map((sw) => (
                <details key={sw.name}>
                  <summary>
                    {sw.name} Â· {sw.dpid} Â·{' '}
                    {sw.connected ? 'Connected' : 'Disconnected'}
                  </summary>
                  <pre className="overflow-auto">
                    {JSON.stringify(sw.ports, null, 2)}
                    {'\n'}
                    {s.flows
                      .filter((f) => f.switch === sw.name)
                      .map((f) => f.rule)
                      .join('\n')}
                  </pre>
                </details>
              ))}
            </CardBody>
          </Card>
        </>
      )}
    </div>
  )
}
