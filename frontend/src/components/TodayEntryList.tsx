// 今日明细卡片(1.9,对照原型):顶部摄入/目标/Δ(目标/Δ 依赖 1.11/1.12,暂"—"
// 占位)、列头、四个固定餐次分组、行删除(二次确认;有未处理完的解析卡片时
// disabled)。分组小计对 null 营养素跳过,全 null 显示"—",不用 0 顶替(AGENTS.md 铁律)。
//
// 展开/收起(两级,纯点击控制,跟滚动无关):
// - 进入页面恒定全收起,只看得到每餐小计;
// - 点顶部摄入区 = 全部展开 / 全部收起;点某一餐的小计行 = 只开这一餐;
// - 展开出来的部分**盖在聊天上**,不把聊天挤下去(见 .today-card-slot 的高度钉法),
//   所以对话的滚动位置和最后一条消息的位置在展开前后完全不动。

import { useLayoutEffect, useRef, useState } from 'react'
import type { MealEntryOut, MealSlot } from '@/types/diet'
import { MEAL_SLOT_LABELS } from '@/types/diet'
import { MealEntryRow } from '@/components/MealEntryRow'
import { UnconfirmedGuardDialog } from '@/components/UnconfirmedGuardDialog'

const SLOT_ORDER: MealSlot[] = ['breakfast', 'lunch', 'dinner', 'other']

function sumField(
  entries: MealEntryOut[],
  field: 'kcal' | 'carb_g' | 'protein_g' | 'fat_g' | 'fiber_g',
): number | null {
  const values = entries.map((e) => e[field]).filter((v): v is number => v !== null)
  if (values.length === 0) return null
  return values.reduce((a, b) => a + b, 0)
}

function fmtSum(value: number | null): string {
  return value === null ? '—' : String(Math.round(value))
}

interface TodayEntryListProps {
  entries: MealEntryOut[]
  /** 存在未结束的解析卡片时为 true:所有删除按钮禁用,防止两块界面同时改数据 */
  disabled: boolean
  onDelete: (entryId: number) => void
  deleteError?: string | null
}

export function TodayEntryList({ entries, disabled, onDelete, deleteError }: TodayEntryListProps) {
  const [expanded, setExpanded] = useState<Partial<Record<MealSlot, boolean>>>({})
  const [deleteTarget, setDeleteTarget] = useState<MealEntryOut | null>(null)
  const slotRef = useRef<HTMLDivElement>(null)
  const cardRef = useRef<HTMLElement>(null)

  const intakeTotal = sumField(entries, 'kcal')
  const anyOpen = SLOT_ORDER.some((slot) => expanded[slot])

  // 把"折叠高度"量出来给外框当上限:卡片展开后超出的部分就溢出显示、盖住聊天,
  // 而外框在流里始终只占折叠时那么高,所以聊天不会被顶下去。
  // 折叠高度 = 卡片高 − 所有明细行容器的高度 —— 这个式子在展开/收起动画的任意
  // 一帧都成立,不必等动画结束再量(等的话会量到中间态,上限就偏大了)。
  useLayoutEffect(() => {
    const card = cardRef.current
    const slot = slotRef.current
    if (!card || !slot) return
    let rows = 0
    for (const element of card.querySelectorAll<HTMLElement>('.entry-group__rows')) {
      rows += element.offsetHeight
    }
    slot.style.setProperty('--card-collapsed-h', `${Math.round(card.offsetHeight - rows)}px`)
  })

  const toggleAll = () => {
    if (anyOpen) {
      setExpanded({})
      return
    }
    const next: Partial<Record<MealSlot, boolean>> = {}
    for (const slot of SLOT_ORDER) {
      if (entries.some((entry) => entry.meal_slot === slot)) next[slot] = true
    }
    setExpanded(next)
  }

  return (
    <div className="today-card-slot" ref={slotRef}>
      {/* 这层的高度 = 卡片真实高度(外框被钉住了量不到),卡片下沿那道渐隐挂在它身上 */}
      <div className="today-card-float">
        <section className="today-card" aria-label="今日明细" ref={cardRef}>
          <button
            type="button"
            className="intake-header"
            aria-expanded={anyOpen}
            aria-label={anyOpen ? '收起全部明细' : '展开全部明细'}
            disabled={entries.length === 0}
            onClick={toggleAll}
          >
            <span className="intake-value">
              {intakeTotal === null ? '—' : Math.round(intakeTotal)}
            </span>
            <span className="intake-target">/ — kcal 目标</span>
            <span className="intake-delta">今日 Δ —</span>
            <span className={`intake-caret${anyOpen ? ' is-open' : ''}`} aria-hidden="true" />
          </button>
          <div className="entry-table">
            <div className="entry-grid entry-grid-header">
              <span>食物</span>
              <span>数量</span>
              <span>kcal</span>
              <span>碳</span>
              <span>蛋</span>
              <span>脂</span>
              <span>纤</span>
              <span />
            </div>
            {SLOT_ORDER.map((slot) => {
              const slotEntries = entries.filter((e) => e.meal_slot === slot)
              const isEmpty = slotEntries.length === 0
              const isOpen = !isEmpty && !!expanded[slot]
              return (
                <div key={slot}>
                  <button
                    type="button"
                    className={`entry-grid group-head${isEmpty ? ' is-empty' : ''}`}
                    disabled={isEmpty}
                    aria-expanded={isOpen}
                    onClick={() => setExpanded((prev) => ({ ...prev, [slot]: !prev[slot] }))}
                  >
                    <span className="group-label">
                      <span className={`group-caret${isOpen ? ' is-open' : ''}`} />
                      {MEAL_SLOT_LABELS[slot]}
                    </span>
                    <span className="group-count entry-num">
                      {isEmpty ? '未记录' : `${slotEntries.length} 条`}
                    </span>
                    <span className="group-num entry-num">
                      {fmtSum(sumField(slotEntries, 'kcal'))}
                    </span>
                    <span className="group-num entry-num">
                      {fmtSum(sumField(slotEntries, 'carb_g'))}
                    </span>
                    <span className="group-num entry-num">
                      {fmtSum(sumField(slotEntries, 'protein_g'))}
                    </span>
                    <span className="group-num entry-num">
                      {fmtSum(sumField(slotEntries, 'fat_g'))}
                    </span>
                    <span className="group-num entry-num">
                      {fmtSum(sumField(slotEntries, 'fiber_g'))}
                    </span>
                    <span />
                  </button>
                  {/* 明细行常驻 DOM、靠 CSS(0fr↔1fr)收放,收起时高度为 0。不用
                      {isOpen && ...} 条件渲染是因为那样没法做展开动画——元素是直接
                      以终态挂上去的。分组小计在 group-head 上,不受收放影响。 */}
                  <div className="entry-group__rows" data-open={isOpen}>
                    <div className="entry-group__rows-inner">
                      {slotEntries.map((entry) => (
                        <MealEntryRow
                          key={entry.id}
                          entry={entry}
                          disabled={disabled}
                          onDeleteRequest={() => setDeleteTarget(entry)}
                        />
                      ))}
                    </div>
                  </div>
                </div>
              )
            })}
            {entries.length === 0 && <div className="entry-empty-text">今天还没有记录</div>}
            {deleteError && (
              <div className="confirm-item__error" role="alert">
                {deleteError}
              </div>
            )}
          </div>
        </section>
      </div>
      {/* 删除确认框放在卡片外面:卡片是裁剪容器(展开时要溢出盖住聊天),
          放里面遮罩就只会盖住卡片自己那一小块。 */}
      <UnconfirmedGuardDialog
        open={deleteTarget !== null}
        title="确定删除?"
        message={
          deleteTarget
            ? `将从今日明细中删除「${deleteTarget.food_name} ${deleteTarget.quantity}${deleteTarget.unit}」,删除后不可恢复。`
            : ''
        }
        confirmLabel="删除"
        cancelLabel="取消"
        onConfirm={() => {
          if (deleteTarget) onDelete(deleteTarget.id)
          setDeleteTarget(null)
        }}
        onCancel={() => setDeleteTarget(null)}
      />
    </div>
  )
}
