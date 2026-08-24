// 1.9 通用二次确认对话框:开/关渲染、文案按场景传入、两个按钮回调。
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { UnconfirmedGuardDialog } from '@/components/UnconfirmedGuardDialog'

const baseProps = {
  title: '还有未确认的解析结果',
  message: '还有 2 项没确认,不确认就不会被记录,确定要放弃吗?',
  confirmLabel: '放弃并继续',
  cancelLabel: '返回处理',
}

describe('UnconfirmedGuardDialog', () => {
  it('portals the backdrop to the phone screen so the bottom tabbar stays outside it', () => {
    const screenRoot = document.createElement('div')
    screenRoot.className = 'device__screen'
    const tabbar = document.createElement('div')
    tabbar.className = 'tabbar'
    screenRoot.append(tabbar)
    document.body.append(screenRoot)

    const view = render(
      <UnconfirmedGuardDialog open {...baseProps} onConfirm={vi.fn()} onCancel={vi.fn()} />,
    )

    const backdrop = screenRoot.querySelector('.dialog-backdrop')!
    expect(backdrop.parentElement).toBe(screenRoot)
    expect(backdrop.querySelector('.tabbar')).not.toBeInTheDocument()

    view.unmount()
    screenRoot.remove()
  })

  it('renders nothing when closed', () => {
    render(
      <UnconfirmedGuardDialog
        open={false}
        {...baseProps}
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />,
    )
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument()
  })

  it('renders passed-in copy when open', () => {
    render(
      <UnconfirmedGuardDialog open {...baseProps} onConfirm={vi.fn()} onCancel={vi.fn()} />,
    )
    expect(screen.getByRole('alertdialog')).toBeInTheDocument()
    expect(screen.getByText(baseProps.title)).toBeInTheDocument()
    expect(screen.getByText(baseProps.message)).toBeInTheDocument()
  })

  it('fires onConfirm / onCancel from the two buttons', async () => {
    const onConfirm = vi.fn()
    const onCancel = vi.fn()
    render(
      <UnconfirmedGuardDialog open {...baseProps} onConfirm={onConfirm} onCancel={onCancel} />,
    )

    await userEvent.click(screen.getByRole('button', { name: '放弃并继续' }))
    expect(onConfirm).toHaveBeenCalledTimes(1)

    await userEvent.click(screen.getByRole('button', { name: '返回处理' }))
    expect(onCancel).toHaveBeenCalledTimes(1)
  })

  it('reused for resume-batch copy', () => {
    render(
      <UnconfirmedGuardDialog
        open
        title="继续上次的识别结果?"
        message="上次有 3 项识别结果没有处理完,是否继续?"
        confirmLabel="继续"
        cancelLabel="放弃"
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />,
    )
    expect(screen.getByRole('button', { name: '继续' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '放弃' })).toBeInTheDocument()
  })
})
