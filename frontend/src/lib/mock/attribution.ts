// mock 后端的时钟。
//
// AGENTS.md 铁律「前端不自己算归属日」约束的是**前端**:真实链路里归属日只有
// backend/app/services/attribution.py 一份定义。这里是 mock **后端**——它顶替的正是
// 那个文件,所以必须自己算,否则演示版没有归属日概念。规则照抄 SPEC §6.1:
// 归属日 B = date(本地时间 − 2h),时间戳一律 UTC-0。
//
// 时区取访问者浏览器的本地时区(演示版没有 settings.user_timezone 可读),
// 这也是演示语义上正确的:每个访问者看自己那一天。

const OFFSET_HOURS = 2

/** 归属日 ISO 字符串,对应 attribution_date()。 */
export function attributionDate(now: Date = new Date()): string {
  const shifted = new Date(now.getTime() - OFFSET_HOURS * 3600 * 1000)
  // 用本地时间取年月日:toISOString() 是 UTC,在东八区会把凌晨算成前一天
  const year = shifted.getFullYear()
  const month = String(shifted.getMonth() + 1).padStart(2, '0')
  const day = String(shifted.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

/** created_at 用的 UTC-0 ISO8601,对应 utc_now_iso()。 */
export function utcNowIso(now: Date = new Date()): string {
  return now.toISOString()
}

/** 模拟 LLM 往返耗时,让「正在解析中…」能真的被看见(真实链路要好几秒)。
 *  这只是给人看的观感,测试里没有意义,白等还会把套件拖慢十几秒——所以跳过。 */
export function fakeLatency(ms: number): Promise<void> {
  if (import.meta.env.MODE === 'test') return Promise.resolve()
  return new Promise((resolve) => setTimeout(resolve, ms))
}
