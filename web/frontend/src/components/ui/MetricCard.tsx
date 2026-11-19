import type { ReactNode } from 'react'
import { cn } from '../../lib/format'

export function MetricCard({
  label,
  value,
  hint,
  icon,
  tone = 'default',
}: {
  label: string
  value: ReactNode
  hint?: ReactNode
  icon?: ReactNode
  tone?: 'default' | 'warning' | 'success'
}) {
  return (
    <div className="rounded-xl border border-line bg-navy-900/70 px-4 py-4">
      <div className="flex items-start justify-between gap-3">
        <p className="text-[11px] font-medium uppercase tracking-wider text-faint">{label}</p>
        {icon ? (
          <span
            className={cn(
              'flex size-8 items-center justify-center rounded-lg border',
              tone === 'warning'
                ? 'border-amber-500/25 bg-amber-500/10 text-amber-300'
                : tone === 'success'
                  ? 'border-emerald-500/25 bg-emerald-500/10 text-emerald-300'
                  : 'border-line bg-navy-800 text-cyan-glow',
            )}
            aria-hidden="true"
          >
            {icon}
          </span>
        ) : null}
      </div>
      <p className="mt-2 truncate text-xl font-semibold tracking-tight text-ink">{value}</p>
      {hint ? <p className="mt-1 text-xs leading-5 text-muted">{hint}</p> : null}
    </div>
  )
}
