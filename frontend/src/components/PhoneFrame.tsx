// 手机外框。产品唯一正式布局是 390×844 竖屏(design.md §1),但在桌面浏览器里
// 直接铺满窗口会看不出真实可视范围:内容有多长、什么时候该滚、底部输入条会挡住
// 什么,全靠脑补。所以套一层机身——屏幕是固定尺寸的裁剪容器,应用的滚动、底部
// 输入条、弹窗全部发生在这层里面,而不是发生在浏览器窗口上。
//
// 真机/窄视口下机身整体收起(见 global.css 的 max-width:480px 分支):屏幕铺满
// 100dvh,状态栏和 Home 条交还给系统——PWA 装到手机上不该看到一个假边框。

import { useEffect, useState, type ReactNode } from 'react'

function clockLabel(now: Date): string {
  return `${now.getHours()}:${String(now.getMinutes()).padStart(2, '0')}`
}

/** 状态栏时钟。纯装饰,跟业务归属日无关(归属日一律走后端,见 SPEC §6.1)。 */
function useClock(): string {
  const [label, setLabel] = useState(() => clockLabel(new Date()))
  useEffect(() => {
    const timer = setInterval(() => setLabel(clockLabel(new Date())), 30_000)
    return () => clearInterval(timer)
  }, [])
  return label
}

export function PhoneFrame({ children }: { children: ReactNode }) {
  const time = useClock()

  return (
    <div className="device">
      <div className="device__chassis">
        <span className="device__key device__key--silent" aria-hidden="true" />
        <span className="device__key device__key--vol-up" aria-hidden="true" />
        <span className="device__key device__key--vol-down" aria-hidden="true" />
        <span className="device__key device__key--power" aria-hidden="true" />

        <div className="device__screen">
          <div className="device__statusbar" aria-hidden="true">
            <span className="device__clock">{time}</span>
            <span className="device__island" />
            <span className="device__signals">
              <svg width="17" height="11" viewBox="0 0 17 11" fill="currentColor">
                <rect y="7.5" width="3" height="3.5" rx="1" />
                <rect x="4.5" y="5" width="3" height="6" rx="1" />
                <rect x="9" y="2.5" width="3" height="8.5" rx="1" />
                <rect x="13.5" width="3" height="11" rx="1" opacity=".35" />
              </svg>
              <svg
                width="15"
                height="11"
                viewBox="0 0 15 11"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.5"
                strokeLinecap="round"
              >
                <path d="M1 3.4a9.5 9.5 0 0 1 13 0" />
                <path d="M3.8 6.2a5.4 5.4 0 0 1 7.4 0" />
                <circle cx="7.5" cy="9.2" r=".8" fill="currentColor" stroke="none" />
              </svg>
              <svg width="25" height="12" viewBox="0 0 25 12" fill="none">
                <rect
                  x=".6"
                  y=".6"
                  width="21"
                  height="10.8"
                  rx="3.2"
                  stroke="currentColor"
                  strokeOpacity=".35"
                />
                <rect x="2.2" y="2.2" width="14" height="7.6" rx="2" fill="currentColor" />
                <path d="M23.2 4.2v3.6a2 2 0 0 0 0-3.6Z" fill="currentColor" fillOpacity=".35" />
              </svg>
            </span>
          </div>

          {children}

          <span className="device__home" aria-hidden="true" />
        </div>
      </div>
    </div>
  )
}
