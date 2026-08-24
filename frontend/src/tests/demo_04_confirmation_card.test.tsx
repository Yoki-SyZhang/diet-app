// 1.9 解析结果卡片(展示与回调层):确认/修改互斥双态渲染、kcal 合计口径、cardBusy
// 全按钮禁用、confirmed 终态无按钮、abandoned 不渲染、writeError/修改留痕/修改失败
// 的展示文字。状态转移本身归 RecordTab,在 demo_04_record_tab_flow 里验证。
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { ConfirmationCard } from '@/components/ConfirmationCard'
import type { ItemUiState, PendingItem } from '@/types/diet'

function makeItem(overrides: Partial<PendingItem> & { name?: string; kcal?: number } = {}): PendingItem {
  const { name = '熟鸡胸肉', kcal = 200, ...rest } = overrides
  return {
    clientItemId: rest.clientItemId ?? name,
    confirmationId: rest.clientItemId ?? name,
    uiState: 'pending',
    writtenEntryId: null,
    pendingModifyNote: null,
    modifyError: null,
    writeError: null,
    outcome: {
      parsed_item: { food_name: name, quantity: 150, unit: 'g', preparation_state: 'cooked' },
      outcome: 'resolved',
      preview: {
        food_name: name,
        quantity: 150,
        unit: 'g',
        meal_slot: 'lunch',
        nutrients: { kcal, carb_g: 0, protein_g: 30, fat_g: 5, fiber_g: null },
        source_tag: 'llm_estimate',
        confidence: 'high',
        confidence_reason: '常见食材',
        warning: '可能不准',
      },
      message: null,
    },
    ...rest,
  }
}

const noop = {
  onToggleConfirm: vi.fn(),
  onToggleModify: vi.fn(),
  onTopConfirm: vi.fn(),
  onTopAbandon: vi.fn(),
}

describe('ConfirmationCard', () => {
  it('renders meal slot header and warning badge per item', () => {
    render(<ConfirmationCard items={[makeItem()]} cardBusy={false} {...noop} />)

    expect(screen.getByText('解析结果 · 午餐')).toBeInTheDocument()
    expect(screen.getByText('网络估算 · 可能不准')).toBeInTheDocument()
    expect(screen.getByText('熟鸡胸肉')).toBeInTheDocument()
  })

  it('kcal total only counts to_confirm and confirmed items', () => {
    const items = [
      makeItem({ name: 'A', kcal: 100, uiState: 'to_confirm' }),
      makeItem({ name: 'B', kcal: 40, uiState: 'confirmed' }),
      makeItem({ name: 'C', kcal: 999, uiState: 'pending' }),
    ]
    render(<ConfirmationCard items={items} cardBusy={false} {...noop} />)

    expect(screen.getByText('140')).toBeInTheDocument()
  })

  it('toggle buttons show is-on state exclusively', () => {
    const items = [
      makeItem({ name: 'A', uiState: 'to_confirm' }),
      makeItem({ name: 'B', uiState: 'to_reparse', pendingModifyNote: '改成300g' }),
    ]
    render(<ConfirmationCard items={items} cardBusy={false} {...noop} />)

    const rows = screen.getAllByText(/^[AB]$/).map((el) => el.closest('.confirm-item') as HTMLElement)
    const rowA = within(rows[0])
    const rowB = within(rows[1])

    expect(rowA.getByRole('button', { name: '确认' })).toHaveClass('is-on')
    expect(rowA.getByRole('button', { name: '修改' })).not.toHaveClass('is-on')
    expect(rowB.getByRole('button', { name: '修改' })).toHaveClass('is-on')
    expect(rowB.getByRole('button', { name: '确认' })).not.toHaveClass('is-on')
    // 暂存修改的留痕(前10字)
    expect(screen.getByText(/^修改:改成300g/)).toBeInTheDocument()
  })

  it('fires item and top callbacks', async () => {
    const onToggleConfirm = vi.fn()
    const onToggleModify = vi.fn()
    const onTopConfirm = vi.fn()
    const onTopAbandon = vi.fn()
    render(
      <ConfirmationCard
        items={[makeItem({ name: 'A' })]}
        cardBusy={false}
        onToggleConfirm={onToggleConfirm}
        onToggleModify={onToggleModify}
        onTopConfirm={onTopConfirm}
        onTopAbandon={onTopAbandon}
      />,
    )

    const buttons = screen.getAllByRole('button', { name: '确认' })
    // 顶部确认在 header 里,单项确认在行内(btn-toggle)
    const topConfirm = buttons.find((b) => b.className.includes('btn-primary'))!
    const itemConfirm = buttons.find((b) => b.className.includes('btn-toggle'))!

    await userEvent.click(itemConfirm)
    expect(onToggleConfirm).toHaveBeenCalledWith('A')

    await userEvent.click(screen.getByRole('button', { name: '修改' }))
    expect(onToggleModify).toHaveBeenCalledWith('A')

    await userEvent.click(topConfirm)
    expect(onTopConfirm).toHaveBeenCalledTimes(1)

    await userEvent.click(screen.getByRole('button', { name: '放弃' }))
    expect(onTopAbandon).toHaveBeenCalledTimes(1)
  })

  it('cardBusy disables every button', () => {
    render(
      <ConfirmationCard
        items={[makeItem({ name: 'A' }), makeItem({ name: 'B', uiState: 'to_confirm' })]}
        cardBusy
        {...noop}
      />,
    )

    for (const button of screen.getAllByRole('button')) {
      expect(button).toBeDisabled()
    }
  })

  it('confirmed item is terminal: 已写入 chip, no buttons in its row', () => {
    render(
      <ConfirmationCard items={[makeItem({ name: 'A', uiState: 'confirmed' })]} cardBusy={false} {...noop} />,
    )

    expect(screen.getByText('已写入')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '修改' })).not.toBeInTheDocument()
    // 顶部确认/放弃仍在(卡片还没整体结束)
    expect(screen.getByRole('button', { name: '确认' })).toHaveClass('btn-primary')
  })

  it('abandoned items are not rendered; all-abandoned renders nothing', () => {
    const { container } = render(
      <ConfirmationCard
        items={[makeItem({ name: 'A', uiState: 'abandoned' as ItemUiState })]}
        cardBusy={false}
        {...noop}
      />,
    )
    expect(container).toBeEmptyDOMElement()
  })

  it('shows writeError and modifyError texts', () => {
    const items = [
      makeItem({ name: 'A', uiState: 'to_confirm', writeError: '写入失败,可重试' }),
      makeItem({ name: 'B', modifyError: '修改失败,请重新描述' }),
    ]
    render(<ConfirmationCard items={items} cardBusy={false} {...noop} />)

    expect(screen.getByText('写入失败,可重试')).toBeInTheDocument()
    expect(screen.getByText('修改失败,请重新描述')).toBeInTheDocument()
  })

  it('modifying item shows progress text instead of buttons', () => {
    render(
      <ConfirmationCard
        items={[makeItem({ name: 'A', uiState: 'modifying', pendingModifyNote: '改成300g' })]}
        cardBusy
        {...noop}
      />,
    )
    expect(screen.getByText('重新估算中…')).toBeInTheDocument()
  })
})
