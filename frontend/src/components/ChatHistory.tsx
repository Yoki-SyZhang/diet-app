// 对话气泡列表(1.9)。chat_message 是给人看的展示层;assistant 左对齐白底,
// user 右对齐浅绿底(对照原型)。渲染为 fragment,由 RecordTab 的 chat-list
// 容器统一排版(解析卡片要紧跟在最后一条 assistant 气泡后"长出来")。

import type { ChatMessageOut } from '@/types/diet'

interface ChatHistoryProps {
  messages: ChatMessageOut[]
}

export function ChatHistory({ messages }: ChatHistoryProps) {
  return (
    <>
      {messages.map((message) => (
        <div key={message.id} className={`bubble ${message.role}`}>
          {message.content}
        </div>
      ))}
    </>
  )
}
