import { useEffect, useState } from 'react'
import { RecordTab } from './components/RecordTab'
import { checkHealth, type HealthStatus } from './lib/health'

type Tab = 'record' | 'board'

const TAB_LABELS: Record<Tab, string> = {
  record: '记录',
  board: '看板',
}

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

  return <p role="status">{text}</p>
}

function App() {
  const [activeTab, setActiveTab] = useState<Tab>('record')

  return (
    <div>
      <div role="tablist" aria-label="主导航">
        {(Object.keys(TAB_LABELS) as Tab[]).map((tab) => (
          <button
            key={tab}
            role="tab"
            aria-selected={activeTab === tab}
            onClick={() => setActiveTab(tab)}
          >
            {TAB_LABELS[tab]}
          </button>
        ))}
      </div>
      <main role="tabpanel">
        {activeTab === 'record' ? <RecordTab /> : <p>看板页(待实现)</p>}
      </main>
      <HealthIndicator />
    </div>
  )
}

export default App
