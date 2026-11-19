import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { SettingsPage } from './SettingsPage'

describe('SettingsPage', () => {
  it('saves the base URL and token to local storage', () => {
    render(<SettingsPage />)
    fireEvent.change(screen.getByLabelText(/API base URL/i), {
      target: { value: 'http://127.0.0.1:9100/' },
    })
    fireEvent.change(screen.getByLabelText(/Shared bearer token/i), {
      target: { value: '  secret-token  ' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))

    expect(screen.getByText(/API settings saved/i)).toBeInTheDocument()
    expect(JSON.parse(window.localStorage.getItem('securefed.console.api.v1') ?? '{}')).toEqual({
      baseUrl: 'http://127.0.0.1:9100',
      token: 'secret-token',
    })
  })

  it('shows a validation error for a non-http URL', () => {
    render(<SettingsPage />)
    fireEvent.change(screen.getByLabelText(/API base URL/i), {
      target: { value: 'ftp://127.0.0.1' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))
    expect(screen.getByText(/must use http or https/i)).toBeInTheDocument()
  })
})
