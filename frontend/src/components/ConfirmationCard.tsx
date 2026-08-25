// 解析结果卡片(1.9,tasks/current.md"每样食物的状态机")。
//
// 关键语义:单项"确认"/"修改"只是本地暂存/意图标记,不产生任何网络请求;真正写库/
// 触发重新估算/放弃的决定者是顶部"确认"/"放弃"两个按钮。confirmed 是卡片内终态,
// 不再有按钮(想撤销去今日明细删行);abandoned 项不渲染。

import type { PendingItem } from '@/types/diet'
import { MEAL_SLOT_LABELS, PREP_STATE_LABELS } from '@/types/diet'
import { isDemoMode } from '@/lib/dataSource'

// vercel-display:演示版没有真发生过网络估算,这行小字不能照写「网络估算」
// (只有顶栏的「Mock 演示模式」还不够——这里是逐项声明数据是哪来的)。
const SOURCE_BADGE = isDemoMode ? '演示估算 · 可能不准' : '网络估算 · 可能不准'

function fmt(value: number | null | undefined): string {
  return value === null || value === undefined ? '—' : String(Math.round(value * 10) / 10)
}

interface ConfirmationCardProps {
  items: PendingItem[]
  cardBusy: boolean
  onToggleConfirm: (clientItemId: string) => void
  onToggleModify: (clientItemId: string) => void
  onTopConfirm: () => void
  onTopAbandon: () => void
}

export function ConfirmationCard({
  items,
  cardBusy,
  onToggleConfirm,
  onToggleModify,
  onTopConfirm,
  onTopAbandon,
}: ConfirmationCardProps) {
  const visible = items.filter((item) => item.uiState !== 'abandoned')
  if (visible.length === 0) return null

  const mealSlot = visible[0].outcome.preview?.meal_slot ?? 'other'
  // kcal 合计只算 confirmed/to_confirm 的预估值(tasks/current.md)
  const kcalTotal = visible
    .filter((item) => item.uiState === 'confirmed' || item.uiState === 'to_confirm')
    .reduce((sum, item) => sum + (item.outcome.preview?.nutrients.kcal ?? 0), 0)

  return (
    <section className="confirm-card" aria-label="解析结果卡片">
      <div className="confirm-card__header">
        <div className="confirm-card__title">
          <span className="confirm-card__kicker">解析结果 · {MEAL_SLOT_LABELS[mealSlot]}</span>
          <span className="confirm-card__kcal">
            {Math.round(kcalTotal)} <small>kcal</small>
          </span>
        </div>
        <div className="confirm-card__actions">
          <button
            type="button"
            className="btn-ghost"
            disabled={cardBusy}
            onClick={onTopAbandon}
          >
            放弃
          </button>
          <button
            type="button"
            className="btn-primary"
            disabled={cardBusy}
            onClick={onTopConfirm}
          >
            确认
          </button>
        </div>
      </div>
      <div>
        {visible.map((item) => {
          const preview = item.outcome.preview
          const parsed = item.outcome.parsed_item
          const terminal = item.uiState === 'confirmed'
          const modifying = item.uiState === 'modifying'
          return (
            <div key={item.clientItemId} className="confirm-item">
              <div className="confirm-item__main">
                <span className="confirm-item__name">{preview?.food_name ?? parsed.food_name}</span>
                <span className="confirm-item__qty">
                  {PREP_STATE_LABELS[parsed.preparation_state]} {preview?.quantity ?? parsed.quantity}g
                </span>
                <span className="confirm-item__badge">{SOURCE_BADGE}</span>
                <span className="confirm-item__spacer" />
                <span className="confirm-item__kcal">{fmt(preview?.nutrients.kcal)}</span>
                <span className="confirm-item__unit">kcal</span>
              </div>
              <div className="confirm-item__sub">
                <span className="confirm-item__per100">
                  碳 {fmt(preview?.nutrients.carb_g)} / 蛋 {fmt(preview?.nutrients.protein_g)} / 脂{' '}
                  {fmt(preview?.nutrients.fat_g)} / 纤 {fmt(preview?.nutrients.fiber_g)}
                </span>
                {terminal ? (
                  <span className="confirm-item__done">已写入</span>
                ) : modifying ? (
                  <span className="confirm-item__done">重新估算中…</span>
                ) : (
                  <>
                    <button
                      type="button"
                      className={`btn-toggle${
                        item.uiState === 'to_modify' || item.uiState === 'to_reparse'
                          ? ' is-on'
                          : ''
                      }`}
                      disabled={cardBusy}
                      onClick={() => onToggleModify(item.clientItemId)}
                    >
                      修改
                    </button>
                    <button
                      type="button"
                      className={`btn-toggle${item.uiState === 'to_confirm' ? ' is-on' : ''}`}
                      disabled={cardBusy}
                      onClick={() => onToggleConfirm(item.clientItemId)}
                    >
                      确认
                    </button>
                  </>
                )}
              </div>
              {item.writeError && <div className="confirm-item__error">{item.writeError}</div>}
              {item.modifyError ? (
                <div className="confirm-item__error">{item.modifyError}</div>
              ) : (
                item.pendingModifyNote && (
                  <div className="confirm-item__note">
                    修改:{item.pendingModifyNote.slice(0, 10)}
                    {item.pendingModifyNote.length > 10 ? '…' : ''}
                  </div>
                )
              )}
            </div>
          )
        })}
      </div>
    </section>
  )
}
