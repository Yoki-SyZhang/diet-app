import { useEffect, useState } from 'react'
import { PhoneFrame } from './components/PhoneFrame'
import { RecordTab } from './components/RecordTab'
import { checkHealth, resetDemoData, type AppHealthStatus } from './lib/api'
import { isDemoMode } from './lib/dataSource'

type Tab = 'record' | 'board' | 'mine'

/** 底部导航。图形沿用设计稿的抽象形状(圆角方/方/圆),不是临时占位。 */
const TABS: { id: Tab; label: string; kicker: string }[] = [
  { id: 'record', label: '记录', kicker: 'RECORD' },
  { id: 'board', label: '看板', kicker: 'DASHBOARD' },
  { id: 'mine', label: '我的', kicker: 'PROFILE' },
]

const HEALTH_TEXT: Record<AppHealthStatus | 'checking', string> = {
  checking: '连接后端中…',
  ok: '已连接后端',
  error: '无法连接后端',
  unreachable: '无法连接后端',
  // 演示版没有后端可连,这里绝不能显示成「已连接」(mock/system.ts 的注释同理)
  demo: 'Mock 演示模式',
}

function HealthIndicator() {
  const [status, setStatus] = useState<AppHealthStatus | 'checking'>('checking')

  useEffect(() => {
    let cancelled = false
    checkHealth().then((result) => {
      if (!cancelled) setStatus(result)
    })
    return () => {
      cancelled = true
    }
  }, [])

  return (
    <p role="status" className={`health health--${status}`}>
      <span className="health__dot" aria-hidden="true" />
      {HEALTH_TEXT[status]}
    </p>
  )
}

/** 演示模式顶栏:说清「数据只在本机」,并给一条把数据玩乱后回到初始状态的路。 */
function DemoBar() {
  const [confirming, setConfirming] = useState(false)

  return (
    <div className="demo-bar">
      <HealthIndicator />
      <span className="demo-bar__note">· 数据仅存本机</span>
      <button
        type="button"
        className="demo-bar__reset"
        onClick={() => {
          if (!confirming) {
            setConfirming(true)
            return
          }
          resetDemoData()
          // 整页重载最省事:记录页的消息/明细/卡片状态都在组件里,重新挂载即可
          globalThis.location.reload()
        }}
      >
        {confirming ? '确定重置?' : '重置演示数据'}
      </button>
    </div>
  )
}

function App() {
  const [activeTab, setActiveTab] = useState<Tab>('record')
  const current = TABS.find((tab) => tab.id === activeTab)!

  return (
    <PhoneFrame>
      <div className="app-shell">
        <header className="app-bar">
          <span className="app-bar__kicker">{current.kicker}</span>
          {isDemoMode ? <DemoBar /> : <HealthIndicator />}
        </header>
        <main role="tabpanel" className="app-body">
          {activeTab === 'record' ? (
            <RecordTab />
          ) : (
            <p className="tab-todo">{current.label}页(待实现)</p>
          )}
        </main>
        <nav className="tabbar" role="tablist" aria-label="主导航">
          {TABS.map((tab) => (
            <button
              key={tab.id}
              type="button"
              role="tab"
              aria-selected={activeTab === tab.id}
              onClick={() => setActiveTab(tab.id)}
            >
              <span className={`tabbar__glyph tabbar__glyph--${tab.id}`} aria-hidden="true" />
              {tab.label}
            </button>
          ))}
        </nav>
      </div>
    </PhoneFrame>
  )
}

export default App
