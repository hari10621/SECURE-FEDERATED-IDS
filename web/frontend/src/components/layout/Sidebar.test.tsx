import { render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import { Sidebar } from './Sidebar'

function renderSidebar(path = '/') {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Sidebar />
    </MemoryRouter>,
  )
}

describe('Sidebar', () => {
  it('renders the eleven current dashboard pages', () => {
    renderSidebar()
    const nav = screen.getByRole('navigation', { name: 'Primary' })
    expect(within(nav).getAllByRole('link')).toHaveLength(11)
    expect(within(nav).getByText('Federated Training')).toBeInTheDocument()
    expect(within(nav).queryByText('Homomorphic Encryption')).not.toBeInTheDocument()
    expect(within(nav).queryByText('IPS & Prevention')).not.toBeInTheDocument()
    expect(within(nav).getByText('Settings')).toBeInTheDocument()
  })

  it('marks the current route with aria-current', () => {
    renderSidebar('/training')
    const nav = screen.getByRole('navigation', { name: 'Primary' })
    const active = within(nav).getByRole('link', { name: /Federated Training/ })
    expect(active).toHaveAttribute('aria-current', 'page')
  })
})
