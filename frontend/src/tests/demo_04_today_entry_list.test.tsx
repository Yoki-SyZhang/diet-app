// 1.9 今日明细:四个固定餐次分组/小计/合计、null 营养素显示"—"不是 0、空态、
// 展开收起、删除二次确认、存在未结束卡片时删除禁用。
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { TodayEntryList } from '@/components/TodayEntryList'
import type { MealEntryOut } from '@/types/diet'

let nextId = 1
function entry(overrides: Partial<MealEntryOut> = {}): MealEntryOut {
  return {
    id: nextId++,
    confirmation_id: `conf-${nextId}`,
    date: '2026-08-24',
    meal_slot: 'lunch',
    food_name: '熟鸡胸肉',
    quantity: 150,
    unit: 'g',
    kcal: 200,
    carb_g: 0,
    protein_g: 30,
    fat_g: 5,
    fiber_g: null,
    source_tag: 'llm_estimate',
    created_at: '2026-08-24T12:00:00+00:00',
    ...overrides,
  }
}

describe('TodayEntryList', () => {
  it('groups entries into four fixed slots; empty slots show 未记录 and are not expandable', () => {
    render(
      <TodayEntryList
        entries={[entry({ meal_slot: 'lunch', food_name: '午饭肉' })]}
        disabled={false}
        onDelete={vi.fn()}
      />,
    )

    for (const label of ['早餐', '午餐', '晚餐', '其他']) {
      expect(screen.getByText(label)).toBeInTheDocument()
    }
    expect(screen.getAllByText('未记录')).toHaveLength(3)
    expect(screen.getByText('午饭肉')).toBeInTheDocument()

    const breakfastHead = screen.getByText('早餐').closest('button')!
    expect(breakfastHead).toBeDisabled()
  })

  it('collapses and re-expands a non-empty group', async () => {
    render(
      <TodayEntryList entries={[entry({ food_name: '午饭肉' })]} disabled={false} onDelete={vi.fn()} />,
    )

    const lunchHead = screen.getByText('午餐').closest('button')!
    expect(lunchHead).toHaveAttribute('aria-expanded', 'true')

    await userEvent.click(lunchHead)
    expect(screen.queryByText('午饭肉')).not.toBeInTheDocument()

    await userEvent.click(lunchHead)
    expect(screen.getByText('午饭肉')).toBeInTheDocument()
  })

  it('intake total sums kcal; group subtotal shows — when all values missing', () => {
    render(
      <TodayEntryList
        entries={[
          entry({ meal_slot: 'lunch', kcal: 200, fiber_g: null }),
          entry({ meal_slot: 'lunch', kcal: 100.4, fiber_g: null }),
        ]}
        disabled={false}
        onDelete={vi.fn()}
      />,
    )

    // 顶部摄入合计(和分组小计都可能是 300,用容器区分)
    expect(document.querySelector('.intake-value')).toHaveTextContent('300')
    const lunchHead = screen.getByText('午餐').closest('button')!
    // 纤维两行都是 null → 小计显示 —,不是 0(AGENTS.md 铁律)
    expect(within(lunchHead).getAllByText('—').length).toBeGreaterThanOrEqual(1)
    expect(screen.getByText('/ — kcal 目标')).toBeInTheDocument() // 目标占位
  })

  it('empty state', () => {
    render(<TodayEntryList entries={[]} disabled={false} onDelete={vi.fn()} />)
    expect(screen.getByText('今天还没有记录')).toBeInTheDocument()
  })

  it('delete flows through confirm dialog', async () => {
    const onDelete = vi.fn()
    const target = entry({ food_name: '待删行' })
    render(<TodayEntryList entries={[target]} disabled={false} onDelete={onDelete} />)

    await userEvent.click(screen.getByRole('button', { name: '删除 待删行' }))
    expect(screen.getByRole('alertdialog')).toBeInTheDocument()
    expect(onDelete).not.toHaveBeenCalled()

    await userEvent.click(screen.getByRole('button', { name: '删除' }))
    expect(onDelete).toHaveBeenCalledWith(target.id)
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument()
  })

  it('cancel in confirm dialog does not delete', async () => {
    const onDelete = vi.fn()
    render(<TodayEntryList entries={[entry({ food_name: '保留行' })]} disabled={false} onDelete={onDelete} />)

    await userEvent.click(screen.getByRole('button', { name: '删除 保留行' }))
    await userEvent.click(screen.getByRole('button', { name: '取消' }))

    expect(onDelete).not.toHaveBeenCalled()
  })

  it('disabled=true disables every delete button', () => {
    render(
      <TodayEntryList
        entries={[entry({ food_name: 'A' }), entry({ food_name: 'B' })]}
        disabled
        onDelete={vi.fn()}
      />,
    )

    expect(screen.getByRole('button', { name: '删除 A' })).toBeDisabled()
    expect(screen.getByRole('button', { name: '删除 B' })).toBeDisabled()
  })

  it('row shows — for missing nutrient and 估 badge for llm_estimate', () => {
    render(
      <TodayEntryList
        entries={[entry({ food_name: '估算行', fiber_g: null, source_tag: 'llm_estimate' })]}
        disabled={false}
        onDelete={vi.fn()}
      />,
    )

    const row = screen.getByText('估算行').closest('.entry-row') as HTMLElement
    expect(within(row).getByText('—')).toBeInTheDocument()
    expect(within(row).getByText('估')).toBeInTheDocument()
  })
})
