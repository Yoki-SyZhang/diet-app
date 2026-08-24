// 今日明细卡片(1.9,对照原型):顶部摄入/目标/Δ(目标/Δ 依赖 1.11/1.12,暂"—"
// 占位)、列头、四个固定餐次分组(展开/收起,空分组浅色不可点)、行删除(二次确认;
// 有未处理完的解析卡片时 disabled)。分组小计对 null 营养素跳过,全 null 显示"—",
// 不用 0 顶替(AGENTS.md 铁律)。

import { useState } from 'react'
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
  const [collapsed, setCollapsed] = useState<Partial<Record<MealSlot, boolean>>>({})
  const [deleteTarget, setDeleteTarget] = useState<MealEntryOut | null>(null)

  const intakeTotal = sumField(entries, 'kcal')

  return (
    <section className="today-card" aria-label="今日明细">
      <div className="intake-header">
        <span className="intake-value">{intakeTotal === null ? '—' : Math.round(intakeTotal)}</span>
        <span className="intake-target">/ — kcal 目标</span>
        <span className="intake-delta">今日 Δ —</span>
      </div>
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
          const isOpen = !isEmpty && !collapsed[slot]
          return (
            <div key={slot}>
              <button
                type="button"
                className={`entry-grid group-head${isEmpty ? ' is-empty' : ''}`}
                disabled={isEmpty}
                aria-expanded={isOpen}
                onClick={() => setCollapsed((prev) => ({ ...prev, [slot]: !prev[slot] }))}
              >
                <span className="group-label">
                  <span className={`group-caret${isOpen ? ' is-open' : ''}`} />
                  {MEAL_SLOT_LABELS[slot]}
                </span>
                <span className="group-count entry-num">
                  {isEmpty ? '未记录' : `${slotEntries.length} 条`}
                </span>
                <span className="group-num entry-num">{fmtSum(sumField(slotEntries, 'kcal'))}</span>
                <span className="group-num entry-num">{fmtSum(sumField(slotEntries, 'carb_g'))}</span>
                <span className="group-num entry-num">
                  {fmtSum(sumField(slotEntries, 'protein_g'))}
                </span>
                <span className="group-num entry-num">{fmtSum(sumField(slotEntries, 'fat_g'))}</span>
                <span className="group-num entry-num">
                  {fmtSum(sumField(slotEntries, 'fiber_g'))}
                </span>
                <span />
              </button>
              {isOpen &&
                slotEntries.map((entry) => (
                  <MealEntryRow
                    key={entry.id}
                    entry={entry}
                    disabled={disabled}
                    onDeleteRequest={() => setDeleteTarget(entry)}
                  />
                ))}
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
    </section>
  )
}
