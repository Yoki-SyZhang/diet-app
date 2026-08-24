// 今日明细单行(1.9)。缺失营养素显示"—"不是 0(AGENTS.md 铁律);LLM 估算来源带
// "估"警示徽标(design.md §2:警示徽标必配"可能不准"语义,行内空间有限用缩写,
// 完整文案在解析卡片阶段已展示)。删除按钮在有未处理完的解析卡片时禁用。

import type { MealEntryOut } from '@/types/diet'

function fmt(value: number | null): string {
  return value === null ? '—' : String(Math.round(value * 10) / 10)
}

interface MealEntryRowProps {
  entry: MealEntryOut
  disabled: boolean
  onDeleteRequest: (entryId: number) => void
}

export function MealEntryRow({ entry, disabled, onDeleteRequest }: MealEntryRowProps) {
  const isEstimate =
    entry.source_tag === 'llm_estimate' || entry.source_tag === 'decompose_estimate'
  return (
    <div className="entry-grid entry-row">
      <span className="entry-name">
        {entry.food_name}
        {isEstimate && <i className="badge-est">估</i>}
      </span>
      <span className="entry-num">
        {entry.quantity}
        {entry.unit}
      </span>
      <span className="entry-num entry-kcal">{fmt(entry.kcal)}</span>
      <span className="entry-num">{fmt(entry.carb_g)}</span>
      <span className="entry-num">{fmt(entry.protein_g)}</span>
      <span className="entry-num">{fmt(entry.fat_g)}</span>
      <span className="entry-num">{fmt(entry.fiber_g)}</span>
      <button
        type="button"
        className="entry-delete"
        aria-label={`删除 ${entry.food_name}`}
        disabled={disabled}
        onClick={() => onDeleteRequest(entry.id)}
      >
        ✕
      </button>
    </div>
  )
}
