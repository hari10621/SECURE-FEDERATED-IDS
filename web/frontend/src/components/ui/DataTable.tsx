import type { ReactNode } from 'react'
import { cn } from '../../lib/format'

export interface Column<T> {
  key: string
  header: string
  render: (row: T) => ReactNode
  className?: string
  headerClassName?: string
}

export function DataTable<T>({
  columns,
  rows,
  rowKey,
  caption,
  empty,
  className,
}: {
  columns: Column<T>[]
  rows: T[]
  rowKey: (row: T) => string
  caption: string
  empty?: ReactNode
  className?: string
}) {
  return (
    <div className={cn('overflow-x-auto', className)}>
      <table className="w-full min-w-[720px] border-collapse text-sm">
        <caption className="sr-only">{caption}</caption>
        <thead>
          <tr className="border-b border-line text-left">
            {columns.map((column) => (
              <th
                key={column.key}
                scope="col"
                className={cn(
                  'px-5 py-3 text-[11px] font-semibold uppercase tracking-wider text-faint',
                  column.headerClassName,
                )}
              >
                {column.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-line/70">
          {rows.length === 0 ? (
            <tr>
              <td colSpan={columns.length} className="px-5 py-4">
                {empty ?? <p className="py-8 text-center text-sm text-muted">No records.</p>}
              </td>
            </tr>
          ) : (
            rows.map((row) => (
              <tr key={rowKey(row)} className="align-top transition-colors hover:bg-navy-800/40">
                {columns.map((column) => (
                  <td
                    key={column.key}
                    className={cn('px-5 py-3 text-sm text-ink/90', column.className)}
                  >
                    {column.render(row)}
                  </td>
                ))}
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  )
}
