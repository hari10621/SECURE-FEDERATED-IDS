import { NotificationBell } from '../AutomaticRetraining'
import { Menu } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { api } from '../../lib/api'
import { cn } from '../../lib/format'
import { NAV_ITEMS } from '../../lib/nav'
import type { HealthResponse } from '../../lib/types'

type ConnectionState = 'checking' | 'online' | 'offline'

function currentTitle(pathname: string): string {
  const match = NAV_ITEMS.find((item) =>
    item.end ? pathname === item.to : pathname === item.to || pathname.startsWith(`${item.to}/`),
  )
  return match?.label ?? 'SecureFed-IDS'
}

function StatusPill({
  tone,
  label,
  detail,
}: {
  tone: 'success' | 'danger' | 'warning' | 'neutral'
  label: string
  detail: string
}) {
  const tones = {
    success: 'border-emerald-500/25 bg-emerald-500/10 text-emerald-300',
    danger: 'border-red-500/25 bg-red-500/10 text-red-300',
    warning: 'border-amber-500/25 bg-amber-500/10 text-amber-300',
    neutral: 'border-line bg-navy-800 text-muted',
  }
  const dots = {
    success: 'bg-emerald-400',
    danger: 'bg-red-400',
    warning: 'bg-amber-400',
    neutral: 'bg-faint',
  }
  return (
    <span
      title={detail}
      className={cn(
        'inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-medium',
        tones[tone],
      )}
    >
      <span className={cn('size-1.5 rounded-full', dots[tone])} aria-hidden="true" />
      {label}
    </span>
  )
}

export function Topbar({ onMenu }: { onMenu: () => void }) {
  const location = useLocation()
  const [connection, setConnection] = useState<ConnectionState>('checking')
  const [health, setHealth] = useState<HealthResponse | null>(null)

  useEffect(() => {
    let active = true
    const check = () => {
      api.health().then(
        (result) => {
          if (!active) return
          setHealth(result)
          setConnection('online')
        },
        () => {
          if (!active) return
          setHealth(null)
          setConnection('offline')
        },
      )
    }
    check()
    const timer = window.setInterval(check, 30_000)
    return () => {
      active = false
      window.clearInterval(timer)
    }
  }, [])

  return (
    <header className="sticky top-0 z-30 border-b border-line bg-navy-950/85 backdrop-blur">
      <div className="flex h-16 items-center gap-3 px-4 sm:px-6 lg:px-8">
        <button
          type="button"
          onClick={onMenu}
          className="flex size-9 items-center justify-center rounded-lg border border-line text-muted hover:bg-navy-800 hover:text-ink lg:hidden"
          aria-label="Open navigation"
          aria-controls="mobile-navigation"
        >
          <Menu className="size-4" aria-hidden="true" />
        </button>

        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-semibold text-ink lg:hidden">{currentTitle(location.pathname)}</p>
        </div>

        <div className="flex items-center gap-2">
          <NotificationBell />
          {connection === 'checking' ? (
            <StatusPill tone="neutral" label="Checking API" detail="Contacting the local backend." />
          ) : connection === 'online' ? (
            <StatusPill
              tone="success"
              label="API online"
              detail={`Database: ${health?.database ?? 'unknown'} · version ${health?.version ?? 'unknown'}`}
            />
          ) : (
            <StatusPill
              tone="danger"
              label="API offline"
              detail="The backend is unreachable. Start uvicorn and check Settings."
            />
          )}
        </div>
      </div>
    </header>
  )
}
