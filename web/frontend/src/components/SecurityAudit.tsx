import { useEffect, useState } from 'react'
import { apiRequest } from '../lib/api'
import { useApi } from '../hooks/useApi'
import { Card, CardBody, CardHeader } from './ui/Card'
import { Button } from './ui/Button'
import { TextInput } from './ui/Field'
type Entry = {
  id: string
  ts: number
  category: string
  severity: string
  client: string | null
  organization: string | null
  version: string | null
  job: string | null
  event: string | null
}
const path = '/api/v1/automation/audit?'
export function SecurityAudit() {
  const [filter, setFilter] = useState<Record<string, string>>({}),
    [offset, page] = useState(0),
    [message, status] = useState(''),
    [busy, setBusy] = useState(false)
  const q = new URLSearchParams(
    Object.entries(filter)
      .filter(([, v]) => v)
      .map(([k, v]) => [
        k,
        k === 'since' || k === 'until'
          ? String(new Date(v).getTime() / 1000)
          : v,
      ]),
  ).toString()
  const data = useApi(
    () => apiRequest<Entry[]>(path + q + '&offset=' + offset),
    [q, offset],
  )
  useEffect(() => {
    const t = setInterval(data.reload, 5000)
    return () => clearInterval(t)
  }, [data.reload])
  async function download(format: string) {
    setBusy(true)
    try {
      const rows: Entry[] = []
      const snapshot = new URLSearchParams(q)
      snapshot.set(
        'until',
        String(
          Math.min(
            Number(snapshot.get('until') || Infinity),
            Date.now() / 1000,
          ),
        ),
      )
      for (let start = 0; ; start += 200) {
        const batch = await apiRequest<Entry[]>(
          path + snapshot.toString() + '&offset=' + start,
        )
        rows.push(...batch)
        if (batch.length < 200) break
      }
      const keys: (keyof Entry)[] = [
        'ts',
        'category',
        'severity',
        'client',
        'organization',
        'version',
        'job',
        'event',
        'id',
      ]
      const escape = (v: unknown) => {
        const s = String(v ?? '')
        return (
          '"' +
          (/^[=+@\-\t\r]/.test(s) ? "'" : '') +
          s.replaceAll('"', '""') +
          '"'
        )
      }
      const content =
        format === 'json'
          ? JSON.stringify(rows, null, 2)
          : [
              keys.join(','),
              ...rows.map((r) => keys.map((k) => escape(r[k])).join(',')),
            ].join('\r\n')
      const url = URL.createObjectURL(
        new Blob([content], {
          type: format === 'json' ? 'application/json' : 'text/csv',
        }),
      )
      const a = document.createElement('a')
      a.href = url
      a.download = 'securefed-security.' + format
      a.click()
      setTimeout(() => URL.revokeObjectURL(url), 1000)
      status('Exported ' + rows.length + ' records')
    } catch (e) {
      status(String(e))
    } finally {
      setBusy(false)
    }
  }
  return (
    <Card>
      <CardHeader title="Security lifecycle log" />
      <CardBody className="space-y-3">
        <div className="grid gap-2 sm:grid-cols-3">
          {Object.entries({
            category: 'Category',
            severity: 'Severity',
            organization: 'Organization',
            client: 'Client ID',
            version: 'Model version',
            since: 'From',
            until: 'Through',
          }).map(([k, title]) => (
            <label key={k}>
              {title}
              <TextInput
                type={
                  k === 'since' || k === 'until' ? 'datetime-local' : 'text'
                }
                value={filter[k] ?? ''}
                onChange={(e) => {
                  page(0)
                  setFilter({ ...filter, [k]: e.target.value })
                }}
              />
            </label>
          ))}
        </div>
        <div className="flex flex-wrap gap-2">
          {['csv', 'json'].map((f) => (
            <Button key={f} disabled={busy} onClick={() => download(f)}>
              Export {f.toUpperCase()}
            </Button>
          ))}
        </div>
        {(data.data ?? []).map((r) => (
          <details key={r.id} className="border-t border-line p-2">
            <summary>
              {new Date(r.ts * 1000).toLocaleString()} · {r.category} ·{' '}
              {r.organization ?? 'Coordinator'}
            </summary>
            <p className="break-all">
              {r.severity} · {r.client} · {r.version} · {r.job} · {r.event}
            </p>
          </details>
        ))}
        <Button disabled={!offset} onClick={() => page(offset - 200)}>
          Previous records
        </Button>
        <Button
          disabled={data.data?.length !== 200}
          onClick={() => page(offset + 200)}
        >
          Next records
        </Button>
        <p role="status">{data.error || message}</p>
      </CardBody>
    </Card>
  )
}
