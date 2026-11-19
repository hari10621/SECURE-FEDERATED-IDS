import type { ReactNode } from 'react'
import { cn } from '../../lib/format'

export function Card({
  children,
  className,
  as: Tag = 'section',
}: {
  children: ReactNode
  className?: string
  as?: 'section' | 'div' | 'article'
}) {
  return (
    <Tag
      className={cn(
        'rounded-xl border border-line bg-navy-900/70 shadow-[0_18px_50px_-30px_rgba(0,0,0,0.9)]',
        className,
      )}
    >
      {children}
    </Tag>
  )
}

export function CardHeader({
  title,
  description,
  actions,
  className,
}: {
  title: ReactNode
  description?: ReactNode
  actions?: ReactNode
  className?: string
}) {
  return (
    <div
      className={cn(
        'flex flex-wrap items-start justify-between gap-3 border-b border-line/80 px-5 py-4',
        className,
      )}
    >
      <div className="min-w-0">
        <h3 className="text-sm font-semibold tracking-wide text-ink">{title}</h3>
        {description ? <p className="mt-1 text-xs leading-5 text-muted">{description}</p> : null}
      </div>
      {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
    </div>
  )
}

export function CardBody({
  children,
  className,
}: {
  children: ReactNode
  className?: string
}) {
  return <div className={cn('px-5 py-4', className)}>{children}</div>
}
