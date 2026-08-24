// 对话消息列表(1.9)。chat_message 是给人看的展示层;user 右对齐浅绿气泡,
// assistant 不加气泡、左侧平铺直出(读长回复时框线只是噪声)。渲染为 fragment,
// 由 RecordTab 的 chat-list 容器统一排版(解析卡片紧跟最后一条 assistant 文本)。
// 类名保留 .bubble.assistant/.bubble.user:冒烟驱动和测试按它选元素,别改名。

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
