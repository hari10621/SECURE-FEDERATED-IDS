import { AlertTriangle, Inbox, Loader2, Lock, RefreshCw } from 'lucide-react'
import type { ReactNode } from 'react'
import { cn } from '../../lib/format'
import { Button } from './Button'

export function LoadingState({ label = 'Loading…' }: { label?: string }) {
  return (
    <div className="flex items-center justify-center gap-3 px-6 py-14 text-sm text-muted" role="status">
      <Loader2 className="size-5 animate-spin text-cyan-glow" aria-hidden="true" />
      {label}
    </div>
  )
}

export function InlineLoading({ label = 'Working…' }: { label?: string }) {
  return (
    <span className="inline-flex items-center gap-2 text-xs text-muted" role="status">
      <Loader2 className="size-3.5 animate-spin" aria-hidden="true" />
      {label}
    </span>
  )
}

export function ErrorState({
  message,
  title = 'Could not load this view',
  onRetry,
  hint,
}: {
  message: string
  title?: string
  onRetry?: () => void
  hint?: string
}) {
  return (
    <div className="rounded-xl border border-red-500/30 bg-red-500/5 px-6 py-8" role="alert">
      <div className="flex items-start gap-3">
        <AlertTriangle className="mt-0.5 size-5 shrink-0 text-red-300" aria-hidden="true" />
        <div className="min-w-0">
          <p className="text-sm font-semibold text-red-200">{title}</p>
          <p className="mt-1 text-sm leading-6 text-red-200/80">{message}</p>
          {hint ? <p className="mt-2 text-xs leading-5 text-muted">{hint}</p> : null}
          {onRetry ? (
            <Button
              variant="secondary"
              size="sm"
              className="mt-4"
              onClick={onRetry}
              icon={<RefreshCw className="size-3.5" aria-hidden="true" />}
            >
              Retry
            </Button>
          ) : null}
        </div>
      </div>
    </div>
  )
}

export function EmptyState({
  title,
  description,
  action,
  icon,
}: {
  title: string
  description: string
  action?: ReactNode
  icon?: ReactNode
}) {
  return (
    <div className="flex flex-col items-center justify-center px-6 py-14 text-center">
      <div className="mb-3 flex size-11 items-center justify-center rounded-full border border-line bg-navy-800 text-faint">
        {icon ?? <Inbox className="size-5" aria-hidden="true" />}
      </div>
      <p className="text-sm font-semibold text-ink">{title}</p>
      <p className="mt-1 max-w-md text-sm leading-6 text-muted">{description}</p>
      {action ? <div className="mt-4">{action}</div> : null}
    </div>
  )
}

export function UnavailableState({
  title,
  reason,
  items,
  className,
}: {
  title: string
  reason: string
  items?: string[]
  className?: string
}) {
  return (
    <div
      className={cn(
        'rounded-xl border border-amber-500/25 bg-amber-500/5 px-6 py-7',
        className,
      )}
    >
      <div className="flex items-start gap-3">
        <Lock className="mt-0.5 size-5 shrink-0 text-amber-300" aria-hidden="true" />
        <div className="min-w-0">
          <p className="text-sm font-semibold text-amber-200">{title}</p>
          <p className="mt-1 text-sm leading-6 text-amber-100/75">{reason}</p>
          {items && items.length > 0 ? (
            <ul className="mt-3 space-y-1.5 text-xs leading-5 text-muted">
              {items.map((item) => (
                <li key={item} className="flex gap-2">
                  <span className="mt-2 size-1 shrink-0 rounded-full bg-faint" aria-hidden="true" />
                  <span>{item}</span>
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      </div>
    </div>
  )
}
