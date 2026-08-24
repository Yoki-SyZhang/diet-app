// 底部常驻胶囊输入条(1.9,design.md §5:记录页唯一主要录入入口)。
// 修改模式(modifyingItem 非空)下:顶部灰色小字提示"修改:XX…",发送按钮变
// "确认修改"——此时发送是纯本地暂存(RecordTab 处理),不发网络请求。

import { useState } from 'react'
import type { PendingItem } from '@/types/diet'

interface ChatInputBarProps {
  modifyingItem: PendingItem | null
  disabled?: boolean
  onSend: (text: string) => void
}

export function ChatInputBar({ modifyingItem, disabled = false, onSend }: ChatInputBarProps) {
  const [text, setText] = useState('')

  const submit = () => {
    const trimmed = text.trim()
    if (!trimmed || disabled) return
    onSend(trimmed)
    setText('')
  }

  const modifyTarget =
    modifyingItem?.outcome.preview?.food_name ?? modifyingItem?.outcome.parsed_item.food_name

  return (
    <div className="input-bar">
      {modifyingItem && (
        <div className="input-bar__modify-hint">修改:{modifyTarget}(说说怎么改,发送后暂存)</div>
      )}
      <div className="input-bar__capsule">
        <input
          className="input-bar__field"
          placeholder={modifyingItem ? '比如:改成200g / 其实是蛋炒饭' : '描述你吃了什么…'}
          value={text}
          disabled={disabled}
          onChange={(event) => setText(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter') submit()
          }}
        />
        <button type="button" className="input-bar__send" disabled={disabled} onClick={submit}>
          {modifyingItem ? '确认修改' : '发送'}
        </button>
      </div>
    </div>
  )
}
