// mock 版 /today 和 /health。
//
// /health 在演示版里**不返回 'ok'**:那会让顶栏显示「已连接后端」,而演示版根本没有
// 后端。返回 'demo',顶栏据此显示「Mock 演示模式」(App.tsx),不伪装成已连接。

import type { TodayOut } from '@/types/diet'
import { attributionDate } from './attribution'
import { resetState, storage } from './store'

/** 开场说明弹窗看过没有。和演示数据分开存:它记的是「这个人来过」,不是业务数据。 */
const INTRO_KEY = 'dietapp-demo-intro-v1'

/** GET /today */
export async function fetchToday(): Promise<TodayOut> {
  return { date: attributionDate() }
}

/** GET /health */
export async function checkHealth(): Promise<'demo'> {
  return 'demo'
}

export function hasSeenDemoIntro(): boolean {
  try {
    return storage()?.getItem(INTRO_KEY) === '1'
  } catch {
    // 读不到就当没看过。宁可多弹一次,也不能让第一次来的人错过说明
    return false
  }
}

export function markDemoIntroSeen(): void {
  try {
    storage()?.setItem(INTRO_KEY, '1')
  } catch {
    /* 存不进去(无痕模式)就每次都弹,可以接受 */
  }
}

/** 顶栏「重置」按钮:公开演示里谁都可能把数据玩乱,得给一条回到初始状态的路。
 *  连开场说明一起清掉——重置的语义是「回到第一次打开的样子」。 */
export function resetDemoData(): void {
  resetState()
  try {
    storage()?.removeItem(INTRO_KEY)
  } catch {
    /* ignore */
  }
}
