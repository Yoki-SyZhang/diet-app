// 通用二次确认对话框(1.9)。最初只服务"还有未确认项"拦截,现泛化:"是否继续上一批"
// 恢复提示、今日明细删除确认都复用同一视觉,文案按场景传入。
// 视觉说明:design.md §7 Gap——bundle 无二次确认样式,此处先行,后续统一收敛。

import { createPortal } from 'react-dom'

interface UnconfirmedGuardDialogProps {
  open: boolean
  title: string
  message: string
  confirmLabel: string
  cancelLabel: string
  onConfirm: () => void
  onCancel: () => void
}

export function UnconfirmedGuardDialog({
  open,
  title,
  message,
  confirmLabel,
  cancelLabel,
  onConfirm,
  onCancel,
}: UnconfirmedGuardDialogProps) {
  if (!open) return null

  // 弹窗必须脱离调用方自己的定位/裁剪上下文。例如删除弹窗由今日卡片触发,
  // 但遮罩应覆盖整块手机屏幕(底部 Tab 除外),不能被 .today-card-slot 限住。
  const portalTarget = document.querySelector('.device__screen') ?? document.body
  return createPortal(
    <div className="dialog-backdrop">
      <div role="alertdialog" aria-label={title} className="dialog">
        <h3 className="dialog__title">{title}</h3>
        <p className="dialog__message">{message}</p>
        <div className="dialog__actions">
          <button type="button" className="btn-ghost" onClick={onCancel}>
            {cancelLabel}
          </button>
          <button type="button" className="btn-primary" onClick={onConfirm}>
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>,
    portalTarget,
  )
}
