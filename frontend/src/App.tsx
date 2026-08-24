import { useEffect, useState } from 'react'
import { PhoneFrame } from './components/PhoneFrame'
import { RecordTab } from './components/RecordTab'
import { checkHealth, type HealthStatus } from './lib/health'

type Tab = 'record' | 'board' | 'mine'

/** 底部导航。图形沿用设计稿的抽象形状(圆角方/方/圆),不是临时占位。 */
const TABS: { id: Tab; label: string; kicker: string }[] = [
  { id: 'record', label: '记录', kicker: 'RECORD' },
  { id: 'board', label: '看板', kicker: 'DASHBOARD' },
  { id: 'mine', label: '我的', kicker: 'PROFILE' },
]

function HealthIndicator() {
  const [status, setStatus] = useState<HealthStatus | 'checking'>('checking')

  useEffect(() => {
    let cancelled = false
    checkHealth().then((result) => {
      if (!cancelled) setStatus(result)
    })
    return () => {
      cancelled = true
    }
  }, [])

  const text =
    status === 'checking' ? '连接后端中…' : status === 'ok' ? '已连接后端' : '无法连接后端'

  return (
    <p role="status" className={`health health--${status}`}>
      <span className="health__dot" aria-hidden="true" />
      {text}
    </p>
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
          <HealthIndicator />
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
