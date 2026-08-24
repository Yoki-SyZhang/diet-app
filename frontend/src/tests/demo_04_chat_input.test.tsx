// 1.9 输入胶囊:普通模式发送/清空/空文本忽略;修改模式的提示文案与按钮文案;
// disabled 状态。修改模式"不触发网络请求"的完整闭环在 demo_04_record_tab_flow 里验证。
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { ChatInputBar } from '@/components/ChatInputBar'
import type { PendingItem } from '@/types/diet'

function makeModifyingItem(): PendingItem {
  return {
    clientItemId: 'c1',
    confirmationId: 'c1',
    uiState: 'to_modify',
    writtenEntryId: null,
    pendingModifyNote: null,
    modifyError: null,
    writeError: null,
    outcome: {
      parsed_item: { food_name: '熟鸡胸肉', quantity: 150, unit: 'g', preparation_state: 'cooked' },
      outcome: 'resolved',
      preview: {
        food_name: '熟鸡胸肉',
        quantity: 150,
        unit: 'g',
        meal_slot: 'lunch',
        nutrients: { kcal: 247.5, carb_g: 0, protein_g: 46.5, fat_g: 5.3, fiber_g: null },
        source_tag: 'llm_estimate',
        confidence: 'high',
        confidence_reason: '常见食材',
        warning: '可能不准',
      },
      message: null,
    },
  }
}

describe('ChatInputBar', () => {
  it('sends trimmed text and clears the field', async () => {
    const onSend = vi.fn()
    render(<ChatInputBar modifyingItem={null} onSend={onSend} />)

    const field = screen.getByPlaceholderText('描述你吃了什么…')
    await userEvent.type(field, '  中午吃了一碗米饭  ')
    await userEvent.click(screen.getByRole('button', { name: '发送' }))

    expect(onSend).toHaveBeenCalledWith('中午吃了一碗米饭')
    expect(field).toHaveValue('')
  })

  it('enter key also sends', async () => {
    const onSend = vi.fn()
    render(<ChatInputBar modifyingItem={null} onSend={onSend} />)

    await userEvent.type(screen.getByPlaceholderText('描述你吃了什么…'), '一根香蕉{Enter}')

    expect(onSend).toHaveBeenCalledWith('一根香蕉')
  })

  it('ignores empty submissions', async () => {
    const onSend = vi.fn()
    render(<ChatInputBar modifyingItem={null} onSend={onSend} />)

    await userEvent.click(screen.getByRole('button', { name: '发送' }))

    expect(onSend).not.toHaveBeenCalled()
  })

  it('modify mode shows target hint and 确认修改 label', () => {
    render(<ChatInputBar modifyingItem={makeModifyingItem()} onSend={vi.fn()} />)

    expect(screen.getByText(/修改:熟鸡胸肉/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '确认修改' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '发送' })).not.toBeInTheDocument()
  })

  it('disabled blocks sending', async () => {
    const onSend = vi.fn()
    render(<ChatInputBar modifyingItem={null} disabled onSend={onSend} />)

    expect(screen.getByRole('button', { name: '发送' })).toBeDisabled()
    expect(screen.getByPlaceholderText('描述你吃了什么…')).toBeDisabled()
  })
})
