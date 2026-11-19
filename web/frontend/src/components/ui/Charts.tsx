import {
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import type { FederatedRound, MetricValue } from '../../lib/types'

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
