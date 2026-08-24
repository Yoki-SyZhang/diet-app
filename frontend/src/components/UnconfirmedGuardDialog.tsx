// 通用二次确认对话框(1.9)。最初只服务"还有未确认项"拦截,现泛化:"是否继续上一批"
// 恢复提示、今日明细删除确认都复用同一视觉,文案按场景传入。
// 视觉说明:design.md §7 Gap——bundle 无二次确认样式,此处先行,后续统一收敛。

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
  return (
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
    </div>
  )
}
