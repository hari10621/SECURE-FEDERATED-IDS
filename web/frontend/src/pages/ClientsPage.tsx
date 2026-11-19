import { Plus, RefreshCw } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { Alert } from '../components/ui/Alert'
import { Button } from '../components/ui/Button'
import { Card, CardBody, CardHeader } from '../components/ui/Card'
import { DataTable, type Column } from '../components/ui/DataTable'
import { Field, TextInput } from '../components/ui/Field'
import { PageHeader } from '../components/ui/PageHeader'
import { EmptyState, ErrorState, LoadingState } from '../components/ui/States'
import { StatusBadge } from '../components/ui/StatusBadge'
import { useApi } from '../hooks/useApi'
import { api } from '../lib/api'
import { describeError, formatDate } from '../lib/format'
import type { ClientResponse, ClientStatus } from '../lib/types'

export function ClientsPage() {
  const clients = useApi(() => api.listClients({ limit: 100 }), [])
  const [name, setName] = useState('')
  const [creating, setCreating] = useState(false)
  const [busyId, setBusyId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  async function handleCreate(event: FormEvent) {
    event.preventDefault()
    setError(null)
    setNotice(null)
    if (!name.trim()) {
      setError('Client name is required.')
      return
    }
    setCreating(true)
    try {
      const client = await api.createClient({ name: name.trim(), config: {} })
      setName('')
      setNotice(`Created configuration record "${client.name}" (${client.id}).`)
      clients.reload()
    } catch (cause) {
      setError(describeError(cause))
    } finally {
      setCreating(false)
    }
  }

  async function handleStatus(client: ClientResponse, status: ClientStatus) {
    setBusyId(client.id)
    setError(null)
    setNotice(null)
    try {
      const updated = await api.updateClient(client.id, { status })
      setNotice(`Client "${updated.name}" is now ${updated.status}. This changes configuration only.`)
      clients.reload()
    } catch (cause) {
      setError(describeError(cause))
    } finally {
      setBusyId(null)
    }
  }

  const columns: Column<ClientResponse>[] = [
    {
      key: 'name',
      header: 'Client',
      render: (row) => (
        <div className="min-w-0">
          <p className="truncate font-medium text-ink">{row.name}</p>
          <p className="mt-0.5 font-mono text-[11px] text-faint">{row.id}</p>
        </div>
      ),
    },
    {
      key: 'status',
      header: 'Status',
      render: (row) => <StatusBadge status={row.status} />,
    },
    {
      key: 'runtime',
      header: 'Runtime',
      render: () => <StatusBadge tone="warning" label="Not connected" />,
    },
    {
      key: 'config',
      header: 'Config',
      render: (row) => (
        <code className="block max-w-[240px] truncate rounded bg-navy-950/70 px-2 py-1 font-mono text-[11px] text-muted">
          {Object.keys(row.config).length === 0 ? '{}' : JSON.stringify(row.config)}
        </code>
      ),
    },
    {
      key: 'updated',
      header: 'Updated',
      render: (row) => <span className="text-xs text-muted">{formatDate(row.updated_at)}</span>,
    },
    {
      key: 'actions',
      header: 'Actions',
      headerClassName: 'text-right',
      className: 'text-right',
      render: (row) => (
        <div className="flex justify-end gap-2">
          <Button
            variant="secondary"
            size="sm"
            loading={busyId === row.id}
            disabled={row.status === 'enabled'}
            onClick={() => handleStatus(row, 'enabled')}
          >
            Enable
          </Button>
          <Button
            variant="ghost"
            size="sm"
            loading={busyId === row.id}
            disabled={row.status === 'disabled'}
            onClick={() => handleStatus(row, 'disabled')}
          >
            Disable
          </Button>
        </div>
      ),
    },
  ]

  return (
    <div>
      <PageHeader
        eyebrow="Operations"
        title="Federated Clients"
        description="Client records are persisted configuration only. The backend does not start independent client processes or authenticate client sessions."
        actions={
          <Button
            variant="secondary"
            size="sm"
            onClick={clients.reload}
            icon={<RefreshCw className="size-3.5" aria-hidden="true" />}
          >
            Refresh
          </Button>
        }
      />

      <Alert tone="warning" title="Configuration, not a running client" className="mb-4">
        Enabling a client updates the stored status field. It does not establish a network
        connection, start a worker, or create a trusted remote node.
      </Alert>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.6fr)]">
        <Card>
          <CardHeader
            title="Create a client record"
            description="Use a stable local name. The backend assigns the immutable client ID."
          />
          <CardBody>
            <form className="space-y-4" onSubmit={handleCreate}>
              <Field label="Client name" htmlFor="client-name" required>
                <TextInput
                  id="client-name"
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                  placeholder="e.g. lab-node-01"
                  maxLength={120}
                />
              </Field>
              {error ? <Alert tone="danger" title="Client action failed">{error}</Alert> : null}
              {notice ? <Alert tone="success">{notice}</Alert> : null}
              <Button
                type="submit"
                loading={creating}
                icon={<Plus className="size-4" aria-hidden="true" />}
              >
                Create client
              </Button>
            </form>
          </CardBody>
        </Card>

        <Card>
          <CardHeader
            title="Client records"
            description={
              clients.data
                ? `${clients.data.total} local configuration record${clients.data.total === 1 ? '' : 's'}.`
                : 'Loading client records.'
            }
          />
          {clients.loading && !clients.data ? (
            <LoadingState label="Loading clients…" />
          ) : clients.error ? (
            <CardBody>
              <ErrorState message={clients.error} onRetry={clients.reload} />
            </CardBody>
          ) : (clients.data?.items.length ?? 0) === 0 ? (
            <EmptyState
              title="No client records"
              description="Create a configuration record to pre-register a future federated client."
            />
          ) : (
            <DataTable
              columns={columns}
              rows={clients.data?.items ?? []}
              rowKey={(row) => row.id}
              caption="Client configuration records"
            />
          )}
        </Card>
      </div>
    </div>
  )
}
