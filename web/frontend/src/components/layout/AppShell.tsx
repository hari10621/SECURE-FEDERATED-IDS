import { useEffect, useState } from 'react'
import { Outlet, useLocation } from 'react-router-dom'
import { MobileSidebar, Sidebar } from './Sidebar'
import { Topbar } from './Topbar'

export function AppShell() {
  const [mobileOpen, setMobileOpen] = useState(false)
  const location = useLocation()

  useEffect(() => {
    setMobileOpen(false)
  }, [location.pathname])

  return (
    <div className="flex min-h-screen bg-navy-950">
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-[60] focus:rounded-lg focus:bg-cyan-deep focus:px-4 focus:py-2 focus:text-sm focus:font-semibold focus:text-navy-950"
      >
        Skip to content
      </a>
      <Sidebar />
      <MobileSidebar open={mobileOpen} onClose={() => setMobileOpen(false)} />
      <div className="flex min-w-0 flex-1 flex-col">
        <Topbar onMenu={() => setMobileOpen(true)} />
        <main id="main-content" className="relative flex-1">
          <div className="surface-grid pointer-events-none absolute inset-0 opacity-[0.35]" aria-hidden="true" />
          <div className="relative mx-auto w-full max-w-[1440px] px-4 py-6 sm:px-6 lg:px-8 lg:py-8">
            <Outlet />
          </div>
        </main>
        <footer className="border-t border-line/70 px-4 py-4 text-center text-[11px] text-faint sm:px-6 lg:px-8">
          SecureFed-IDS local console · results are local and unverified unless explicitly labelled
        </footer>
      </div>
    </div>
  )
}
