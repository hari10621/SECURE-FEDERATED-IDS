import { SecurityAudit } from '../components/SecurityAudit'
import { EventHistory } from '../components/AutomaticRetraining'
import { useState } from 'react'
import { Alert } from '../components/ui/Alert'
import { Button } from '../components/ui/Button'
import { Card, CardBody, CardHeader } from '../components/ui/Card'
import { Field, Select } from '../components/ui/Field'
import { PageHeader } from '../components/ui/PageHeader'
import { useApi } from '../hooks/useApi'
import { labRequest, type LabSnapshot } from '../lib/sdn'
import { api } from '../lib/api'
import { describeError } from '../lib/format'
import type { AttackReplay } from '../lib/types'

export function SecurityPage() {
  const clients = useApi(() => api.listClients({limit: 200}))
  const labEvents = useApi(() => labRequest<{state:string;reason:string;items:LabSnapshot['events']}>('inventory/events'))
  const model = useApi(api.predictionStatus)
  const [clientId, setClientId] = useState('')
  const [offset, setOffset] = useState(0)
  const [receipt, setReceipt] = useState<AttackReplay | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const selected = clients.data?.items.find(client => client.id === clientId)
  async function replay() {
    setBusy(true)
    setReceipt(null)
    setError('')
    try {
      setReceipt(await api.replayAttack(clientId, offset))
      setOffset(offset + 1)
    } catch (cause) {
      setError(describeError(cause))
    } finally {
      setBusy(false)
    }
  }
  return <div className="space-y-4">
    <PageHeader title="Security Monitoring"
      actions={<Button disabled={busy} onClick={() => {clients.reload(); model.reload(); labEvents.reload()}}>Refresh</Button>} />
    <Card><CardHeader title="Client attack replay" />
      <CardBody className="space-y-4">
        <Field label="Federated client" htmlFor="replay-client"><Select id="replay-client" disabled={busy} value={clientId} onChange={event => {
          setClientId(event.target.value); setOffset(0); setReceipt(null); setError('')
        }}>
          <option value="">Select a client</option>
          {clients.data?.items.map(client => <option key={client.id} value={client.id}>{client.name} · {client.runtime_connected ? 'Connected' : 'Disconnected'}</option>)}
        </Select></Field>
        {selected && !selected.runtime_connected && <p>Enable this worker under Federated Clients, then refresh.</p>}
        {(clients.error || model.error || (model.data && !model.data.available)) && <Alert tone="warning">{clients.error || model.error || model.data?.reason}</Alert>}
        <Button disabled={busy || !selected?.runtime_connected || !model.data?.available || !!clients.error || !!model.error} onClick={replay}>{busy ? 'Replaying…' : 'Replay attack sample'}</Button>
        {error && <Alert tone="danger">{error}</Alert>}
      </CardBody></Card>
    {receipt && <Card><CardHeader title={receipt.label === 1 ? 'Attack detected' : 'Attack missed'} description={receipt.client_name + ' · held-out CSV row ' + receipt.csv_row + ' · actual label: Attack'} />
      <CardBody className="space-y-3 text-sm" ><p className="text-2xl font-semibold text-ink">{(100 * receipt.prediction).toFixed(2)}% attack probability</p>
        <p>Transmission confirmed · worker PID {receipt.worker_pid} sent {receipt.feature_count} features to the central prediction service.</p>
        <p className="break-all">Scored by model {receipt.version}. This replay performed inference only. Training updates are reported in Overview and Experiment History.</p>
      </CardBody></Card>}
    <EventHistory clientId={clientId} /><SecurityAudit/>
    <Card><CardHeader title="SDN lab detections" description={labEvents.error ?? labEvents.data?.reason}/>
      <CardBody>{labEvents.data?.items.length ? labEvents.data.items.map((event,i)=><p key={i} className="break-all py-1">
        {new Date(event.ts*1000).toLocaleString()} · {event.host} · {event.kind} · {event.result.label?'Attack':'Benign'} · {(event.result.prediction*100).toFixed(2)}% attack probability · model {event.result.version}
      </p>):<p>No recorded predictions for the current lab.</p>}</CardBody></Card>
  </div>
}
