import { FileCheck2, RefreshCw, Upload } from 'lucide-react'
import { useRef, useState, type FormEvent } from 'react'
import { Alert } from '../components/ui/Alert'
import { Button } from '../components/ui/Button'
import { Card, CardBody, CardHeader } from '../components/ui/Card'
import { DataTable, type Column } from '../components/ui/DataTable'
import { Field, Select, TextInput } from '../components/ui/Field'
import { PageHeader } from '../components/ui/PageHeader'
import { EmptyState, ErrorState, LoadingState } from '../components/ui/States'
import { StatusBadge } from '../components/ui/StatusBadge'
import { useApi } from '../hooks/useApi'
import { api } from '../lib/api'
import { describeError, formatBytes, formatDate, formatNumber } from '../lib/format'
import type {
  DatasetResponse,
  DatasetType,
  DatasetValidationReport,
} from '../lib/types'

const DATASET_TYPES: Array<{ value: DatasetType; label: string }> = [
  { value: 'insdn', label: 'InSDN' },
  { value: 'cicids2017', label: 'CICIDS2017' },
  { value: 'cicids2019', label: 'CICIDS2019' },
]

export function DatasetsPage() {
  const datasets = useApi(() => api.listDatasets({ limit: 100 }), [])
  const [file, setFile] = useState<File | null>(null)
  const [fileKey, setFileKey] = useState(0)
  const [datasetType, setDatasetType] = useState<DatasetType>('insdn')
  const [name, setName] = useState('')
  const [labelColumn, setLabelColumn] = useState('')
  const [report, setReport] = useState<DatasetValidationReport | null>(null)
  const [formError, setFormError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [revalidating, setRevalidating] = useState<string | null>(null)
  const fileInput = useRef<HTMLInputElement>(null)

  async function handleValidate() {
    setFormError(null)
    setNotice(null)
    if (!file) {
      setFormError('Choose a CSV file before validating.')
      return
    }
    setBusy('validate')
    try {
      const result = await api.validateDataset(file, labelColumn.trim() || undefined)
      setReport(result)
    } catch (error) {
      setReport(null)
      setFormError(describeError(error))
    } finally {
      setBusy(null)
    }
  }

  async function handleUpload(event: FormEvent) {
    event.preventDefault()
    setFormError(null)
    setNotice(null)
    if (!file) {
      setFormError('Choose a CSV file before uploading.')
      return
    }
    setBusy('upload')
    try {
      const result = await api.uploadDataset({
        file,
        datasetType,
        name: name.trim() || undefined,
        labelColumn: labelColumn.trim() || undefined,
      })
      setNotice(
        `Uploaded "${result.name}" with ${formatNumber(result.rows)} rows. Validation status: ${result.validation_status}.`,
      )
      setFile(null)
      setReport(null)
      setName('')
      setFileKey((value) => value + 1)
      if (fileInput.current) fileInput.current.value = ''
      datasets.reload()
    } catch (error) {
      setFormError(describeError(error))
    } finally {
      setBusy(null)
    }
  }

  async function handleRevalidate(id: string) {
    setRevalidating(id)
    setNotice(null)
    try {
      const result = await api.revalidateDataset(id)
      setReport(result)
      setNotice(`Revalidation complete for dataset ${id}.`)
      datasets.reload()
    } catch (error) {
      setFormError(describeError(error))
    } finally {
      setRevalidating(null)
    }
  }

  async function handleDeleteDataset(id: string) {
    setBusy(id)
    setNotice(null)
    if (
      !window.confirm(
        `Are you sure you want to delete dataset "${id}"?\nThis will remove the dataset record and the associated physical CSV file from storage.`
      )
    ) {
      setBusy(null)
      return
    }
    try {
      await api.deleteDataset(id)
      setNotice(`Dataset ${id} has been deleted.`)
      datasets.reload()
    } catch (error) {
      setFormError(describeError(error))
    } finally {
      setBusy(null)
    }
  }

  const columns: Column<DatasetResponse>[] = [
    {
      key: 'name',
      header: 'Dataset',
      render: (row) => (
        <div className="min-w-0">
          <p className="truncate font-medium text-ink">{row.name}</p>
          <p className="mt-0.5 font-mono text-[11px] text-faint">{row.original_filename}</p>
        </div>
      ),
    },
    {
      key: 'type',
      header: 'Type',
      render: (row) => <StatusBadge tone="neutral" label={row.dataset_type.toUpperCase()} />,
    },
    {
      key: 'shape',
      header: 'Shape',
      render: (row) => (
        <div className="text-xs">
          <p className="font-mono text-ink">{formatNumber(row.rows)} rows</p>
          <p className="mt-0.5 text-faint">
            {row.feature_count} features · {formatBytes(row.size_bytes)}
          </p>
        </div>
      ),
    },
    {
      key: 'validation',
      header: 'Validation',
      render: (row) => (
        <div>
          <StatusBadge status={row.validation_status} />
          {row.validation_errors.length > 0 ? (
            <p className="mt-1 max-w-[220px] truncate text-[11px] text-red-300" title={row.validation_errors[0]}>
              {row.validation_errors[0]}
            </p>
          ) : null}
        </div>
      ),
    },
    {
      key: 'research',
      header: 'Research schema',
      render: (row) => (
        <StatusBadge
          tone={row.research_compatible ? 'success' : 'warning'}
          label={row.research_compatible ? '48 features' : 'Incompatible'}
        />
      ),
    },
    {
      key: 'created',
      header: 'Uploaded',
      render: (row) => <span className="text-xs text-muted">{formatDate(row.created_at)}</span>,
    },
    {
      key: 'actions',
      header: '',
      headerClassName: 'text-right',
      className: 'text-right',
      render: (row) => (
        <div className="flex gap-1">
          <Button
            variant="secondary"
            size="sm"
            loading={revalidating === row.id}
            onClick={() => handleRevalidate(row.id)}
          >
            Revalidate
          </Button>
          <Button
            variant="danger"
            size="sm"
            onClick={() => handleDeleteDataset(row.id)}
          >
            Delete
          </Button>
        </div>
      ),
    },
  ]

  return (
    <div>
      <PageHeader
        title="Datasets"
        actions={
          <Button
            variant="secondary"
            size="sm"
            onClick={datasets.reload}
            icon={<RefreshCw className="size-3.5" aria-hidden="true" />}
          >
            Refresh
          </Button>
        }
      />

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)]">
        <Card>
          <CardHeader
            title="Upload a dataset"
          />
          <CardBody>
            <form className="space-y-4" onSubmit={handleUpload}>
              <Field
                label="CSV file"
                htmlFor="dataset-file"
                required
                hint="InSDN, CICIDS2017, or CICIDS2019 CSV exported locally."
              >
                <input
                  key={fileKey}
                  ref={fileInput}
                  id="dataset-file"
                  type="file"
                  accept=".csv,text/csv"
                  className="block w-full cursor-pointer rounded-lg border border-line bg-navy-950/70 px-3 py-2 text-sm text-muted file:mr-3 file:rounded-md file:border-0 file:bg-navy-700 file:px-3 file:py-1.5 file:text-xs file:font-medium file:text-ink hover:border-navy-700"
                  onChange={(event) => {
                    setFile(event.target.files?.[0] ?? null)
                    setReport(null)
                    setFormError(null)
                    setNotice(null)
                  }}
                />
              </Field>

              <div className="grid gap-4 sm:grid-cols-2">
                <Field label="Dataset type" htmlFor="dataset-type" required>
                  <Select
                    id="dataset-type"
                    value={datasetType}
                    onChange={(event) => setDatasetType(event.target.value as DatasetType)}
                  >
                    {DATASET_TYPES.map((type) => (
                      <option key={type.value} value={type.value}>
                        {type.label}
                      </option>
                    ))}
                  </Select>
                </Field>
                <Field
                  label="Display name"
                  htmlFor="dataset-name"
                  hint="Optional. Defaults to the filename."
                >
                  <TextInput
                    id="dataset-name"
                    value={name}
                    onChange={(event) => setName(event.target.value)}
                    placeholder="e.g. InSDN cleaned sample"
                    maxLength={120}
                  />
                </Field>
              </div>

              <Field
                label="Label column"
                htmlFor="dataset-label"
                hint="Optional. Leave blank to use the backend default."
              >
                <TextInput
                  id="dataset-label"
                  value={labelColumn}
                  onChange={(event) => setLabelColumn(event.target.value)}
                  placeholder="e.g. Label"
                />
              </Field>

              {formError ? <Alert tone="danger" title="Dataset action failed">{formError}</Alert> : null}
              {notice ? <Alert tone="success">{notice}</Alert> : null}

              <div className="flex flex-wrap gap-2">
                <Button
                  variant="secondary"
                  loading={busy === 'validate'}
                  disabled={busy !== null}
                  onClick={handleValidate}
                  icon={<FileCheck2 className="size-4" aria-hidden="true" />}
                >
                  Validate
                </Button>
                <Button
                  type="submit"
                  loading={busy === 'upload'}
                  disabled={busy !== null}
                  icon={<Upload className="size-4" aria-hidden="true" />}
                >
                  Upload
                </Button>
              </div>
            </form>

            {report ? <ValidationReport report={report} /> : null}
          </CardBody>
        </Card>

        <Card>
          <CardHeader
            title="Stored datasets"
            description={
              datasets.data
                ? `${formatNumber(datasets.data.total)} record${datasets.data.total === 1 ? '' : 's'} in local storage.`
                : 'Loading local dataset records.'
            }
          />
          {datasets.loading && !datasets.data ? (
            <LoadingState label="Loading datasets…" />
          ) : datasets.error ? (
            <CardBody>
              <ErrorState message={datasets.error} onRetry={datasets.reload} />
            </CardBody>
          ) : (datasets.data?.items.length ?? 0) === 0 ? (
            <EmptyState
              title="No datasets stored"
              description="Validate and upload a local CSV to create the first dataset record."
            />
          ) : (
            <DataTable
              columns={columns}
              rows={datasets.data?.items ?? []}
              rowKey={(row) => row.id}
              caption="Stored datasets"
            />
          )}
        </Card>
      </div>
    </div>
  )
}

function ValidationReport({ report }: { report: DatasetValidationReport }) {
  return (
    <div className="mt-5 rounded-lg border border-line bg-navy-950/50 p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <p className="text-sm font-semibold text-ink">Validation report</p>
          <StatusBadge
            tone={report.valid ? 'success' : 'danger'}
            label={report.valid ? 'Valid' : 'Invalid'}
          />
        </div>
        <StatusBadge
          tone={report.research_compatible ? 'success' : 'warning'}
          label={report.research_compatible ? 'Research compatible' : 'Not research compatible'}
        />
      </div>
      <dl className="mt-3 grid grid-cols-2 gap-3 text-xs sm:grid-cols-4">
        <div>
          <dt className="text-faint">Rows</dt>
          <dd className="mt-0.5 font-mono text-ink">{formatNumber(report.rows)}</dd>
        </div>
        <div>
          <dt className="text-faint">Columns</dt>
          <dd className="mt-0.5 font-mono text-ink">{formatNumber(report.columns)}</dd>
        </div>
        <div>
          <dt className="text-faint">Features</dt>
          <dd className="mt-0.5 font-mono text-ink">{formatNumber(report.feature_count)}</dd>
        </div>
        <div>
          <dt className="text-faint">Label column</dt>
          <dd className="mt-0.5 font-mono text-ink">
            {report.label_column} · index {report.label_column_index}
          </dd>
        </div>
      </dl>
      {Object.keys(report.label_counts).length > 0 ? (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {Object.entries(report.label_counts)
            .slice(0, 8)
            .map(([label, count]) => (
              <span
                key={label}
                className="rounded-full border border-line bg-navy-800 px-2 py-0.5 font-mono text-[11px] text-muted"
              >
                {label}: {formatNumber(count)}
              </span>
            ))}
        </div>
      ) : null}
      {report.warnings.length > 0 ? (
        <div className="mt-3">
          <p className="text-[11px] font-semibold uppercase tracking-wider text-amber-300">
            Warnings
          </p>
          <ul className="mt-1 space-y-1 text-xs leading-5 text-amber-100/80">
            {report.warnings.map((warning) => (
              <li key={warning}>{warning}</li>
            ))}
          </ul>
        </div>
      ) : null}
      {report.errors.length > 0 ? (
        <div className="mt-3">
          <p className="text-[11px] font-semibold uppercase tracking-wider text-red-300">Errors</p>
          <ul className="mt-1 space-y-1 text-xs leading-5 text-red-200/90">
            {report.errors.map((error) => (
              <li key={error}>{error}</li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  )
}
