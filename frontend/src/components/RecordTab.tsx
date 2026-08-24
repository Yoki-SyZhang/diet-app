// 记录页(1.9,tasks/current.md"五、前端组件实现")。状态机归属地:
//
// - 单项"确认"/"修改"/输入框"确认修改"都是本地暂存,不发网络请求;
// - 真正对外的动作只发生在卡片顶部"确认"(批量写入 + 批量重新估算,共用同一个
//   now_utc)和"放弃"(本地标 abandoned);
// - 所有项到达 confirmed/abandoned 终态 → 立刻本地解锁,再发一次性 recap(失败就
//   放弃,不重试、不阻塞 UI);
// - 挂载时查 open-batch,有未完成批次弹"继续/放弃"对话框;
// - 存在未结束卡片时:今日明细删除禁用;输入框直接打字被"未确认放弃"弹窗拦截;
// - 发送后先挂乐观用户气泡 + "正在解析中…",拿到回执再用真实消息替换。

import { useCallback, useEffect, useRef, useState } from 'react'
import type {
  BatchItemStatus,
  ChatMessageOut,
  ConfirmableItem,
  ItemUiState,
  MealEntryOut,
  OpenBatchOut,
  PendingItem,
} from '@/types/diet'
import { TERMINAL_STATES } from '@/types/diet'
import {
  fetchOpenBatch,
  fetchTodayMessages,
  sendChatMessage,
  sendModifyCorrection,
  sendRecap,
} from '@/lib/chat'
import { confirmMealEntry, deleteMealEntry, fetchTodayEntries } from '@/lib/mealEntries'
import { ChatHistory } from '@/components/ChatHistory'
import { ChatInputBar } from '@/components/ChatInputBar'
import { ConfirmationCard } from '@/components/ConfirmationCard'
import { TodayEntryList } from '@/components/TodayEntryList'
import { UnconfirmedGuardDialog } from '@/components/UnconfirmedGuardDialog'

type GuardState =
  | { kind: 'unconfirmed'; text: string }
  | { kind: 'resume'; batch: OpenBatchOut }

/** 还没拿到服务端回执的用户消息(乐观气泡)。解析要等 LLM 好几秒,这期间必须先把
 *  用户自己说的话显示出来,否则看起来像没发出去。key 只用于 React 列表和撤下。 */
interface OptimisticSend {
  key: string
  text: string
}

function toPendingItem(item: ConfirmableItem): PendingItem {
  return {
    clientItemId: item.confirmation_id,
    confirmationId: item.confirmation_id,
    outcome: item.outcome,
    uiState: 'pending',
    writtenEntryId: null,
    pendingModifyNote: null,
    modifyError: null,
    writeError: null,
  }
}

function isTerminal(state: ItemUiState): boolean {
  return TERMINAL_STATES.has(state)
}

/** 按 id 去重合并消息。挂载时的"拉今日消息"GET 可能在一次 POST 处理到一半时被
 * 后端受理(POST 等 LLM 的几秒里),返回的列表已经含有刚写入的那条用户消息——
 * 这时再裸 append POST 响应就会出现重复气泡,所以所有消息更新都走这里合并。 */
function mergeMessages(
  prev: ChatMessageOut[],
  incoming: ChatMessageOut[],
): ChatMessageOut[] {
  const byId = new Map<number, ChatMessageOut>()
  for (const message of prev) byId.set(message.id, message)
  for (const message of incoming) byId.set(message.id, message)
  return [...byId.values()].sort((a, b) => a.id - b.id)
}

export function RecordTab() {
  const [messages, setMessages] = useState<ChatMessageOut[]>([])
  const [optimistic, setOptimistic] = useState<OptimisticSend[]>([])
  const [entries, setEntries] = useState<MealEntryOut[]>([])
  const [pendingItems, setPendingItems] = useState<PendingItem[]>([])
  const [batchId, setBatchId] = useState<string | null>(null)
  const [modifyingItemId, setModifyingItemId] = useState<string | null>(null)
  const [cardBusy, setCardBusy] = useState(false)
  const [sendBusy, setSendBusy] = useState(false)
  const [sendError, setSendError] = useState<string | null>(null)
  const [deleteError, setDeleteError] = useState<string | null>(null)
  const [guard, setGuard] = useState<GuardState | null>(null)
  // 同一张卡片生命周期里 recap 只发一次(值=已发送 recap 的 batchId)
  const recapSentRef = useRef<string | null>(null)
  const scrollRef = useRef<HTMLDivElement>(null)

  const hasOpenCard = pendingItems.some((item) => !isTerminal(item.uiState))

  /** 收下服务端消息,并撤掉已被真实消息覆盖的乐观气泡(同内容即同一条)。
   *  不能只靠"POST 返回时撤":挂载的今日消息 GET 可能先一步带回这条用户消息,
   *  那时就得立刻撤,否则同一句话会并排出现两次。 */
  const applyIncoming = useCallback((incoming: ChatMessageOut[]) => {
    setMessages((prev) => mergeMessages(prev, incoming))
    const settled = incoming.filter((message) => message.role === 'user').map((m) => m.content)
    if (settled.length === 0) return
    setOptimistic((prev) =>
      prev.filter((item) => {
        const at = settled.indexOf(item.text)
        if (at === -1) return true
        settled.splice(at, 1) // 同内容只抵消一条,连发两句一样的话不会多撤
        return false
      }),
    )
  }, [])

  useEffect(() => {
    let cancelled = false
    fetchTodayMessages()
      .then((data) => !cancelled && applyIncoming(data))
      .catch(() => {})
    fetchTodayEntries()
      .then((data) => !cancelled && setEntries(data))
      .catch(() => {})
    fetchOpenBatch()
      .then((batch) => {
        if (batch && batch.items.length > 0 && !cancelled) {
          setGuard({ kind: 'resume', batch })
        }
      })
      .catch(() => {})
    return () => {
      cancelled = true
    }
  }, [applyIncoming])

  // 新消息/新卡片出现后把对话滚到底。屏幕高度固定(手机外框),不主动滚就会出现
  // "AI 已经答了但看不见"。用 scrollTop 赋值而不是 scrollTo:jsdom 里也能跑。
  useEffect(() => {
    const element = scrollRef.current
    if (element) element.scrollTop = element.scrollHeight
  }, [messages, optimistic, pendingItems, sendBusy])

  /** 全部到终态 → 清卡片(立刻解锁)+ 发一次性 recap(不等网络结果,不重试)。 */
  const finalizeBatchIfDone = useCallback(
    (items: PendingItem[], currentBatchId: string | null, nowUtc?: string) => {
      if (!currentBatchId || items.length === 0) return
      if (items.some((item) => !isTerminal(item.uiState))) return

      setPendingItems([])
      setBatchId(null)
      setModifyingItemId(null)

      if (recapSentRef.current === currentBatchId) return
      recapSentRef.current = currentBatchId

      const statuses: BatchItemStatus[] = items.map((item) => {
        const confirmed = item.uiState === 'confirmed'
        return {
          food_name: item.outcome.preview?.food_name ?? item.outcome.parsed_item.food_name,
          quantity: item.outcome.preview?.quantity ?? item.outcome.parsed_item.quantity,
          state: confirmed ? 'confirmed' : 'abandoned',
          kcal: confirmed ? (item.outcome.preview?.nutrients.kcal ?? null) : null,
        }
      })
      sendRecap({
        batch_id: currentBatchId,
        meal_slot: items[0].outcome.preview?.meal_slot ?? 'other',
        items: statuses,
        now_utc: nowUtc ?? new Date().toISOString(),
      })
        .then((resp) =>
          setMessages((prev) => mergeMessages(prev, [resp.assistant_message])),
        )
        .catch(() => {})
    },
    [],
  )

  const doSend = useCallback(
    async (text: string) => {
      // 先上屏再发请求:用户气泡不等 LLM,顺序跟人的预期一致(说完就看见自己说的)
      const key = `local-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
      setOptimistic((prev) => [...prev, { key, text }])
      setSendBusy(true)
      setSendError(null)
      try {
        const resp = await sendChatMessage(text)
        applyIncoming([resp.user_message, resp.assistant_message])
        if (resp.batch_id && resp.items.length > 0) {
          recapSentRef.current = null
          setBatchId(resp.batch_id)
          setPendingItems(resp.items.map(toPendingItem))
        }
      } catch {
        setSendError('发送失败,请重试')
      } finally {
        // 成功时真实消息已经顶上,失败时这条也不该留在屏幕上假装发出去了
        setOptimistic((prev) => prev.filter((item) => item.key !== key))
        setSendBusy(false)
      }
    },
    [applyIncoming],
  )

  /** 输入框发送的三条路由规则(tasks/current.md"输入框直接打字时的判断")。 */
  const handleSend = (text: string) => {
    if (modifyingItemId !== null) {
      // 修改模式:纯本地暂存修正文本,不发请求
      setPendingItems((prev) =>
        prev.map((item) =>
          item.clientItemId === modifyingItemId
            ? { ...item, uiState: 'to_reparse', pendingModifyNote: text, modifyError: null }
            : item,
        ),
      )
      setModifyingItemId(null)
      return
    }
    if (hasOpenCard) {
      setGuard({ kind: 'unconfirmed', text })
      return
    }
    void doSend(text)
  }

  const handleToggleConfirm = (clientItemId: string) => {
    if (cardBusy) return
    setPendingItems((prev) =>
      prev.map((item) => {
        if (item.clientItemId !== clientItemId) return item
        if (item.uiState === 'pending') return { ...item, uiState: 'to_confirm' }
        if (item.uiState === 'to_confirm') return { ...item, uiState: 'pending' }
        return item
      }),
    )
  }

  const handleToggleModify = (clientItemId: string) => {
    if (cardBusy) return
    const target = pendingItems.find((item) => item.clientItemId === clientItemId)
    if (!target) return
    if (target.uiState === 'pending') {
      // 同时只允许一项处于 to_modify:切换目标时旧的退回 pending
      setPendingItems((prev) =>
        prev.map((item) => {
          if (item.clientItemId === clientItemId) return { ...item, uiState: 'to_modify' }
          if (item.uiState === 'to_modify') return { ...item, uiState: 'pending' }
          return item
        }),
      )
      setModifyingItemId(clientItemId)
      return
    }
    if (target.uiState === 'to_modify' || target.uiState === 'to_reparse') {
      // 取消:丢弃还没发的修改草稿,退回待处理
      setPendingItems((prev) =>
        prev.map((item) =>
          item.clientItemId === clientItemId
            ? { ...item, uiState: 'pending', pendingModifyNote: null }
            : item,
        ),
      )
      if (modifyingItemId === clientItemId) setModifyingItemId(null)
    }
  }

  /** 顶部"确认":批量写入 to_confirm 项 + 批量重新估算 to_reparse 项,共用同一个 now_utc。 */
  const handleTopConfirm = async () => {
    if (cardBusy || !batchId) return
    const nowUtc = new Date().toISOString()
    setCardBusy(true)
    setModifyingItemId(null)

    const working = pendingItems.map((item) =>
      item.uiState === 'to_reparse' ? { ...item, uiState: 'modifying' as ItemUiState } : item,
    )
    setPendingItems(working)

    const written: MealEntryOut[] = []
    const results = await Promise.all(
      working.map(async (item): Promise<PendingItem> => {
        if (item.uiState === 'to_confirm' && item.outcome.preview) {
          try {
            const entry = await confirmMealEntry({
              confirmation_id: item.confirmationId,
              preview: item.outcome.preview,
              now_utc: nowUtc,
            })
            written.push(entry)
            return { ...item, uiState: 'confirmed', writtenEntryId: entry.id, writeError: null }
          } catch {
            // 保留暂存态,下次顶部"确认"可重试;幂等键保证重试不会重复插入
            return { ...item, writeError: '写入失败,可重试' }
          }
        }
        if (item.uiState === 'modifying' && item.outcome.preview) {
          try {
            const resp = await sendModifyCorrection({
              confirmation_id: item.confirmationId,
              original_item: item.outcome.parsed_item,
              meal_slot: item.outcome.preview.meal_slot,
              correction_text: item.pendingModifyNote ?? '',
            })
            if (resp.success && resp.outcome) {
              // 成功:更新预览值,"修改:…"留痕保留作溯源,回到 pending 等下一次顶部确认
              return { ...item, uiState: 'pending', outcome: resp.outcome, modifyError: null }
            }
            return {
              ...item,
              uiState: 'pending',
              pendingModifyNote: null,
              modifyError: resp.failure_reason ?? '修改失败,请重新描述',
            }
          } catch {
            return {
              ...item,
              uiState: 'pending',
              pendingModifyNote: null,
              modifyError: '修改失败,请重新描述',
            }
          }
        }
        return item
      }),
    )

    if (written.length > 0) setEntries((prev) => [...prev, ...written])
    setPendingItems(results)
    setCardBusy(false)
    finalizeBatchIfDone(results, batchId, nowUtc)
  }

  /** 顶部"放弃":所有非终态项 → abandoned(纯本地)。 */
  const handleTopAbandon = () => {
    if (cardBusy || !batchId) return
    const results = pendingItems.map((item) =>
      isTerminal(item.uiState) ? item : { ...item, uiState: 'abandoned' as ItemUiState },
    )
    setModifyingItemId(null)
    setPendingItems(results)
    finalizeBatchIfDone(results, batchId)
  }

  const handleGuardConfirm = () => {
    if (!guard) return
    if (guard.kind === 'unconfirmed') {
      // "放弃并继续":残留项转 abandoned(等同顶部"放弃"),再发送新消息
      const results = pendingItems.map((item) =>
        isTerminal(item.uiState) ? item : { ...item, uiState: 'abandoned' as ItemUiState },
      )
      setModifyingItemId(null)
      setPendingItems(results)
      finalizeBatchIfDone(results, batchId)
      setGuard(null)
      void doSend(guard.text)
      return
    }
    // resume:用保存的完整预览重建卡片,复用已签发的 confirmation_id/batch_id
    recapSentRef.current = null
    setBatchId(guard.batch.batch_id)
    setPendingItems(guard.batch.items.map(toPendingItem))
    setGuard(null)
  }

  const handleGuardCancel = () => {
    if (!guard) return
    if (guard.kind === 'resume') {
      // 放弃旧批次:整批标 abandoned 发 recap,下次挂载不再提示
      const statuses: BatchItemStatus[] = guard.batch.items.map((item) => ({
        food_name: item.outcome.preview?.food_name ?? item.outcome.parsed_item.food_name,
        quantity: item.outcome.preview?.quantity ?? item.outcome.parsed_item.quantity,
        state: 'abandoned',
      }))
      sendRecap({
        batch_id: guard.batch.batch_id,
        meal_slot: guard.batch.items[0]?.outcome.preview?.meal_slot ?? 'other',
        items: statuses,
        now_utc: new Date().toISOString(),
      })
        .then((resp) =>
          setMessages((prev) => mergeMessages(prev, [resp.assistant_message])),
        )
        .catch(() => {})
    }
    setGuard(null)
  }

  const handleDelete = async (entryId: number) => {
    setDeleteError(null)
    try {
      await deleteMealEntry(entryId) // 204/404 都表示这行已经不存在
      setEntries((prev) => prev.filter((entry) => entry.id !== entryId))
    } catch {
      setDeleteError('删除失败,请重试')
    }
  }

  const modifyingItem =
    pendingItems.find((item) => item.clientItemId === modifyingItemId) ?? null
  const openItemCount = pendingItems.filter((item) => !isTerminal(item.uiState)).length

  return (
    <div className="record-tab">
      {/* 明细卡片不在滚动流里:一直钉在最上方。展开时它盖住聊天,不挤动聊天 */}
      <div className="record-tab__top">
        <TodayEntryList
          entries={entries}
          disabled={hasOpenCard}
          onDelete={handleDelete}
          deleteError={deleteError}
        />
      </div>
      <div className="record-tab__scroll" ref={scrollRef}>
        <div className="section-head">
          <h2>对话录入</h2>
          <span>对话历史保留 1 天</span>
        </div>
        <div className="chat-list">
          <ChatHistory messages={messages} />
          {optimistic.map((item) => (
            <div key={item.key} className="bubble user is-sending">
              {item.text}
            </div>
          ))}
          {sendBusy && (
            <div className="thinking" role="status">
              <span className="thinking__dot" aria-hidden="true" />
              正在解析中…
            </div>
          )}
          {pendingItems.length > 0 && (
            <ConfirmationCard
              items={pendingItems}
              cardBusy={cardBusy}
              onToggleConfirm={handleToggleConfirm}
              onToggleModify={handleToggleModify}
              onTopConfirm={() => void handleTopConfirm()}
              onTopAbandon={handleTopAbandon}
            />
          )}
          {sendError && (
            <div className="chat-error" role="alert">
              {sendError}
            </div>
          )}
        </div>
      </div>
      <ChatInputBar modifyingItem={modifyingItem} disabled={sendBusy} onSend={handleSend} />
      {guard?.kind === 'unconfirmed' && (
        <UnconfirmedGuardDialog
          open
          title="还有未确认的解析结果"
          message={`还有 ${openItemCount} 项没确认,不确认就不会被记录,确定要放弃吗?`}
          confirmLabel="放弃并继续"
          cancelLabel="返回处理"
          onConfirm={handleGuardConfirm}
          onCancel={handleGuardCancel}
        />
      )}
      {guard?.kind === 'resume' && (
        <UnconfirmedGuardDialog
          open
          title="继续上次的识别结果?"
          message={`上次有 ${guard.batch.items.length} 项识别结果没有处理完,是否继续?`}
          confirmLabel="继续"
          cancelLabel="放弃"
          onConfirm={handleGuardConfirm}
          onCancel={handleGuardCancel}
        />
      )}
    </div>
  )
}
