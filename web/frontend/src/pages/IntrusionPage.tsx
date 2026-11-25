import { useState } from 'react'
import { PageHeader } from '../components/ui/PageHeader'
import { Alert } from '../components/ui/Alert'
import { Button } from '../components/ui/Button'
import { Card, CardBody, CardHeader } from '../components/ui/Card'
import { Field, Select, TextArea } from '../components/ui/Field'
import { useApi } from '../hooks/useApi'
import { api } from '../lib/api'
import { describeError } from '../lib/format'
import type { LabelledSample } from '../lib/types'

export function IntrusionPage() {
  const status = useApi(api.predictionStatus)
  const versions = useApi(api.versions)
  const datasets = useApi(() => api.listDatasets({limit: 100}))
  const clients = useApi(() => api.listClients({limit: 100}))
  const [dataset, setDataset] = useState('')
  const [client, setClient] = useState('')
  const [label, setLabel] = useState(1)
  const [type, setType] = useState('')
  const [types, setTypes] = useState<string[]>([])
  const [sample, setSample] = useState<LabelledSample | null>(null)
  const [offset, setOffset] = useState(0)
  const [raw, setRaw] = useState('')
  const [version, setVersion] = useState('')
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const info = status.data
  const selected = dataset || info?.dataset_id || datasets.data?.items[0]?.id || ''
  const partition = client ? 'train' : 'test'
  function reset() { setSample(null); setOffset(0); setMessage(''); setError(''); setTypes([]); setType('') }
  async function run(action: () => Promise<void>) {
    setBusy(true); setError(''); setMessage('')
    try { await action() } catch (cause) { setError(describeError(cause)) } finally { setBusy(false) }
  }
  async function predict(values: number[], row?: LabelledSample) {
    if (values.length !== 48 || values.some(v => !Number.isFinite(v))) throw new Error('Enter exactly 48 finite numbers.')
    const result = await api.predict(values)
    if (row && result.version !== row.version) throw new Error('Active model changed. Load the sample again.')
    setMessage(`Predicted ${result.class_name} · confidence ${(100 * result.confidence).toFixed(2)}%` +
      (row ? ` · actual ${info?.labels?.[row.actual]} · ${row.actual === result.label ? 'Correct' : 'Incorrect'}` : ''))
  }
  return <div className="space-y-4">
    <PageHeader title="Intrusion Detection"
      actions={<Button disabled={busy} onClick={() => run(async () => {
        const fresh = await api.reloadModel(); status.reload(); versions.reload(); reset()
        if (!fresh.available) throw new Error(fresh.reason)
        setMessage(`Reloaded and verified ${fresh.version}`)
      })}>Reload Model</Button>} />
    <Card><CardHeader title={info?.available ? 'Inference available' : 'Inference unavailable'} description={status.error || info?.reason}/>
      <CardBody className="space-y-3 text-sm text-muted">
        <dl className="grid gap-3 sm:grid-cols-2">{Object.entries({
          Model: info?.model, Version: info?.version, 'Model SHA-256': info?.sha256, 'Source experiment': info?.source_experiment,
          'Trained at': info?.trained_at, Rounds: info?.rounds, Participants: info?.participants?.join(', '),
          Preprocessing: info?.available ? 'Validated' : 'Unverified', 'Expected features': info?.feature_count,
          Labels: info?.labels && Object.entries(info.labels).map(([k,v]) => k+' = '+v).join(', ')
        }).map(([k,v]) => <div key={k}><dt>{k}</dt><dd className="break-all text-ink">{v ?? 'Unavailable'}</dd></div>)}</dl>
        <details><summary>Training CSV feature order</summary><ol className="list-decimal pl-6">{info?.features?.map(f => <li key={f}>{f}</li>)}</ol></details>
        <Field label="Saved model version" htmlFor="version"><Select id="version" value={version} onChange={e => setVersion(e.target.value)}>
          <option value="">Choose a version</option>{versions.data?.map(v => <option key={v}>{v}</option>)}</Select></Field>
        <Button disabled={!version || busy} onClick={() => run(async () => { await api.deploy(version); status.reload(); reset(); setMessage('Selected version deployed.') })}>Restore selected version</Button>
      </CardBody></Card>
    <Card><CardHeader title="Labeled dataset samples"/>
      <CardBody className="space-y-3">
        <Field label="Dataset" htmlFor="sample-ds"><Select id="sample-ds" value={selected} onChange={e => {setDataset(e.target.value);reset()}}>
          {datasets.data?.items.map(d => <option value={d.id} key={d.id}>{d.name}</option>)}</Select></Field>
        <Field label="Sample use" htmlFor="sample-use"><Select id="sample-use" value={client} onChange={e => {setClient(e.target.value);reset()}}>
          <option value="">Held-out prediction</option>{clients.data?.items.map(c => <option key={c.id} value={c.id}>Train · {c.name}</option>)}</Select></Field>
        <Field label="Actual category" htmlFor="category"><Select id="category" value={label} onChange={e => {setLabel(Number(e.target.value));reset()}}>
          <option value={0}>Benign</option><option value={1}>Attack</option></Select></Field>
        {label === 1 && <Field label="Attack type" htmlFor="attack-type"><Select id="attack-type" value={type} onChange={e => {setType(e.target.value);setSample(null);setOffset(0);setMessage('')}}>
          <option value="">{types.length ? 'Any recorded type' : 'Binary label only / load sample to check'}</option>{types.map(t => <option key={t}>{t}</option>)}</Select></Field>}
        <Button disabled={busy || !selected} onClick={() => run(async () => {
          const next = await api.sample(selected,label,partition,offset,type);setSample(next);setTypes(next.attack_types);setOffset(offset+1)
        })}>Load sample</Button>
        {sample && <div className="space-y-2"><p>CSV row {sample.index+2} · actual {sample.actual ? 'Attack' : 'Benign'} · {sample.partition} partition {sample.attack_type}</p>
          {client ? <Button disabled={busy} onClick={() => run(async () => {
            const c = await api.getClient(client)
            const previous = c.config.assignment_dataset === selected && Array.isArray(c.config.training_rows) ? c.config.training_rows : []
            await api.updateClient(client,{config:{...c.config, assignment_dataset:selected,training_rows:[...new Set([...previous,sample.index])]}})
            setMessage(`Assigned CSV row ${sample.index+2} to ${c.name} for the next clean training run.`)
          })}>Assign sample to client</Button> : <Button disabled={busy} onClick={() => run(() => predict(sample.features,sample))}>Request sample prediction</Button>}</div>}
      </CardBody></Card>
    <Card><CardHeader title="Manual prediction"/><CardBody className="space-y-2">
      <TextArea aria-label="48 raw feature values" value={raw} onChange={e => {setRaw(e.target.value);setMessage('')}}/>
      <Button disabled={busy || !info?.available} onClick={() => run(() => predict(raw.trim().split(/[\s,;]+/).map(Number)))}>Request prediction</Button>
    </CardBody></Card>
    {error && <Alert tone="danger">{error}</Alert>}{message && <Alert tone="info">{message}</Alert>}
  </div>
}
