import { Compass } from 'lucide-react'
import { Link } from 'react-router-dom'
import { buttonStyles } from '../components/ui/Button'
import { PageHeader } from '../components/ui/PageHeader'
import { EmptyState } from '../components/ui/States'

export function NotFoundPage() {
  return (
    <div>
      <PageHeader eyebrow="System" title="Page not found" />
      <div className="rounded-xl border border-line bg-navy-900/70">
        <EmptyState
          title="This route does not exist"
          description="The console has twelve configured pages. Use the navigation or return to the overview."
          icon={<Compass className="size-5" aria-hidden="true" />}
          action={
            <Link to="/" className={buttonStyles('primary', 'sm')}>
              Back to overview
            </Link>
          }
        />
      </div>
    </div>
  )
}
