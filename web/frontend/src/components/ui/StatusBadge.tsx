import { cn, humanize, statusTone, type Tone } from '../../lib/format'

const TONES: Record<Tone, string> = {
  success: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300',
  warning: 'border-amber-500/30 bg-amber-500/10 text-amber-300',
  danger: 'border-red-500/30 bg-red-500/10 text-red-300',
  info: 'border-cyan-glow/30 bg-cyan-glow/10 text-cyan-300',
  neutral: 'border-line bg-navy-800 text-muted',
}

const DOTS: Record<Tone, string> = {
  success: 'bg-emerald-400',
  warning: 'bg-amber-400',
  danger: 'bg-red-400',
  info: 'bg-cyan-glow',
  neutral: 'bg-faint',
}

export function StatusBadge({
  status,
  label,
  tone,
  className,
}: {
  status?: string
  label?: string
  tone?: Tone
  className?: string
}) {
  const resolvedTone = tone ?? statusTone(status ?? '')
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-medium',
        TONES[resolvedTone],
        className,
      )}
    >
      <span className={cn('size-1.5 rounded-full', DOTS[resolvedTone])} aria-hidden="true" />
      {label ?? humanize(status)}
    </span>
  )
}
