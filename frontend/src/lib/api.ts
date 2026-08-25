// vercel-display 专属:组件唯一的数据入口。
//
// 为什么多这一层——演示分支要能长期跟着业务分支走,所以正式 API 模块
// (`lib/{chat,health,mealEntries,today}.ts`)在这个分支上**一个字都没改**,
// rebase 到业务分支时它们永远是零冲突的。切换只发生在这里:
//
//   isDemoMode(构建时常量)= false → 正式 HTTP 实现,行为和业务分支完全一致
//                          = true  → lib/mock/*,不发任何网络请求
//
// 因为 isDemoMode 在构建时就折叠成字面量,production 打包会把没选中的那一支整个
// 摇掉——mock 构建里不含 fetch 调用,也不含 localhost:8000 这个串。

import { isDemoMode } from './dataSource'

import {
  fetchOpenBatch as httpFetchOpenBatch,
  fetchTodayMessages as httpFetchTodayMessages,
  sendChatMessage as httpSendChatMessage,
  sendModifyCorrection as httpSendModifyCorrection,
  sendRecap as httpSendRecap,
} from './chat'
import { checkHealth as httpCheckHealth, type HealthStatus } from './health'
import {
  confirmMealEntry as httpConfirmMealEntry,
  deleteMealEntry as httpDeleteMealEntry,
  fetchTodayEntries as httpFetchTodayEntries,
} from './mealEntries'
import { fetchToday as httpFetchToday } from './today'

import {
  fetchOpenBatch as mockFetchOpenBatch,
  fetchTodayMessages as mockFetchTodayMessages,
  sendChatMessage as mockSendChatMessage,
  sendModifyCorrection as mockSendModifyCorrection,
  sendRecap as mockSendRecap,
} from './mock/chat'
import {
  confirmMealEntry as mockConfirmMealEntry,
  deleteMealEntry as mockDeleteMealEntry,
  fetchTodayEntries as mockFetchTodayEntries,
} from './mock/mealEntries'
import {
  checkHealth as mockCheckHealth,
  fetchToday as mockFetchToday,
  resetDemoData as mockResetDemoData,
} from './mock/system'

/** 比正式 HealthStatus 多一个 'demo':演示版没有后端可连,顶栏得说实话。 */
export type AppHealthStatus = HealthStatus | 'demo'

// chat
export const sendChatMessage = isDemoMode ? mockSendChatMessage : httpSendChatMessage
export const sendModifyCorrection = isDemoMode ? mockSendModifyCorrection : httpSendModifyCorrection
export const sendRecap = isDemoMode ? mockSendRecap : httpSendRecap
export const fetchTodayMessages = isDemoMode ? mockFetchTodayMessages : httpFetchTodayMessages
export const fetchOpenBatch = isDemoMode ? mockFetchOpenBatch : httpFetchOpenBatch

// meal entries
export const confirmMealEntry = isDemoMode ? mockConfirmMealEntry : httpConfirmMealEntry
export const fetchTodayEntries = isDemoMode ? mockFetchTodayEntries : httpFetchTodayEntries
export const deleteMealEntry = isDemoMode ? mockDeleteMealEntry : httpDeleteMealEntry

// today / health
export const fetchToday = isDemoMode ? mockFetchToday : httpFetchToday
export const checkHealth: () => Promise<AppHealthStatus> = isDemoMode
  ? mockCheckHealth
  : httpCheckHealth

/** 只有演示模式有意义;真实模式下是 no-op(那边的数据在 SQLite 里,不归前端清)。 */
export const resetDemoData = isDemoMode ? mockResetDemoData : () => {}
