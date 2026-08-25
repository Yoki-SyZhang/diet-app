// mock 的「食物营养表 + 自然语言解析」,顶替真实链路里的
// nl_parse.parse_diet_text() + food_estimate.estimate_items()(两次真实 LLM 调用)。
//
// 数值是常见食物每 100g 的量级,够演示用;**不是**可信营养数据,也不是
// food_base_cn/us 快照的子集——演示版不导入任何真实食物库。
// 缺失营养素写 null(AGENTS.md 铁律:绝不用 0 顶替);确定为零的写 0(比如可乐的脂肪)。

import type { MealSlot, NutrientSet, ParsedFoodItem, PreparationState } from '@/types/diet'

export interface FoodDef {
  /** 规范名,进 food_name */
  name: string
  /** 别名/口语说法,匹配用 */
  aliases?: string[]
  /** 每 100g 营养素 */
  per100: NutrientSet
  prep: PreparationState
  /** 没说数量时的默认份量(g) */
  portion: number
  /** 「一个/一只/一颗」折算克重;没有这个概念的食物留空 */
  perUnit?: number
  /** 「一碗」折算克重,默认 200 */
  perBowl?: number
}

function n(
  kcal: number | null,
  carb: number | null,
  protein: number | null,
  fat: number | null,
  fiber: number | null,
): NutrientSet {
  return { kcal, carb_g: carb, protein_g: protein, fat_g: fat, fiber_g: fiber }
}

export const FOOD_TABLE: FoodDef[] = [
  // 主食
  { name: '米饭', aliases: ['白米饭', '大米饭'], per100: n(116, 25.9, 2.6, 0.3, 0.3), prep: 'cooked', portion: 200, perBowl: 200 },
  { name: '蛋炒饭', aliases: ['炒饭'], per100: n(163, 21.0, 5.0, 6.5, 0.6), prep: 'cooked', portion: 250, perBowl: 250 },
  { name: '白粥', aliases: ['稀饭', '大米粥'], per100: n(46, 10.0, 1.1, 0.2, 0.1), prep: 'cooked', portion: 300, perBowl: 300 },
  { name: '面条', aliases: ['挂面', '拉面', '汤面'], per100: n(110, 22.0, 3.5, 0.5, 0.8), prep: 'cooked', portion: 250, perBowl: 250 },
  { name: '馒头', per100: n(223, 47.0, 7.0, 1.1, 1.3), prep: 'cooked', portion: 100, perUnit: 100 },
  { name: '包子', per100: n(227, 32.0, 8.0, 7.0, 1.5), prep: 'cooked', portion: 100, perUnit: 80 },
  { name: '饺子', aliases: ['水饺'], per100: n(240, 30.0, 9.0, 9.0, 1.4), prep: 'cooked', portion: 200, perUnit: 15 },
  { name: '全麦面包', per100: n(247, 41.0, 13.0, 3.4, 7.0), prep: 'ready_to_consume', portion: 80, perUnit: 40 },
  { name: '面包', per100: n(265, 49.0, 9.0, 3.2, 2.7), prep: 'ready_to_consume', portion: 80, perUnit: 40 },
  { name: '燕麦', aliases: ['燕麦片', '麦片'], per100: n(389, 66.3, 16.9, 6.9, 10.6), prep: 'raw', portion: 40 },
  { name: '红薯', aliases: ['地瓜', '番薯'], per100: n(86, 20.0, 1.6, 0.1, 3.0), prep: 'cooked', portion: 200, perUnit: 180 },
  { name: '土豆', aliases: ['马铃薯'], per100: n(77, 17.0, 2.0, 0.1, 2.2), prep: 'cooked', portion: 150, perUnit: 150 },
  { name: '玉米', per100: n(106, 22.8, 4.0, 1.2, 2.9), prep: 'cooked', portion: 200, perUnit: 200 },

  // 蛋白
  { name: '水煮蛋', aliases: ['白煮蛋', '煮鸡蛋'], per100: n(147, 1.1, 12.6, 10.0, null), prep: 'cooked', portion: 100, perUnit: 50 },
  { name: '鸡蛋', per100: n(144, 2.8, 13.3, 8.8, null), prep: 'cooked', portion: 100, perUnit: 50 },
  { name: '鸡胸肉', aliases: ['鸡胸'], per100: n(165, 0, 31.0, 3.6, 0), prep: 'cooked', portion: 150 },
  { name: '鸡腿', per100: n(181, 0, 24.0, 9.0, 0), prep: 'cooked', portion: 120, perUnit: 120 },
  { name: '牛肉', per100: n(250, 0, 26.0, 15.0, 0), prep: 'cooked', portion: 150 },
  { name: '猪肉', per100: n(242, 0, 27.0, 14.0, 0), prep: 'cooked', portion: 150 },
  { name: '排骨', per100: n(278, 0, 18.0, 23.0, 0), prep: 'cooked', portion: 200 },
  { name: '三文鱼', aliases: ['鲑鱼'], per100: n(208, 0, 20.0, 13.0, 0), prep: 'cooked', portion: 150 },
  { name: '虾', aliases: ['虾仁', '基围虾'], per100: n(99, 0.9, 24.0, 0.3, 0), prep: 'cooked', portion: 120, perUnit: 12 },
  { name: '豆腐', per100: n(82, 1.9, 8.1, 4.8, 0.4), prep: 'cooked', portion: 150 },

  // 蔬菜
  { name: '西兰花', aliases: ['花椰菜'], per100: n(34, 7.0, 2.8, 0.4, 2.6), prep: 'cooked', portion: 180 },
  { name: '青菜', aliases: ['小白菜', '油菜', '青梗菜'], per100: n(15, 2.2, 1.5, 0.3, 1.1), prep: 'cooked', portion: 200 },
  { name: '菠菜', per100: n(23, 3.6, 2.9, 0.4, 2.2), prep: 'cooked', portion: 200 },
  { name: '西红柿', aliases: ['番茄', '圣女果'], per100: n(18, 3.9, 0.9, 0.2, 1.2), prep: 'raw', portion: 150, perUnit: 150 },
  { name: '黄瓜', per100: n(15, 3.6, 0.7, 0.1, 0.5), prep: 'raw', portion: 150, perUnit: 150 },
  { name: '胡萝卜', per100: n(41, 9.6, 0.9, 0.2, 2.8), prep: 'cooked', portion: 100, perUnit: 100 },
  { name: '沙拉', aliases: ['蔬菜沙拉'], per100: n(45, 5.0, 1.5, 2.0, 1.8), prep: 'ready_to_consume', portion: 200 },

  // 水果 / 乳品 / 饮料
  { name: '苹果', per100: n(52, 13.8, 0.3, 0.2, 2.4), prep: 'ready_to_consume', portion: 200, perUnit: 200 },
  { name: '香蕉', per100: n(89, 22.8, 1.1, 0.3, 2.6), prep: 'ready_to_consume', portion: 120, perUnit: 120 },
  { name: '橙子', aliases: ['橘子', '桔子'], per100: n(47, 11.8, 0.9, 0.1, 2.4), prep: 'ready_to_consume', portion: 180, perUnit: 180 },
  { name: '葡萄', aliases: ['提子'], per100: n(69, 18.1, 0.7, 0.2, 0.9), prep: 'ready_to_consume', portion: 150 },
  { name: '西瓜', per100: n(30, 7.6, 0.6, 0.2, 0.4), prep: 'ready_to_consume', portion: 300 },
  { name: '牛奶', aliases: ['纯牛奶'], per100: n(54, 3.4, 3.0, 3.2, 0), prep: 'ready_to_consume', portion: 250, perBowl: 250 },
  { name: '酸奶', per100: n(72, 9.3, 3.2, 2.7, 0), prep: 'ready_to_consume', portion: 150 },
  { name: '豆浆', per100: n(31, 1.2, 3.0, 1.6, 1.1), prep: 'ready_to_consume', portion: 250, perBowl: 250 },
  { name: '拿铁', aliases: ['咖啡', '美式'], per100: n(55, 5.0, 3.0, 2.7, 0), prep: 'ready_to_consume', portion: 250 },
  { name: '奶茶', per100: n(75, 13.0, 1.0, 2.2, 0), prep: 'ready_to_consume', portion: 500 },
  { name: '可乐', aliases: ['汽水'], per100: n(43, 10.6, 0, 0, 0), prep: 'ready_to_consume', portion: 330 },

  // 零食 / 快餐
  { name: '花生', per100: n(567, 16.1, 25.8, 49.2, 8.5), prep: 'ready_to_consume', portion: 30 },
  { name: '杏仁', aliases: ['坚果'], per100: n(579, 21.6, 21.2, 49.9, 12.5), prep: 'ready_to_consume', portion: 25 },
  { name: '薯片', per100: n(536, 53.0, 6.6, 34.6, 4.4), prep: 'ready_to_consume', portion: 70 },
  { name: '薯条', per100: n(312, 41.0, 3.4, 15.0, 3.8), prep: 'cooked', portion: 120 },
  { name: '汉堡', per100: n(250, 30.0, 13.0, 9.0, 1.5), prep: 'ready_to_consume', portion: 200, perUnit: 200 },
  { name: '披萨', aliases: ['比萨'], per100: n(266, 33.0, 11.0, 10.0, 2.3), prep: 'ready_to_consume', portion: 200, perUnit: 100 },
  { name: '巧克力', per100: n(546, 61.0, 4.9, 31.0, 7.0), prep: 'ready_to_consume', portion: 30 },
]

// 未命中食物表时的兜底口径:一份普通中式菜的量级。confidence 会标成 low。
export const FALLBACK_PER_100 = n(150, 15.0, 8.0, 6.0, 1.0)
const FALLBACK_PORTION = 150

/** 按规范名找食物定义;兜底项(用户原话当食物名)找不到,返回 null。 */
export function findFoodDef(name: string): FoodDef | null {
  return FOOD_TABLE.find((def) => def.name === name) ?? null
}

/** 全角数字 → 半角,不然「２００ｇ」匹配不上。 */
function normalize(text: string): string {
  return text.replace(/[０-９]/g, (c) => String.fromCharCode(c.charCodeAt(0) - 0xfee0))
}

const CN_DIGITS: Record<string, number> = {
  一: 1,
  两: 2,
  二: 2,
  三: 3,
  四: 4,
  五: 5,
  六: 6,
  七: 7,
  八: 8,
  九: 9,
  十: 10,
  半: 0.5,
}

interface FoodHit {
  def: FoodDef
  start: number
  end: number
}

/** 在文本里找出所有已知食物,长名优先、不重叠,按出现顺序返回。 */
function findFoods(text: string): FoodHit[] {
  const candidates: { def: FoodDef; alias: string; index: number }[] = []
  for (const def of FOOD_TABLE) {
    for (const alias of [def.name, ...(def.aliases ?? [])]) {
      let from = 0
      for (;;) {
        const index = text.indexOf(alias, from)
        if (index === -1) break
        candidates.push({ def, alias, index })
        from = index + 1
      }
    }
  }
  // 同一段文字被多个别名命中时(「全麦面包」同时命中「面包」),取更长的那个
  candidates.sort((a, b) => a.index - b.index || b.alias.length - a.alias.length)
  const hits: FoodHit[] = []
  let cursor = -1
  for (const candidate of candidates) {
    if (candidate.index < cursor) continue
    hits.push({
      def: candidate.def,
      start: candidate.index,
      end: candidate.index + candidate.alias.length,
    })
    cursor = candidate.index + candidate.alias.length
  }
  return hits
}

const QUANTITY_RE =
  /(\d+(?:\.\d+)?|[一两二三四五六七八九十半]+)\s*(千克|公斤|毫升|kg|ml|克|g|升|个|颗|只|杯|碗|片|份|勺|块|根|两|斤)?/gi

function parseCnNumber(raw: string): number | null {
  if (/^\d/.test(raw)) return Number(raw)
  const chars = [...raw]
  if (chars.length === 1) return CN_DIGITS[chars[0]] ?? null
  if (chars.length === 2 && chars[1] === '十') return (CN_DIGITS[chars[0]] ?? 0) * 10
  if (chars.length === 2 && chars[0] === '十') return 10 + (CN_DIGITS[chars[1]] ?? 0)
  return CN_DIGITS[chars[0]] ?? null
}

interface QuantityToken {
  value: number
  unit: string
  start: number
  end: number
}

/** 扫出一段文本里所有「数量(+量词)」。`skip` 是食物名占据的区间——「三文鱼」里的
 *  「三」、「一品锅」里的「一」不是数量,落在食物名内部的匹配一律丢掉。 */
function findQuantities(text: string, skip: { start: number; end: number }[] = []): QuantityToken[] {
  QUANTITY_RE.lastIndex = 0
  const tokens: QuantityToken[] = []
  for (;;) {
    const match = QUANTITY_RE.exec(text)
    if (!match) break
    const start = match.index
    const end = start + match[0].length
    if (skip.some((range) => start < range.end && end > range.start)) continue
    const value = parseCnNumber(match[1])
    if (value === null || value <= 0) continue
    tokens.push({ value, unit: (match[2] ?? '').toLowerCase(), start, end })
  }
  return tokens
}

/** 把「数量 + 量词」折算成克。 */
function tokenToGrams(token: QuantityToken, def: FoodDef | null): number | null {
  const { value, unit } = token
  const portion = def?.portion ?? FALLBACK_PORTION
  switch (unit) {
    case '克':
    case 'g':
    case 'ml':
    case '毫升':
      return value
    case '千克':
    case '公斤':
    case 'kg':
    case '升':
      return value * 1000
    case '两':
      return value * 50
    case '斤':
      return value * 500
    case '个':
    case '颗':
    case '只':
    case '块':
    case '根':
      return value * (def?.perUnit ?? portion)
    case '杯':
      return value * 250
    case '碗':
      return value * (def?.perBowl ?? 200)
    case '片':
      return value * (def?.perUnit ?? 30)
    case '勺':
      return value * 15
    case '份':
      return value * portion
    default:
      // 光写数字没量词:「米饭200」当克重;「两个蛋」已被上面的量词分支接走
      return value >= 10 ? value : value * (def?.perUnit ?? portion)
  }
}

const MEAL_KEYWORDS: [MealSlot, string[]][] = [
  ['breakfast', ['早餐', '早饭', '早上', '早点']],
  ['lunch', ['午餐', '午饭', '中午', '中饭']],
  ['dinner', ['晚餐', '晚饭', '晚上', '夜宵', '宵夜']],
  ['other', ['加餐', '下午茶', '零食']],
]

/** 说了餐次就用说的;没说就按当前钟点猜(真实链路里这个判断在 LLM 里)。 */
export function detectMealSlot(text: string, now: Date = new Date()): MealSlot {
  for (const [slot, keywords] of MEAL_KEYWORDS) {
    if (keywords.some((keyword) => text.includes(keyword))) return slot
  }
  const hour = now.getHours()
  if (hour < 10) return 'breakfast'
  if (hour < 15) return 'lunch'
  if (hour < 21) return 'dinner'
  return 'other'
}

/** 每 100g × 克重 / 100,逐字段 null 传播(SPEC §7.1)。 */
export function scaleNutrients(per100: NutrientSet, grams: number): NutrientSet {
  const scale = (value: number | null): number | null =>
    value === null ? null : Math.round(((value * grams) / 100) * 10) / 10
  return {
    kcal: scale(per100.kcal),
    carb_g: scale(per100.carb_g),
    protein_g: scale(per100.protein_g),
    fat_g: scale(per100.fat_g),
    fiber_g: scale(per100.fiber_g),
  }
}

export interface ParsedHit {
  item: ParsedFoodItem
  per100: NutrientSet
  known: boolean
}

/** 一个数量最多归一样食物,一样食物最多拿一个数量。
 *
 *  中文两种语序都常见——「200g米饭」(数量在前)和「米饭200g」(数量在后),所以按
 *  **紧邻距离**配对,而不是按语序假设:每个数量找离它最近的那样食物,前后都算,
 *  距离相同时算给后面那样(「200g米饭」比「…米饭 200g西兰花」更常见)。
 *  这样「200g米饭和一份西兰花」里,「一份」不会被米饭抢走。 */
const MAX_BIND_DISTANCE = 2

function bindQuantities(hits: FoodHit[], tokens: QuantityToken[]): (QuantityToken | null)[] {
  const bound: (QuantityToken | null)[] = hits.map(() => null)
  for (const token of tokens) {
    let best = -1
    let bestDistance = Number.POSITIVE_INFINITY
    for (let index = 0; index < hits.length; index += 1) {
      if (bound[index] !== null) continue
      const hit = hits[index]
      // 数量在食物名前面 / 后面两种贴法,取够近的那个
      const distance =
        hit.start >= token.end
          ? hit.start - token.end
          : hit.end <= token.start
            ? token.start - hit.end
            : Number.POSITIVE_INFINITY
      if (distance < bestDistance) {
        bestDistance = distance
        best = index
      }
    }
    if (best !== -1 && bestDistance <= MAX_BIND_DISTANCE) bound[best] = token
  }
  return bound
}

/** 顶替 parse_diet_text 的食物抽取部分:文本 → 若干 (食物, 克重, 生熟)。 */
export function parseFoods(rawText: string): ParsedHit[] {
  const text = normalize(rawText)
  const hits = findFoods(text)
  if (hits.length === 0) return []

  const tokens = findQuantities(text, hits)
  const bound = bindQuantities(hits, tokens)

  return hits.map((hit, index) => {
    const token = bound[index]
    const grams = (token && tokenToGrams(token, hit.def)) ?? hit.def.portion
    return {
      item: {
        food_name: hit.def.name,
        quantity: Math.round(grams * 10) / 10,
        unit: 'g' as const,
        preparation_state: hit.def.prep,
      },
      per100: hit.def.per100,
      known: true,
    }
  })
}

/** 只从一句话里取份量(改份量的修正走这条:「改成200g」「其实是两个」)。
 *  量词折算要知道是哪种食物(一个鸡蛋 50g、一个苹果 200g),所以带食物名进来。 */
export function parseQuantity(text: string, foodName: string): number | null {
  const [token] = findQuantities(normalize(text))
  if (!token) return null
  const grams = tokenToGrams(token, findFoodDef(foodName))
  return grams === null ? null : Math.round(grams * 10) / 10
}

/** 「这句话有吃东西的意思吗」——没匹配到食物时用来区分闲聊 / 认不出的食物。 */
export function looksLikeEating(rawText: string): boolean {
  return /吃|喝|来了|干了|点了|炫了|整了|啃|嗦|下肚|摄入/.test(normalize(rawText))
}

/** 认不出食物但明显在说吃东西:拿原话当食物名兜底,置信度标 low。 */
export function fallbackHit(rawText: string): ParsedHit {
  const text = normalize(rawText)
  const [token] = findQuantities(text)
  const grams = (token && tokenToGrams(token, null)) ?? FALLBACK_PORTION
  const name =
    text
      .replace(/[0-9.]+\s*(千克|公斤|毫升|kg|ml|克|g|升|个|颗|只|杯|碗|片|份|勺|块|根|两|斤)?/gi, '')
      .replace(/我?(早餐|早饭|午餐|午饭|晚餐|晚饭|加餐|夜宵)?(刚才|今天|中午|早上|晚上)?(吃|喝)(了|过)?/g, '')
      .trim()
      .slice(0, 12) || '未知食物'
  return {
    item: { food_name: name, quantity: grams, unit: 'g', preparation_state: 'cooked' },
    per100: FALLBACK_PER_100,
    known: false,
  }
}
