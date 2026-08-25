// mock 版 /today 和 /health。
//
// /health 在演示版里**不返回 'ok'**:那会让顶栏显示「已连接后端」,而演示版根本没有
// 后端。返回 'demo',顶栏据此显示「Mock 演示模式」(App.tsx),不伪装成已连接。

import type { TodayOut } from '@/types/diet'
import { attributionDate } from './attribution'
import { resetState } from './store'

/** GET /today */
export async function fetchToday(): Promise<TodayOut> {
  return { date: attributionDate() }
}

/** GET /health */
export async function checkHealth(): Promise<'demo'> {
  return 'demo'
}

/** 顶栏「重置」按钮:公开演示里谁都可能把数据玩乱,得给一条回到初始状态的路。 */
export function resetDemoData(): void {
  resetState()
}
