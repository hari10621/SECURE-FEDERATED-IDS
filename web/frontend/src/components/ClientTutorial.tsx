import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../lib/api'
import { describeError, isActiveStatus } from '../lib/format'
import { useApi } from '../hooks/useApi'
import { Alert } from './ui/Alert'
import { Button } from './ui/Button'
import { Card, CardBody, CardHeader } from './ui/Card'
import { ProgressBar } from './ui/ProgressBar'

const percent = (value: number) => (100 * value).toFixed(1) + '%'

export function ClientTutorial() {
  const latest = useApi(api.latestTutorial)
  const [starting, setStarting] = useState(false)
  const [error, setError] = useState('')
  const job = latest.data
  const active = !!job && isActiveStatus(job.status)
  const reload = latest.reload
  useEffect(() => {
    if (!active) return
    const timer = window.setInterval(reload, 2000)
    return () => window.clearInterval(timer)
  }, [active, reload])

  async function start() {
    setStarting(true)
    setError('')
    try {
      await api.startTutorial()
    } catch (cause) {
      setError(describeError(cause))
    } finally {
      reload()
      setStarting(false)
    }
  }

  const result = job?.result
  return (
    <Card className="mb-5">
      <CardHeader title="Tutorial · Detect an intrusion and verify a model update"
        description="Replay a labeled synthetic flow for a local sensor and compare two rounds of plaintext GRU training."
        actions={<Button onClick={start} disabled={starting || active || latest.loading}>
          {active ? 'Tutorial running' : result ? 'Run tutorial again' : 'Run tutorial'}
        </Button>} />
      <CardBody className="space-y-4">
        <ol className="grid list-decimal gap-4 pl-5 text-sm text-muted md:grid-cols-3 md:gap-8">
          <li><strong className="text-ink">Create a sensor and peer.</strong> Each client trains on its own shard. Their first updates form the baseline model.</li>
          <li><strong className="text-ink">Replay an attack flow.</strong> Score one held-out flow labeled intrusion using the baseline model. A score above 50% triggers detection.</li>
          <li><strong className="text-ink">Check the next model.</strong> Both clients train again. Score the same flow and compare weight hashes and held-out metrics.</li>
        </ol>
        {active && <ProgressBar value={job.progress} label={job.message || 'Starting tutorial'} />}
        {(error || latest.error || job?.error) && <Alert tone="warning">
          {error || latest.error || job?.error} <button className="underline" onClick={reload}>Refresh status</button>
        </Alert>}
        {result && <>
          <p className="text-sm text-muted">
            <Link className="text-cyan-glow underline" to="/clients">{result.sensor.name}</Link> contributed {result.rounds[0].sensor_samples} training flows per round.
            {' '}The replay used row {result.csv_row} of <code>{result.dataset}</code>. Both models were evaluated on the same {result.test_rows} held-out flows.
          </p>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm text-ink">
              <caption className="sr-only">Tutorial detection and model comparison</caption>
              <thead className="text-xs text-muted"><tr>
                {['Model', 'Attack replay', 'Attack score', 'Accuracy', 'F1', 'Weight hash'].map(title =>
                  <th key={title} className="px-2 py-2">{title}</th>)}
              </tr></thead>
              <tbody>{result.rounds.map(round => <tr key={round.round} className="border-t border-line">
                <td className="px-2 py-2">Round {round.round}</td>
                <td className="px-2">{round.label === 1 ? 'Detected' : 'Missed'}</td>
                <td className="px-2">{(100 * round.score).toFixed(3)}%</td>
                <td className="px-2">{percent(round.accuracy)}</td>
                <td className="px-2">{round.f1.toFixed(3)}</td>
                <td className="px-2 font-mono" title={round.digest}>{round.digest.slice(0, 12)}</td>
              </tr>)}</tbody>
            </table>
          </div>
          <Alert tone={result.weights_changed ? 'success' : 'warning'}>
            {result.weights_changed ? 'Verified: the global weights changed after round 2.' : 'The global weights were identical across both rounds.'}
            {' '}The replay measures detection. The labeled training shards drive the update. This tutorial uses a separate model from the dashboard prediction service.
          </Alert>
        </>}
      </CardBody>
    </Card>
  )
}
