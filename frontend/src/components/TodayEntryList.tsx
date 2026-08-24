// 今日明细卡片(1.9,对照原型):顶部摄入/目标/Δ(目标/Δ 依赖 1.11/1.12,暂"—"
// 占位)、列头、四个固定餐次分组、行删除(二次确认;有未处理完的解析卡片时
// disabled)。分组小计对 null 营养素跳过,全 null 显示"—",不用 0 顶替(AGENTS.md 铁律)。
//
// 展开/收起(两级,纯点击控制,跟滚动无关):
// - 进入页面恒定全收起,只看得到每餐小计;
// - 点顶部摄入区 = 全部展开 / 全部收起;点某一餐的小计行 = 只开这一餐;
// - 展开出来的部分**盖在聊天上**,不把聊天挤下去(见 .today-card-slot 的高度钉法),
//   所以对话的滚动位置和最后一条消息的位置在展开前后完全不动;
// - 卡片底边下方的聊天由记录页做渐隐(onOverlapChange → --chat-fade-top),不在这里画。

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

/** 顶部营养素加总。null 是"未提供"不是 0,只显示"—",不能写成"—g"(AGENTS.md 铁律)。 */
function fmtGram(value: number | null): string {
  return value === null ? '—' : `${Math.round(value)}g`
}

const WEEKDAYS = ['周日', '周一', '周二', '周三', '周四', '周五', '周六']

/** 归属日 "2026-08-15" → "8月15日 周六"。
 *
 *  必须手工拆字符串再 new Date(y, m-1, d):`new Date('2026-08-15')` 按 ES 规范
 *  当成 UTC 零点解析,在负时区(美国)取回来就是 14 号,日期会整体差一天。 */
function formatAttributionDate(iso: string): string {
  const [year, month, day] = iso.split('-').map(Number)
  if (!year || !month || !day) return iso
  const weekday = WEEKDAYS[new Date(year, month - 1, day).getDay()]
  return `${month}月${day}日 ${weekday}`
}

const MACROS = [
  { key: 'carb_g', label: '碳水', dot: 'carb' },
  { key: 'protein_g', label: '蛋白', dot: 'protein' },
  { key: 'fat_g', label: '脂肪', dot: 'fat' },
  { key: 'fiber_g', label: '纤维', dot: 'fiber' },
] as const

interface TodayEntryListProps {
  entries: MealEntryOut[]
  /** 存在未结束的解析卡片时为 true:所有删除按钮禁用,防止两块界面同时改数据 */
  disabled: boolean
  onDelete: (entryId: number) => void
  deleteError?: string | null
  /** 当前归属日(ISO "YYYY-MM-DD",由后端给)。null = 还没拿到,那行日期就不渲染 */
  date?: string | null
  /** 报告卡片底边探进聊天区多深(px)。记录页拿它把对话上边缘的渐隐挪到卡片底边下方,
   *  这样聊天是"从卡片底下淡出"而不是被硬切一刀。 */
  onOverlapChange?: (px: number) => void
}

export function TodayEntryList({
  entries,
  disabled,
  onDelete,
  deleteError,
  date,
  onOverlapChange,
}: TodayEntryListProps) {
  const [expanded, setExpanded] = useState<Partial<Record<MealSlot, boolean>>>({})
  const [deleteTarget, setDeleteTarget] = useState<MealEntryOut | null>(null)
  const slotRef = useRef<HTMLDivElement>(null)
  const cardRef = useRef<HTMLElement>(null)

  const intakeTotal = sumField(entries, 'kcal')
  const anyOpen = SLOT_ORDER.some((slot) => expanded[slot])

  // 一次布局量两个数,用途不同、取值方式也不同:
  //
  // 1) 折叠高度(给外框当上限)= 卡片高 − 所有明细行容器**当前帧**的高度。
  //    外框在流里始终只占折叠时那么高,卡片展开后超出的部分溢出显示、盖住聊天,
  //    聊天不会被顶下去。这个式子在动画任意一帧都成立(两项同步变,差值恒定),
  //    所以必须用当前帧的 offsetHeight;换成终态值的话动画中途外框会缩,聊天会跳。
  //
  // 2) 覆盖深度(给对话上边缘的渐隐定起点)= 展开着的那几组明细行的**终态**高度。
  //    这里要终态:渐隐起点自己带 260ms 过渡跟卡片一起滑,给它中间态就会滑两次。
  //    取 inner 的 scrollHeight 而不是 offsetHeight —— 收起时格子是 0fr,inner 盒高
  //    被压成 0,offsetHeight 读到 0;scrollHeight 读的是内容自然高,任意一帧都等于终态。
  useLayoutEffect(() => {
    const card = cardRef.current
    const slot = slotRef.current
    if (!card || !slot) return
    let rows = 0
    let overlap = 0
    for (const element of card.querySelectorAll<HTMLElement>('.entry-group__rows')) {
      rows += element.offsetHeight
      if (element.dataset.open === 'true') {
        overlap += (element.firstElementChild as HTMLElement | null)?.scrollHeight ?? 0
      }
    }
    slot.style.setProperty('--card-collapsed-h', `${Math.round(card.offsetHeight - rows)}px`)
    onOverlapChange?.(Math.round(overlap))
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
      <section className="today-card" aria-label="今日明细" ref={cardRef}>
        <button
          type="button"
          className="intake-header"
          aria-expanded={anyOpen}
          aria-label={anyOpen ? '收起全部明细' : '展开全部明细'}
          disabled={entries.length === 0}
          onClick={toggleAll}
        >
          <span className="intake-main">
            <span className="intake-kcal">
              <span className="intake-value">
                {intakeTotal === null ? '—' : Math.round(intakeTotal)}
              </span>
              <span className="intake-target">/ — kcal 目标</span>
            </span>
            {/* 四大营养素加总。设计稿这里还有一条 kcal 进度条,本次不做:
                进度要有 kcal 目标才有意义,目标属于 1.11/1.12。 */}
            <span className="intake-macros">
              {MACROS.map((macro) => (
                <span key={macro.key} className="intake-macro">
                  <i className={`intake-dot intake-dot--${macro.dot}`} aria-hidden="true" />
                  {macro.label} <b>{fmtGram(sumField(entries, macro.key))}</b>
                </span>
              ))}
            </span>
          </span>
          <span className="intake-side">
            {date && <span className="intake-date">{formatAttributionDate(date)}</span>}
            <span className="intake-delta">
              今日 Δ <b>—</b>
            </span>
          </span>
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
