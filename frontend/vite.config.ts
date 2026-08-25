import { resolve } from 'node:path'
import react from '@vitejs/plugin-react'
import { VitePWA } from 'vite-plugin-pwa'
import { defineConfig } from 'vitest/config'

/** vercel-display:production 构建默认走 mock 数据源(演示版不连任何后端)。
 *
 *  为什么不用 `.env.production`——仓库根 `.gitignore` 第 26 行的 `.env.*` 会把它挡在
 *  git 之外,Vercel 上根本拿不到这个文件,构建出来反而是连真实后端的版本(而且本地
 *  跑一切正常,极难发现)。所以默认值写在这份**被 git 跟踪**的配置里。
 *
 *  显式给了 VITE_DATA_SOURCE 就用给的,方便本地试:
 *  `VITE_DATA_SOURCE=mock npm run dev`(PowerShell: `$env:VITE_DATA_SOURCE='mock'`)。
 *  dev / test 默认空串 → 走真实 FastAPI,和业务分支行为一致。 */
function dataSource(mode: string): string {
  return process.env.VITE_DATA_SOURCE ?? (mode === 'production' ? 'mock' : '')
}

// https://vite.dev/config/
export default defineConfig(({ mode }) => ({
  define: {
    'import.meta.env.VITE_DATA_SOURCE': JSON.stringify(dataSource(mode)),
  },
  plugins: [
    react(),
    VitePWA({
      registerType: 'autoUpdate',
      manifest: {
        name: 'DietApp',
        short_name: 'DietApp',
        description: '单用户减脂追踪 PWA',
        theme_color: '#2E8B62',
        background_color: '#EDF2E9',
        display: 'standalone',
        icons: [
          { src: '/icons/icon-192.png', sizes: '192x192', type: 'image/png' },
          { src: '/icons/icon-512.png', sizes: '512x512', type: 'image/png' },
          {
            src: '/icons/icon-512.png',
            sizes: '512x512',
            type: 'image/png',
            purpose: 'maskable',
          },
        ],
      },
    }),
  ],
  resolve: {
    alias: {
      '@': resolve(import.meta.dirname, 'src'),
    },
  },
  server: {
    port: 5173,
    strictPort: true,
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./vitest.setup.ts'],
    globals: true,
    // 前端测试放 src/tests/ 而非仓库根 tests/:测试文件依赖 Node 从自身
    // 所在目录逐级向上找 node_modules,tests/ 和 frontend/ 是平行目录,
    // node_modules 只在 frontend/ 下,放到仓库根 tests/ 会找不到依赖
    // (实测验证过,不是配置疏漏)。例外记录见 AGENTS.md。
    include: ['src/tests/**/*.{test,spec}.{ts,tsx}'],
  },
}))
