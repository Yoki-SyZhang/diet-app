// vercel-display 专属:开场说明。公开链接的第一屏必须先把边界讲清楚——这是演示、
// 数据是假的、哪些流程能走通、哪些没有。不说清楚的话,访客会拿演示版的行为当产品
// 行为来判断(比如以为「只认几十种食物」是产品缺陷,而不是 mock 的限制)。
//
// 只在演示模式渲染(App.tsx 已用 isDemoMode 挡住),首次访问弹一次;之后点顶栏那个
// 「Mock 演示模式」徽标可以随时重开,「重置演示数据」也会让它重新出现。

import { createPortal } from 'react-dom'

const REPO_BRANCH_URL = 'https://github.com/Yoki-SyZhang/diet-app/tree/feature_demo_04_write_path'

/** 挑 8 个覆盖不同量词写法的,让访客照着就能试出效果。完整食物表在 lib/mock/foods.ts。
 *
 *  `prep` 必须标出来,而且要和 foods.ts 里的 preparation_state 一致:生熟口径差得很多
 *  (生米饭每 100g 约 350kcal、熟的 116),不写清楚等于让人按错的口径填克重。
 *  用词跟 types/diet.ts 的 PREP_STATE_LABELS 对齐,和确认卡片上显示的那个字一样。 */
const SAMPLE_FOODS = [
  { name: '米饭', prep: '熟', hint: '一碗 = 200g' },
  { name: '水煮蛋', prep: '熟', hint: '两个 = 100g' },
  { name: '鸡胸肉', prep: '熟', hint: '150g' },
  { name: '西兰花', prep: '熟', hint: '一份 = 180g' },
  { name: '面条', prep: '熟', hint: '一碗 = 250g' },
  { name: '牛奶', prep: '即食', hint: '一杯 = 250g' },
  { name: '香蕉', prep: '即食', hint: '一根 = 120g' },
  { name: '苹果', prep: '即食', hint: '一个 = 200g' },
]

const CAN_DO = [
  '输入 → 识别 → 确认 → 写进今日明细',
  '输入 → 修改解析结果 → 重新估算 → 写入',
  '输入 → 放弃整批,不留记录',
  '在今日明细里手动删除某一行',
]

const CANNOT_DO = [
  '在对话里修改已经记录的内容(要去今日明细删掉那行重记)',
  '在对话里删除记录(同上,只能手动删)',
  '真正的闲聊——没接模型,只有固定回复',
]

export function DemoIntroDialog({ onClose }: { onClose: () => void }) {
  const portalTarget = document.querySelector('.device__screen') ?? document.body

  return createPortal(
    <div className="intro-backdrop">
      <div role="dialog" aria-label="Mock 演示模式说明" className="intro">
        <div className="intro__scroll">
          <span className="intro__badge">Mock 演示模式</span>
          <h2 className="intro__title">这是一个交互演示,不是真实产品</h2>
          <p className="intro__lead">
            所有数据都是 <b>mock</b>:<b>未连接真实后端 API</b>、<b>未调用真实模型</b>。
            你的操作只写进这台设备的浏览器(localStorage),不会上传,别人也看不到。
          </p>
          <p className="intro__lead">
            想看接真实 FastAPI + LLM 的完整实现,去 GitHub 的{' '}
            <a href={REPO_BRANCH_URL} target="_blank" rel="noreferrer">
              feature_demo_04_write_path
            </a>{' '}
            分支。
          </p>

          <h3 className="intro__h3">能识别的食物只有这几样</h3>
          <ul className="intro__foods">
            {SAMPLE_FOODS.map((food) => (
              <li key={food.name}>
                <b>{food.name}</b>
                <i className="intro__prep">{food.prep}</i>
                <span>{food.hint}</span>
              </li>
            ))}
          </ul>
          <p className="intro__note">
            克重一律按标注的状态算:<b>熟重</b>(米饭、鸡胸肉、西兰花都是做熟之后的重量)或
            <b>即食</b>。生熟差别很大,生米饭每 100g 约 350kcal、熟的只有 116。
            <br />
            表外的食物也能录入,但营养值是粗略兜底估的,会标成低置信度。
          </p>

          <h3 className="intro__h3">可以走通的流程</h3>
          <ul className="intro__list intro__list--yes">
            {CAN_DO.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>

          <h3 className="intro__h3">演示里没有的</h3>
          <ul className="intro__list intro__list--no">
            {CANNOT_DO.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>

          <h3 className="intro__h3">照这句试试</h3>
          <p className="intro__example">午餐吃了200g米饭和一份西兰花</p>
        </div>
        <button type="button" className="btn-primary intro__cta" onClick={onClose}>
          开始体验
        </button>
      </div>
    </div>,
    portalTarget,
  )
}
