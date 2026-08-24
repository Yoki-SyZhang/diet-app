// 1.9 对话相关 API(backend/app/routers/chat.py)。网络失败/非 2xx 一律抛 Error,
// 由调用方(RecordTab)决定呈现方式——写入交互必须呈现明确失败态,不能伪成功
// (.claude/rules/frontend.md)。

import type {
  ChatMessageOut,
  ChatTurnResponse,
  ModifyCorrectionRequest,
  ModifyCorrectionResponse,
  OpenBatchOut,
  RecapRequest,
  RecapResponse,
} from '@/types/diet'

function baseUrl(): string {
  return import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'
}

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${baseUrl()}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  })
  if (!response.ok) {
    throw new Error(`请求失败(HTTP ${response.status})`)
  }
  return (await response.json()) as T
}

export function sendChatMessage(text: string): Promise<ChatTurnResponse> {
  return requestJson<ChatTurnResponse>('/chat/messages', {
    method: 'POST',
    body: JSON.stringify({ text }),
  })
}

export function sendModifyCorrection(
  request: ModifyCorrectionRequest,
): Promise<ModifyCorrectionResponse> {
  return requestJson<ModifyCorrectionResponse>('/chat/messages/modify', {
    method: 'POST',
    body: JSON.stringify(request),
  })
}

export function sendRecap(request: RecapRequest): Promise<RecapResponse> {
  return requestJson<RecapResponse>('/chat/messages/recap', {
    method: 'POST',
    body: JSON.stringify(request),
  })
}

export function fetchTodayMessages(): Promise<ChatMessageOut[]> {
  return requestJson<ChatMessageOut[]>('/chat/messages/today')
}

export function fetchOpenBatch(): Promise<OpenBatchOut | null> {
  return requestJson<OpenBatchOut | null>('/chat/messages/open-batch')
}
