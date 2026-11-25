import { Compass } from 'lucide-react'
import { Link } from 'react-router-dom'
import { buttonStyles } from '../components/ui/Button'
import { PageHeader } from '../components/ui/PageHeader'
import { EmptyState } from '../components/ui/States'

export function NotFoundPage() {
  return (
    <div>
      <PageHeader title="Page not found" />
      <div className="rounded-xl border border-line bg-navy-900/70">
        <EmptyState
          title="This route does not exist"
          description="Check the address or return to Overview."
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
