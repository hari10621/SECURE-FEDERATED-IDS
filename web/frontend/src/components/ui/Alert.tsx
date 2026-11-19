import { AlertTriangle, CheckCircle2, Info, Lock } from 'lucide-react'
import type { ReactNode } from 'react'
import { cn, type Tone } from '../../lib/format'

const TONES: Record<Exclude<Tone, 'neutral'>, string> = {
  success: 'border-emerald-500/30 bg-emerald-500/5 text-emerald-100',
  warning: 'border-amber-500/30 bg-amber-500/5 text-amber-100',
  danger: 'border-red-500/30 bg-red-500/5 text-red-100',
  info: 'border-cyan-glow/25 bg-cyan-glow/5 text-cyan-50',
}

const ICONS = {
  success: CheckCircle2,
  warning: AlertTriangle,
  danger: AlertTriangle,
  info: Info,
} as const

export function Alert({
  tone = 'info',
  title,
  children,
  className,
}: {
  tone?: Exclude<Tone, 'neutral'>
  title?: ReactNode
  children: ReactNode
  className?: string
}) {
  const Icon = tone === 'warning' ? Lock : ICONS[tone]
  return (
    <div className={cn('rounded-lg border px-4 py-3 text-sm', TONES[tone], className)}>
      <div className="flex items-start gap-2.5">
        <Icon className="mt-0.5 size-4 shrink-0 opacity-80" aria-hidden="true" />
        <div className="min-w-0 leading-6">
          {title ? <p className="font-semibold">{title}</p> : null}
          <div className={cn(title ? 'mt-0.5 opacity-90' : undefined)}>{children}</div>
        </div>
      </div>
    </div>
  )
}
