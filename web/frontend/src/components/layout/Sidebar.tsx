import { Lock, ShieldCheck, X } from 'lucide-react'
import { NavLink } from 'react-router-dom'
import { cn } from '../../lib/format'
import { NAV_SECTIONS } from '../../lib/nav'

function SidebarContent({ onNavigate }: { onNavigate?: () => void }) {
  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-3 border-b border-line/80 px-5 py-5">
        <span className="flex size-10 items-center justify-center rounded-xl border border-cyan-glow/25 bg-gradient-to-br from-cyan-glow/20 to-blue-glow/10 text-cyan-glow">
          <ShieldCheck className="size-5" aria-hidden="true" />
        </span>
        <div className="min-w-0">
          <p className="truncate text-sm font-semibold tracking-wide text-ink">SecureFed-IDS</p>
          <p className="text-[11px] uppercase tracking-[0.16em] text-faint">Research console</p>
        </div>
      </div>

      <nav aria-label="Primary" className="flex-1 overflow-y-auto px-3 py-4">
        {NAV_SECTIONS.map((section) => (
          <div key={section.title} className="mb-5 last:mb-0">
            <p className="mb-2 px-3 text-[10px] font-semibold uppercase tracking-[0.18em] text-faint">
              {section.title}
            </p>
            <ul className="space-y-1">
              {section.items.map((item) => {
                const Icon = item.icon
                return (
                  <li key={item.to}>
                    <NavLink
                      to={item.to}
                      end={item.end}
                      onClick={onNavigate}
                      title={item.description}
                      className={({ isActive }) =>
                        cn(
                          'group flex items-center gap-3 rounded-lg px-2.5 py-2 text-sm transition-colors',
                          isActive
                            ? 'bg-cyan-glow/10 text-ink ring-1 ring-inset ring-cyan-glow/20'
                            : 'text-muted hover:bg-navy-800/80 hover:text-ink',
                        )
                      }
                    >
                      {({ isActive }) => (
                        <>
                          <span
                            className={cn(
                              'flex size-8 shrink-0 items-center justify-center rounded-md border',
                              isActive
                                ? 'border-cyan-glow/20 bg-navy-950/60 text-cyan-glow'
                                : 'border-transparent text-faint group-hover:text-muted',
                            )}
                          >
                            <Icon className="size-4" aria-hidden="true" />
                          </span>
                          <span className="min-w-0 flex-1 truncate">{item.label}</span>
                          {isActive ? (
                            <span className="size-1.5 rounded-full bg-cyan-glow" aria-hidden="true" />
                          ) : null}
                        </>
                      )}
                    </NavLink>
                  </li>
                )
              })}
            </ul>
          </div>
        ))}
      </nav>

      <div className="border-t border-line/80 px-5 py-4">
        <p className="flex items-center gap-2 text-[11px] text-muted">
          <Lock className="size-3.5 text-cyan-glow/70" aria-hidden="true" />
          Loopback only · local first
        </p>
        <p className="mt-1 text-[10px] leading-4 text-faint">
          No telemetry. Encryption and predictions fail closed.
        </p>
      </div>
    </div>
  )
}

export function Sidebar() {
  return (
    <aside className="sticky top-0 hidden h-screen w-72 shrink-0 border-r border-line bg-navy-900/50 lg:flex">
      <SidebarContent />
    </aside>
  )
}

export function MobileSidebar({ open, onClose }: { open: boolean; onClose: () => void }) {
  if (!open) return null
  return (
    <div className="fixed inset-0 z-50 lg:hidden">
      <button
        type="button"
        className="absolute inset-0 bg-black/70 backdrop-blur-sm"
        aria-label="Close navigation"
        onClick={onClose}
      />
      <aside
        id="mobile-navigation"
        className="absolute inset-y-0 left-0 flex w-72 max-w-[85vw] flex-col border-r border-line bg-navy-900 shadow-2xl"
      >
        <div className="flex items-center justify-between border-b border-line/80 px-4 py-3">
          <span className="text-xs font-semibold uppercase tracking-[0.16em] text-faint">
            Navigation
          </span>
          <button
            type="button"
            onClick={onClose}
            className="flex size-9 items-center justify-center rounded-lg border border-line text-muted hover:bg-navy-800 hover:text-ink"
            aria-label="Close navigation"
          >
            <X className="size-4" aria-hidden="true" />
          </button>
        </div>
        <div className="min-h-0 flex-1">
          <SidebarContent onNavigate={onClose} />
        </div>
      </aside>
    </div>
  )
}
