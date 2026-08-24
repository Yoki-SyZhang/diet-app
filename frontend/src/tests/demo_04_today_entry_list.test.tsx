// 1.9 今日明细:四个固定餐次分组/小计/合计、null 营养素显示"—"不是 0、空态、
// 展开收起、删除二次确认、存在未结束卡片时删除禁用。
//
// 不测的:--card-collapsed-h / onOverlapChange 这两个量测值。jsdom 不做布局,
// offsetHeight/scrollHeight 恒为 0,断言只能断出"0px 被写进了 style",既证明不了
// 覆盖式展开没挤动聊天,也证明不了渐隐带贴着卡片底边——这两条只能在真实浏览器里
// 量(见 .claude/skills/run-dietapp/)。
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

describe('TodayEntryList 顶部摄入区', () => {
  it('显示四大营养素加总,带单位 g', () => {
    render(
      <TodayEntryList
        entries={[
          entry({ carb_g: 20.4, protein_g: 30, fat_g: 5, fiber_g: 2 }),
          entry({ carb_g: 10.1, protein_g: 12, fat_g: 3, fiber_g: 1 }),
        ]}
        disabled={false}
        onDelete={vi.fn()}
      />,
    )

    expect(screen.getByText('31g')).toBeInTheDocument() // 碳水 20.4+10.1 四舍五入
    expect(screen.getByText('42g')).toBeInTheDocument() // 蛋白
    expect(screen.getByText('8g')).toBeInTheDocument() // 脂肪
    expect(screen.getByText('3g')).toBeInTheDocument() // 纤维
    for (const label of ['碳水', '蛋白', '脂肪', '纤维']) {
      expect(screen.getByText(label, { exact: false })).toBeInTheDocument()
    }
  })

  it('区分"未提供"和"确定为零":null 显示 —,真实的 0 显示 0g', () => {
    const { container } = render(
      <TodayEntryList
        entries={[
          entry({ carb_g: 0, fiber_g: null }),
          entry({ carb_g: 0, fiber_g: null }),
        ]}
        disabled={false}
        onDelete={vi.fn()}
      />,
    )
    const macroValue = (label: string) =>
      [...container.querySelectorAll('.intake-macro')]
        .find((el) => el.textContent?.startsWith(label))!
        .querySelector('b')!.textContent

    // 铁律:null 是"未提供"→ "—"(且不能是 "—g");0 是"确定为零"→ 照常显示 0g
    expect(macroValue('纤维')).toBe('—')
    expect(macroValue('碳水')).toBe('0g')
  })

  it('归属日渲染成 "8月15日 周六";没拿到日期时整行不渲染', () => {
    const { unmount } = render(
      <TodayEntryList entries={[entry()]} disabled={false} onDelete={vi.fn()} date="2026-08-15" />,
    )
    expect(screen.getByText('8月15日 周六')).toBeInTheDocument()
    unmount()

    render(<TodayEntryList entries={[entry()]} disabled={false} onDelete={vi.fn()} />)
    expect(screen.queryByText(/月.*日/)).not.toBeInTheDocument()
  })
})

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

  it('默认全收起;点某餐小计行只展开那一餐', async () => {
    render(
      <TodayEntryList
        entries={[entry({ meal_slot: 'lunch' }), entry({ meal_slot: 'dinner' })]}
        disabled={false}
        onDelete={vi.fn()}
      />,
    )

    const lunchHead = screen.getByText('午餐').closest('button')!
    const dinnerHead = screen.getByText('晚餐').closest('button')!
    // 行常驻 DOM(收放靠 CSS,才能做动画),所以展开态看 aria-expanded/data-open
    const rowsOf = (head: HTMLElement) =>
      head.parentElement!.querySelector('.entry-group__rows')!

    expect(lunchHead).toHaveAttribute('aria-expanded', 'false')
    expect(rowsOf(lunchHead)).toHaveAttribute('data-open', 'false')

    await userEvent.click(lunchHead)
    expect(lunchHead).toHaveAttribute('aria-expanded', 'true')
    expect(rowsOf(lunchHead)).toHaveAttribute('data-open', 'true')
    expect(dinnerHead).toHaveAttribute('aria-expanded', 'false') // 只开这一餐

    await userEvent.click(lunchHead)
    expect(lunchHead).toHaveAttribute('aria-expanded', 'false')
  })

  it('点顶部摄入区一键展开全部/一键收起;空明细时不可点', async () => {
    const { unmount } = render(
      <TodayEntryList
        entries={[entry({ meal_slot: 'lunch' }), entry({ meal_slot: 'dinner' })]}
        disabled={false}
        onDelete={vi.fn()}
      />,
    )

    const heads = () => ['午餐', '晚餐'].map((l) => screen.getByText(l).closest('button')!)
    expect(document.querySelector('.intake-caret')).not.toBeInTheDocument()
    expect(heads().map((h) => h.getAttribute('aria-expanded'))).toEqual(['false', 'false'])

    await userEvent.click(screen.getByRole('button', { name: '展开全部明细' }))
    expect(heads().map((h) => h.getAttribute('aria-expanded'))).toEqual(['true', 'true'])

    await userEvent.click(screen.getByRole('button', { name: '收起全部明细' }))
    expect(heads().map((h) => h.getAttribute('aria-expanded'))).toEqual(['false', 'false'])

    unmount()
    render(<TodayEntryList entries={[]} disabled={false} onDelete={vi.fn()} />)
    expect(screen.getByRole('button', { name: '展开全部明细' })).toBeDisabled()
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
