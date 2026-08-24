// 1.9 RecordTab 集成(mock HTTP 层):完整闭环——发送→部分估算失败(只进播报不进
// 卡片)→暂存确认+暂存修改→顶部确认(写入+重新估算)→修改项回到待处理→再次确认→
// 全部终态后只出现一条总结气泡;追问循环;全部失败无卡片;写入失败重试;未确认
// 放弃弹窗;刷新后 open-batch 继续/放弃;卡片存在期间今日明细删除禁用。
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { RecordTab } from '@/components/RecordTab'
import type { ChatMessageOut, ConfirmableItem } from '@/types/diet'

let nextMessageId = 100

function msg(role: 'user' | 'assistant', content: string, extra: Partial<ChatMessageOut> = {}): ChatMessageOut {
  return {
    id: nextMessageId++,
    date: '2026-08-24',
    role,
    content,
    image_ref: null,
    created_at: '2026-08-24T12:00:00+00:00',
    batch_id: null,
    kind: null,
    ...extra,
  }
}

function confirmable(cid: string, name: string, kcal: number, quantity = 150): ConfirmableItem {
  return {
    confirmation_id: cid,
    outcome: {
      parsed_item: { food_name: name, quantity, unit: 'g', preparation_state: 'cooked' },
      outcome: 'resolved',
      preview: {
        food_name: name,
        quantity,
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
  }
}

interface MockApi {
  todayMessages: ChatMessageOut[]
  todayEntries: unknown[]
  openBatch: unknown
  chatQueue: unknown[]
  modifyQueue: unknown[]
  failNextConfirm: number
  chatCalls: unknown[]
  modifyCalls: unknown[]
  confirmCalls: { confirmation_id: string; now_utc: string }[]
  recapCalls: { batch_id: string; items: { food_name: string; state: string }[] }[]
  deleteCalls: string[]
}

let api: MockApi
let nextEntryId = 1

function json(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

function installFetchMock() {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input).replace('http://localhost:8000', '')
      const method = init?.method ?? 'GET'
      const body = init?.body ? JSON.parse(String(init.body)) : undefined

      if (path === '/chat/messages/today' && method === 'GET') return json(api.todayMessages)
      if (path === '/meal-entries/today' && method === 'GET') return json(api.todayEntries)
      if (path === '/chat/messages/open-batch' && method === 'GET') return json(api.openBatch)
      if (path === '/chat/messages' && method === 'POST') {
        api.chatCalls.push(body)
        return json(api.chatQueue.shift())
      }
      if (path === '/chat/messages/modify' && method === 'POST') {
        api.modifyCalls.push(body)
        return json(api.modifyQueue.shift())
      }
      if (path === '/chat/messages/recap' && method === 'POST') {
        api.recapCalls.push(body)
        return json({
          assistant_message: msg('assistant', `总结:${body.batch_id} 处理完成`, {
            batch_id: body.batch_id,
            kind: 'recap',
          }),
        })
      }
      if (path === '/meal-entries' && method === 'POST') {
        if (api.failNextConfirm > 0) {
          api.failNextConfirm -= 1
          return json({ detail: 'boom' }, 500)
        }
        api.confirmCalls.push(body)
        return json(
          {
            id: nextEntryId++,
            confirmation_id: body.confirmation_id,
            date: '2026-08-24',
            meal_slot: body.preview.meal_slot,
            food_name: body.preview.food_name,
            quantity: body.preview.quantity,
            unit: body.preview.unit,
            ...body.preview.nutrients,
            source_tag: body.preview.source_tag,
            created_at: body.now_utc,
          },
          201,
        )
      }
      if (path.startsWith('/meal-entries/') && method === 'DELETE') {
        api.deleteCalls.push(path)
        return new Response(null, { status: 204 })
      }
      throw new Error(`unexpected request: ${method} ${path}`)
    }),
  )
}

beforeEach(() => {
  api = {
    todayMessages: [],
    todayEntries: [],
    openBatch: null,
    chatQueue: [],
    modifyQueue: [],
    failNextConfirm: 0,
    chatCalls: [],
    modifyCalls: [],
    confirmCalls: [],
    recapCalls: [],
    deleteCalls: [],
  }
  installFetchMock()
})

async function sendText(text: string, buttonName = '发送') {
  await userEvent.type(screen.getByPlaceholderText(/描述你吃了什么|比如:/), text)
  await userEvent.click(screen.getByRole('button', { name: buttonName }))
}

function queueResolvedTurn(batchId: string, items: ConfirmableItem[], broadcast: string) {
  api.chatQueue.push({
    user_message: msg('user', '午饭吃了鸡胸肉和米饭'),
    assistant_message: msg('assistant', broadcast, { batch_id: batchId, kind: 'recognition' }),
    intent: 'new_entry',
    outcome: 'resolved',
    batch_id: batchId,
    items,
  })
}

describe('RecordTab full journey', () => {
  it('部分估算失败只进播报;暂存确认+暂存修改;分两次顶部确认;终态后恰好一条总结', async () => {
    queueResolvedTurn(
      'B1',
      [confirmable('cA', '熟鸡胸肉', 200), confirmable('cB', '白米饭', 232, 200)],
      '我识别到了(午餐):熟鸡胸肉 150g、白米饭 200g。以下食物这次没能完成估算,不会出现在卡片里:神秘炖菜(AI 服务暂时不可用)。',
    )
    render(<RecordTab />)
    await sendText('午饭吃了鸡胸肉、米饭和神秘炖菜')

    // 播报里有失败项,卡片里没有
    const card = await screen.findByRole('region', { name: '解析结果卡片' })
    expect(screen.getByText(/神秘炖菜/)).toBeInTheDocument()
    expect(within(card).queryByText(/神秘炖菜/)).not.toBeInTheDocument()
    expect(within(card).getByText('熟鸡胸肉')).toBeInTheDocument()
    expect(within(card).getByText('白米饭')).toBeInTheDocument()

    // 暂存:A 确认,B 修改(输入框切修改模式→确认修改,纯本地)
    const rowA = within(screen.getByText('熟鸡胸肉').closest('.confirm-item') as HTMLElement)
    const rowB = within(screen.getByText('白米饭').closest('.confirm-item') as HTMLElement)
    await userEvent.click(rowA.getByRole('button', { name: '确认' }))
    await userEvent.click(rowB.getByRole('button', { name: '修改' }))
    expect(screen.getByText(/修改:白米饭/)).toBeInTheDocument()

    const chatCallsBefore = api.chatCalls.length
    await sendText('其实是蛋炒饭300g', '确认修改')
    expect(api.chatCalls.length).toBe(chatCallsBefore) // 纯本地暂存,没有网络请求
    expect(screen.getByText(/^修改:其实是蛋炒饭300/)).toBeInTheDocument()

    // 顶部确认:写入 A + 触发 B 重新估算
    api.modifyQueue.push({
      confirmation_id: 'cB',
      success: true,
      outcome: confirmable('cB', '蛋炒饭', 540, 300).outcome,
      failure_reason: null,
    })
    const topConfirm = screen
      .getAllByRole('button', { name: '确认' })
      .find((b) => b.className.includes('btn-primary'))!
    await userEvent.click(topConfirm)

    // A 已写入并进今日明细;B 带新预览值回到待处理;还没有总结
    await screen.findByText('已写入')
    expect(api.confirmCalls.map((c) => c.confirmation_id)).toEqual(['cA'])
    expect(api.modifyCalls).toHaveLength(1)
    const todayCard = screen.getByRole('region', { name: '今日明细' })
    expect(within(todayCard).getByText('熟鸡胸肉')).toBeInTheDocument()
    expect(await screen.findByText('蛋炒饭')).toBeInTheDocument()
    expect(api.recapCalls).toHaveLength(0)

    // 卡片未结束:今日明细删除按钮禁用
    expect(within(todayCard).getByRole('button', { name: '删除 熟鸡胸肉' })).toBeDisabled()

    // B 再确认 → 顶部确认 → 全部终态
    const rowB2 = within(screen.getByText('蛋炒饭').closest('.confirm-item') as HTMLElement)
    await userEvent.click(rowB2.getByRole('button', { name: '确认' }))
    await userEvent.click(
      screen.getAllByRole('button', { name: '确认' }).find((b) => b.className.includes('btn-primary'))!,
    )

    // 只有一条总结气泡;卡片消失;删除恢复可用
    await screen.findByText(/总结:B1 处理完成/)
    expect(api.recapCalls).toHaveLength(1)
    expect(api.recapCalls[0].items.map((i) => i.state)).toEqual(['confirmed', 'confirmed'])
    expect(screen.queryByRole('region', { name: '解析结果卡片' })).not.toBeInTheDocument()
    await waitFor(() =>
      expect(within(todayCard).getByRole('button', { name: '删除 熟鸡胸肉' })).toBeEnabled(),
    )
    // 两次批量请求共用同一个 now_utc 语义:同一次点击里的写入使用同一时刻
    expect(api.confirmCalls).toHaveLength(2)
  })

  it('needs_clarification 循环:追问期间不出现卡片,resolved 后才弹卡', async () => {
    api.chatQueue.push({
      user_message: msg('user', '我吃了鸡胸肉'),
      assistant_message: msg('assistant', '大概吃了多少克呢?'),
      intent: 'new_entry',
      outcome: 'needs_clarification',
      batch_id: null,
      items: [],
    })
    render(<RecordTab />)
    await sendText('我吃了鸡胸肉')

    await screen.findByText('大概吃了多少克呢?')
    expect(screen.queryByRole('region', { name: '解析结果卡片' })).not.toBeInTheDocument()

    queueResolvedTurn('B2', [confirmable('cX', '熟鸡胸肉', 200)], '我识别到了(午餐):熟鸡胸肉 150g。')
    await sendText('150g,熟的')
    expect(await screen.findByRole('region', { name: '解析结果卡片' })).toBeInTheDocument()
  })

  it('全部估算失败:没有卡片,只有播报气泡', async () => {
    api.chatQueue.push({
      user_message: msg('user', '我吃了神秘炖菜'),
      assistant_message: msg('assistant', '以下食物这次没能完成估算,不会出现在卡片里:神秘炖菜(服务不可用)。'),
      intent: 'new_entry',
      outcome: 'resolved',
      batch_id: null,
      items: [],
    })
    render(<RecordTab />)
    await sendText('我吃了神秘炖菜')

    await screen.findByText(/不会出现在卡片里/)
    expect(screen.queryByRole('region', { name: '解析结果卡片' })).not.toBeInTheDocument()
    expect(api.recapCalls).toHaveLength(0)
  })

  it('单项写入失败保留暂存态,再次顶部确认靠幂等键重试成功', async () => {
    queueResolvedTurn('B3', [confirmable('cA', '熟鸡胸肉', 200)], '识别到熟鸡胸肉')
    render(<RecordTab />)
    await sendText('午饭吃了150g熟鸡胸肉')
    await screen.findByRole('region', { name: '解析结果卡片' })

    await userEvent.click(
      within(screen.getByText('熟鸡胸肉').closest('.confirm-item') as HTMLElement).getByRole(
        'button',
        { name: '确认' },
      ),
    )
    api.failNextConfirm = 1
    const topConfirm = () =>
      screen.getAllByRole('button', { name: '确认' }).find((b) => b.className.includes('btn-primary'))!
    await userEvent.click(topConfirm())

    await screen.findByText('写入失败,可重试')
    expect(api.recapCalls).toHaveLength(0)

    await userEvent.click(topConfirm())
    await screen.findByText(/总结:B3 处理完成/)
    expect(api.confirmCalls.map((c) => c.confirmation_id)).toEqual(['cA'])
    expect(api.recapCalls).toHaveLength(1)
  })

  it('修改重新估算失败:数值退回,提示修改失败', async () => {
    queueResolvedTurn('B4', [confirmable('cA', '熟鸡胸肉', 200)], '识别到熟鸡胸肉')
    render(<RecordTab />)
    await sendText('午饭吃了150g熟鸡胸肉')
    await screen.findByRole('region', { name: '解析结果卡片' })

    await userEvent.click(screen.getByRole('button', { name: '修改' }))
    await sendText('随便改改', '确认修改')
    api.modifyQueue.push({
      confirmation_id: 'cA',
      success: false,
      outcome: null,
      failure_reason: '修改失败,请重新描述',
    })
    await userEvent.click(
      screen.getAllByRole('button', { name: '确认' }).find((b) => b.className.includes('btn-primary'))!,
    )

    await screen.findByText('修改失败,请重新描述')
    // 数值退回修改前
    expect(screen.getByText('200')).toBeInTheDocument()
    expect(screen.queryByText(/^修改:随便改改/)).not.toBeInTheDocument()
  })

  it('有未确认项时直接打字被拦截;放弃并继续会转 abandoned+发 recap+发送新消息', async () => {
    queueResolvedTurn('B5', [confirmable('cA', '熟鸡胸肉', 200)], '识别到熟鸡胸肉')
    render(<RecordTab />)
    await sendText('午饭吃了150g熟鸡胸肉')
    await screen.findByRole('region', { name: '解析结果卡片' })

    api.chatQueue.push({
      user_message: msg('user', '下午喝了一杯拿铁'),
      assistant_message: msg('assistant', '好的,已识别拿铁'),
      intent: 'new_entry',
      outcome: 'needs_clarification',
      batch_id: null,
      items: [],
    })
    await sendText('下午喝了一杯拿铁')

    // 弹窗拦截,消息还没发出去
    expect(screen.getByRole('alertdialog')).toBeInTheDocument()
    expect(api.chatCalls).toHaveLength(1)

    await userEvent.click(screen.getByRole('button', { name: '放弃并继续' }))

    await screen.findByText('好的,已识别拿铁')
    expect(api.chatCalls).toHaveLength(2)
    expect(api.recapCalls).toHaveLength(1)
    expect(api.recapCalls[0].items.map((i) => i.state)).toEqual(['abandoned'])
    expect(screen.queryByRole('region', { name: '解析结果卡片' })).not.toBeInTheDocument()
  })

  it('挂载发现未完成批次:继续重建卡片并复用 batch_id', async () => {
    api.openBatch = {
      batch_id: 'B9',
      items: [confirmable('cOld', '昨晚的米饭', 232)],
    }
    render(<RecordTab />)

    await screen.findByText(/上次有 1 项识别结果没有处理完/)
    await userEvent.click(screen.getByRole('button', { name: '继续' }))

    const card = await screen.findByRole('region', { name: '解析结果卡片' })
    expect(within(card).getByText('昨晚的米饭')).toBeInTheDocument()

    // 顶部放弃 → recap 复用 B9
    await userEvent.click(within(card).getByRole('button', { name: '放弃' }))
    await screen.findByText(/总结:B9 处理完成/)
    expect(api.recapCalls[0].batch_id).toBe('B9')
    expect(api.recapCalls[0].items.map((i) => i.state)).toEqual(['abandoned'])
  })

  it('挂载发现未完成批次:放弃直接整批 abandoned 发 recap,不重建卡片', async () => {
    api.openBatch = {
      batch_id: 'B9',
      items: [confirmable('cOld', '昨晚的米饭', 232)],
    }
    render(<RecordTab />)

    await screen.findByText(/上次有 1 项识别结果没有处理完/)
    await userEvent.click(screen.getByRole('button', { name: '放弃' }))

    await waitFor(() => expect(api.recapCalls).toHaveLength(1))
    expect(api.recapCalls[0].batch_id).toBe('B9')
    expect(screen.queryByRole('region', { name: '解析结果卡片' })).not.toBeInTheDocument()
  })

  it('挂载的今日消息 GET 在 POST 处理中途被受理:同一条消息不重复渲染', async () => {
    // 真实冒烟测出的竞态:POST 等 LLM 的几秒里,后端先受理了挂载时的 GET,
    // 返回列表已含刚写入的用户消息;POST 响应回来再 append 就重复了。
    const userMsg = msg('user', '我吃了鸡胸肉')
    const assistantMsg = msg('assistant', '大概多少克呢?')

    let resolveToday!: (r: Response) => void
    let resolvePost!: (r: Response) => void
    const fetchMock = globalThis.fetch as ReturnType<typeof vi.fn>
    // getMockImplementation() 的联合类型含构造签名,直接调用过不了 tsc,按用法收窄
    const original = fetchMock.getMockImplementation() as (
      input: RequestInfo | URL,
      init?: RequestInit,
    ) => Promise<Response>
    fetchMock.mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input).replace('http://localhost:8000', '')
      const method = init?.method ?? 'GET'
      if (path === '/chat/messages/today' && method === 'GET') {
        return new Promise<Response>((res) => {
          resolveToday = res
        })
      }
      if (path === '/chat/messages' && method === 'POST') {
        return new Promise<Response>((res) => {
          resolvePost = res
        })
      }
      return original(input, init)
    })

    render(<RecordTab />)
    await sendText('我吃了鸡胸肉')

    // POST 还没返回,此时"历史"GET 先返回,已包含这条用户消息
    await waitFor(() => expect(resolveToday).toBeDefined())
    resolveToday(json([userMsg]))
    await screen.findByText('我吃了鸡胸肉')

    resolvePost(
      json({
        user_message: userMsg,
        assistant_message: assistantMsg,
        intent: 'new_entry',
        outcome: 'needs_clarification',
        batch_id: null,
        items: [],
      }),
    )

    await screen.findByText('大概多少克呢?')
    expect(screen.getAllByText('我吃了鸡胸肉')).toHaveLength(1)
  })

  it('发送后不等 LLM:用户气泡和"正在解析中…"立刻上屏,回执到达再替换', async () => {
    // 解析要等好几秒;等响应回来才一起显示,用户会以为消息没发出去或程序卡了。
    let resolvePost!: (r: Response) => void
    const fetchMock = globalThis.fetch as ReturnType<typeof vi.fn>
    // getMockImplementation() 的联合类型含构造签名,直接调用过不了 tsc,按用法收窄
    const original = fetchMock.getMockImplementation() as (
      input: RequestInfo | URL,
      init?: RequestInit,
    ) => Promise<Response>
    fetchMock.mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input).replace('http://localhost:8000', '')
      if (path === '/chat/messages' && init?.method === 'POST') {
        return new Promise<Response>((res) => {
          resolvePost = res
        })
      }
      return original(input, init)
    })

    render(<RecordTab />)
    await sendText('午饭吃了一碗米饭')

    // POST 仍在飞行中
    expect(screen.getByText('午饭吃了一碗米饭')).toBeInTheDocument()
    expect(screen.getByText('正在解析中…')).toBeInTheDocument()

    resolvePost(
      json({
        user_message: msg('user', '午饭吃了一碗米饭'),
        assistant_message: msg('assistant', '大概多少克呢?'),
        intent: 'new_entry',
        outcome: 'needs_clarification',
        batch_id: null,
        items: [],
      }),
    )

    await screen.findByText('大概多少克呢?')
    expect(screen.queryByText('正在解析中…')).not.toBeInTheDocument()
    // 乐观气泡被真实消息顶替,不是两条并存
    expect(screen.getAllByText('午饭吃了一碗米饭')).toHaveLength(1)
  })

  it('发送网络失败:撤下乐观气泡,显示发送失败提示', async () => {
    render(<RecordTab />)
    const fetchMock = globalThis.fetch as ReturnType<typeof vi.fn>
    fetchMock.mockImplementationOnce(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input).replace('http://localhost:8000', '')
      if (path === '/chat/messages' && init?.method === 'POST') {
        throw new TypeError('network down')
      }
      return json([])
    })

    await sendText('我吃了饭')
    expect(await screen.findByRole('alert')).toHaveTextContent('发送失败,请重试')
    // 没记上的话不能留在屏幕上装作已发出(.claude/rules/frontend.md:不能伪成功)
    expect(screen.queryByText('我吃了饭')).not.toBeInTheDocument()
    expect(screen.queryByText('正在解析中…')).not.toBeInTheDocument()
  })
})
