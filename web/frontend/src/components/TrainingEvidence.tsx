import { useApi } from '../hooks/useApi'
import { api } from '../lib/api'
import type { FederatedResult, ExperimentResponse } from '../lib/types'

function metric(value: unknown) { return typeof value === 'number' ? value.toFixed(4) : 'Unavailable' }

export function TrainingEvidence({experiment}: {experiment: ExperimentResponse}) {
  const status = useApi(api.predictionStatus, [experiment.id])
  const run = experiment.result as FederatedResult | null
  if (!run) return null
  const baseline = run.baseline_metrics as Record<string, number> | undefined
  const version = run.artifact?.version
  return <section className="my-4 space-y-3 rounded-xl border border-line bg-navy-900 p-4 text-sm text-muted">
    <h3 className="font-semibold text-ink">Global model and client updates</h3>
    <p className="break-all">{run.encrypted ? 'Encrypted' : 'Plaintext'} · {version && status.data?.version === version ? 'Deployed' : 'Inactive'} · {String(run.artifact?.weights_file ?? 'No stored GRU artifact')}</p>
    {baseline && <p>Same held-out split · accuracy {metric(baseline.accuracy)} before, {metric(run.final_metrics?.accuracy)} after · F1 {metric(baseline.f1)} before, {metric(run.final_metrics?.f1)} after</p>}
    {Array.isArray(run.rounds) && run.rounds.map(round => <details key={round.round} className="border-t border-line py-2">
      <summary>Round {round.round+1} · accuracy {metric(round.metrics?.accuracy)} · precision {metric(round.metrics?.precision)} · recall {metric(round.metrics?.recall)} · F1 {metric(round.metrics?.f1_score)} · {metric(round.metrics?.training_time_seconds)} seconds</summary>
      <p className="break-all">Global hash before: {round.global_hash_before ?? 'Unavailable'}<br/>Global hash after: {round.global_hash_after || (!run.encrypted && round.aggregate_digest) || 'Unavailable'}</p>
      {round.updates.map((u,i) => <p key={i} className="break-all py-1">Client {String(u.client_id)} · {String(u.sample_count)} samples · loss {metric(u.local_loss)} · update hash {String(u.digest ?? u.ciphertext_digest ?? 'Unavailable')}</p>)}
    </details>)}
  </section>
}
