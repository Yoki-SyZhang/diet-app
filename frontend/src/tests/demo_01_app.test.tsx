// 1.3 前端 PWA 空壳:记录/看板两个 Tab 都渲染,点击后 aria-selected 正确切换。
// 1.9 起记录页真实挂载 RecordTab(会拉今日消息/明细/open-batch),stub 按 URL 路由。
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import App from '@/App'

beforeEach(() => {
  vi.stubGlobal(
    'fetch',
    vi.fn((input: RequestInfo | URL) => {
      const url = String(input)
      const body = url.endsWith('/health')
        ? { status: 'ok', db: 'ok' }
        : url.endsWith('/open-batch')
          ? null
          : []
      return Promise.resolve(
        new Response(JSON.stringify(body), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
      )
    }),
  )
})

describe('App', () => {
  it('renders both tabs and switches the active one on click', async () => {
    render(<App />)

    expect(await screen.findByText('已连接后端')).toBeInTheDocument()

    const recordTab = screen.getByRole('tab', { name: '记录' })
    const boardTab = screen.getByRole('tab', { name: '看板' })

    expect(recordTab).toBeInTheDocument()
    expect(boardTab).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: '我的' })).toBeInTheDocument()
    expect(recordTab).toHaveAttribute('aria-selected', 'true')
    expect(boardTab).toHaveAttribute('aria-selected', 'false')

    await userEvent.click(boardTab)

    expect(boardTab).toHaveAttribute('aria-selected', 'true')
    expect(recordTab).toHaveAttribute('aria-selected', 'false')
  })
})
