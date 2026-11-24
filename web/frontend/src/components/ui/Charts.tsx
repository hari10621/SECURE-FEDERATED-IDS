import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import type { FederatedRound, MetricValue, RoundMetric } from '../../lib/types'

const AXIS = '#64789a'
const GRID = '#1e3050'
const TOOLTIP_STYLE = {
  backgroundColor: '#0b1528',
  border: '1px solid #1e3050',
  borderRadius: '8px',
  color: '#e7eef9',
  fontSize: '12px',
} as const

const LABELS: Record<string, string> = {
  accuracy: 'Accuracy',
  precision: 'Precision',
  recall: 'Recall',
  f1: 'F1',
}

const CORE_METRICS = ['accuracy', 'precision', 'recall', 'f1']

export function MetricBarChart({ metrics }: { metrics: Record<string, MetricValue> | null }) {
  if (!metrics) return null
  const data = CORE_METRICS.filter((key) => typeof metrics[key] === 'number').map((key) => ({
    name: LABELS[key] ?? key,
    value: metrics[key] as number,
  }))
  if (data.length === 0) return null

  return (
    <div className="h-64 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: -12 }}>
          <CartesianGrid stroke={GRID} strokeDasharray="3 3" vertical={false} />
          <XAxis dataKey="name" stroke={AXIS} tick={{ fontSize: 11 }} tickLine={false} />
          <YAxis
            domain={[0, 1]}
            stroke={AXIS}
            tick={{ fontSize: 11 }}
            tickLine={false}
            tickFormatter={(value) => `${Math.round(Number(value) * 100)}%`}
          />
          <Tooltip
            contentStyle={TOOLTIP_STYLE}
            cursor={{ fill: 'rgba(34, 211, 238, 0.06)' }}
            formatter={(value) => [`${(Number(value) * 100).toFixed(2)}%`, 'Score']}
          />
          <Bar dataKey="value" fill="#22d3ee" radius={[4, 4, 0, 0]} isAnimationActive={false} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

export function RoundLineChart({
  rounds,
  metric = 'accuracy',
}: {
  rounds: FederatedRound[]
  metric?: string
}) {
  const data = rounds
    .filter((round) => round.metrics && typeof round.metrics[metric] === 'number')
    .map((round) => ({
      round: round.round + 1,
      value: round.metrics?.[metric] as number,
    }))
  if (data.length === 0) return null

  return (
    <div className="h-64 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: -12 }}>
          <CartesianGrid stroke={GRID} strokeDasharray="3 3" vertical={false} />
          <XAxis
            dataKey="round"
            stroke={AXIS}
            tick={{ fontSize: 11 }}
            tickLine={false}
            label={{ value: 'Round', position: 'insideBottom', offset: -2, fill: AXIS, fontSize: 11 }}
          />
          <YAxis
            domain={[0, 1]}
            stroke={AXIS}
            tick={{ fontSize: 11 }}
            tickLine={false}
            tickFormatter={(value) => `${Math.round(Number(value) * 100)}%`}
          />
          <Tooltip
            contentStyle={TOOLTIP_STYLE}
            formatter={(value) => [`${(Number(value) * 100).toFixed(2)}%`, LABELS[metric] ?? metric]}
            labelFormatter={(label) => `Round ${label}`}
          />
          <Line
            type="monotone"
            dataKey="value"
            stroke="#22d3ee"
            strokeWidth={2}
            dot={false}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}

const STANDARD_COLOR = '#22d3ee'
const HE_COLOR = '#f59e0b'
const TIME_COLORS = {
  training: '#22d3ee',
  encryption: '#f59e0b',
  aggregation: '#a78bfa',
  decryption: '#34d399',
} as const

type ComparisonMetric = 'accuracy' | 'loss'

interface ComparisonPoint {
  round: number
  standard?: number
  he?: number
}

function comparisonData(
  standard: RoundMetric[],
  he: RoundMetric[],
  metric: ComparisonMetric,
): ComparisonPoint[] {
  const points = new Map<number, ComparisonPoint>()
  const add = (entries: RoundMetric[], field: 'standard' | 'he') => {
    for (const entry of entries) {
      const value = entry[metric]
      if (typeof value !== 'number') continue
      const round = entry.round_index + 1
      const point = points.get(round) ?? { round }
      point[field] = value
      points.set(round, point)
    }
  }
  add(standard, 'standard')
  add(he, 'he')
  return [...points.values()].sort((left, right) => left.round - right.round)
}

export function RoundComparisonChart({
  standard,
  he,
  metric,
  label,
}: {
  standard: RoundMetric[]
  he: RoundMetric[]
  metric: ComparisonMetric
  label: string
}) {
  const data = comparisonData(standard, he, metric)
  if (data.length === 0) return null
  const percent = metric !== 'loss'
  const format = (value: number) => (percent ? `${(value * 100).toFixed(2)}%` : value.toFixed(4))

  return (
    <div className="h-64 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: -12 }}>
          <CartesianGrid stroke={GRID} strokeDasharray="3 3" vertical={false} />
          <XAxis
            dataKey="round"
            stroke={AXIS}
            tick={{ fontSize: 11 }}
            tickLine={false}
            label={{ value: 'Round', position: 'insideBottom', offset: -2, fill: AXIS, fontSize: 11 }}
          />
          <YAxis
            domain={percent ? [0, 1] : ['auto', 'auto']}
            stroke={AXIS}
            tick={{ fontSize: 11 }}
            tickLine={false}
            tickFormatter={(value) => (percent ? `${Math.round(Number(value) * 100)}%` : Number(value).toFixed(2))}
          />
          <Tooltip
            contentStyle={TOOLTIP_STYLE}
            formatter={(value, name) => [format(Number(value)), String(name)]}
            labelFormatter={(value) => `Round ${value}`}
          />
          <Legend wrapperStyle={{ fontSize: 11, color: AXIS }} />
          <Line
            type="monotone"
            dataKey="standard"
            name="Standard FL"
            stroke={STANDARD_COLOR}
            strokeWidth={2}
            dot={false}
            connectNulls
            isAnimationActive={false}
          />
          <Line
            type="monotone"
            dataKey="he"
            name="HE-FL"
            stroke={HE_COLOR}
            strokeWidth={2}
            dot={false}
            connectNulls
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
      <p className="mt-1 text-center text-[11px] text-faint">{label}</p>
    </div>
  )
}

interface TimePoint {
  round: number
  training: number
  encryption: number
  aggregation: number
  decryption: number
}

export function ComputationTimeChart({ rounds }: { rounds: RoundMetric[] }) {
  const data: TimePoint[] = rounds
    .filter(
      (entry) =>
        typeof entry.training_time_seconds === 'number' ||
        typeof entry.encryption_time_seconds === 'number' ||
        typeof entry.aggregation_time_seconds === 'number' ||
        typeof entry.decryption_time_seconds === 'number',
    )
    .map((entry) => ({
      round: entry.round_index + 1,
      training: Number(entry.training_time_seconds ?? 0),
      encryption: Number(entry.encryption_time_seconds ?? 0),
      aggregation: Number(entry.aggregation_time_seconds ?? 0),
      decryption: Number(entry.decryption_time_seconds ?? 0),
    }))
  if (data.length === 0) return null

  return (
    <div className="h-64 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: -12 }}>
          <CartesianGrid stroke={GRID} strokeDasharray="3 3" vertical={false} />
          <XAxis dataKey="round" stroke={AXIS} tick={{ fontSize: 11 }} tickLine={false} />
          <YAxis
            stroke={AXIS}
            tick={{ fontSize: 11 }}
            tickLine={false}
            tickFormatter={(value) => `${Number(value).toFixed(1)}s`}
          />
          <Tooltip
            contentStyle={TOOLTIP_STYLE}
            cursor={{ fill: 'rgba(34, 211, 238, 0.06)' }}
            formatter={(value, name) => [`${Number(value).toFixed(4)} s`, String(name)]}
            labelFormatter={(value) => `Round ${value}`}
          />
          <Legend wrapperStyle={{ fontSize: 11, color: AXIS }} />
          <Bar dataKey="training" name="Training" stackId="time" fill={TIME_COLORS.training} isAnimationActive={false} />
          <Bar dataKey="encryption" name="Encryption" stackId="time" fill={TIME_COLORS.encryption} isAnimationActive={false} />
          <Bar dataKey="aggregation" name="Aggregation" stackId="time" fill={TIME_COLORS.aggregation} isAnimationActive={false} />
          <Bar
            dataKey="decryption"
            name="Decryption"
            stackId="time"
            fill={TIME_COLORS.decryption}
            radius={[4, 4, 0, 0]}
            isAnimationActive={false}
          />
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

interface CommunicationPoint {
  round: number
  plaintext?: number
  encrypted?: number
}

const BYTES_PER_MB = 1024 * 1024

export function CommunicationOverheadChart({
  standard,
  he,
}: {
  standard: RoundMetric[]
  he: RoundMetric[]
}) {
  const points = new Map<number, CommunicationPoint>()
  for (const entry of standard) {
    const bytes = entry.plaintext_update_size_bytes ?? entry.bytes_transmitted_per_client
    if (typeof bytes !== 'number') continue
    const round = entry.round_index + 1
    points.set(round, { ...(points.get(round) ?? { round }), plaintext: bytes / BYTES_PER_MB })
  }
  for (const entry of he) {
    const bytes = entry.encrypted_update_size_bytes ?? entry.bytes_transmitted_per_client
    if (typeof bytes !== 'number') continue
    const round = entry.round_index + 1
    points.set(round, { ...(points.get(round) ?? { round }), encrypted: bytes / BYTES_PER_MB })
  }
  const data = [...points.values()].sort((left, right) => left.round - right.round)
  if (data.length === 0) return null

  return (
    <div className="h-64 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: -12 }}>
          <CartesianGrid stroke={GRID} strokeDasharray="3 3" vertical={false} />
          <XAxis dataKey="round" stroke={AXIS} tick={{ fontSize: 11 }} tickLine={false} />
          <YAxis
            stroke={AXIS}
            tick={{ fontSize: 11 }}
            tickLine={false}
            tickFormatter={(value) => `${Number(value).toFixed(2)} MB`}
          />
          <Tooltip
            contentStyle={TOOLTIP_STYLE}
            cursor={{ fill: 'rgba(34, 211, 238, 0.06)' }}
            formatter={(value, name) => [`${Number(value).toFixed(4)} MB`, String(name)]}
            labelFormatter={(value) => `Round ${value}`}
          />
          <Legend wrapperStyle={{ fontSize: 11, color: AXIS }} />
          <Bar dataKey="plaintext" name="Plaintext" fill={STANDARD_COLOR} isAnimationActive={false} />
          <Bar
            dataKey="encrypted"
            name="Encrypted (CKKS)"
            fill={HE_COLOR}
            radius={[4, 4, 0, 0]}
            isAnimationActive={false}
          />
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}
