import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import App from '@/App'

beforeEach(() => {
  vi.stubGlobal(
    'fetch',
    vi.fn(() =>
      Promise.resolve(new Response(JSON.stringify({ status: 'ok', db: 'ok' }), { status: 200 })),
    ),
  )
})

describe('App', () => {
  it('renders both tabs and switches the active one on click', async () => {
    render(<App />)

    const recordTab = screen.getByRole('tab', { name: '记录' })
    const boardTab = screen.getByRole('tab', { name: '看板' })

    expect(recordTab).toBeInTheDocument()
    expect(boardTab).toBeInTheDocument()
    expect(recordTab).toHaveAttribute('aria-selected', 'true')
    expect(boardTab).toHaveAttribute('aria-selected', 'false')

    await userEvent.click(boardTab)

    expect(boardTab).toHaveAttribute('aria-selected', 'true')
    expect(recordTab).toHaveAttribute('aria-selected', 'false')
  })
})
