import { resolve } from 'node:path'
import react from '@vitejs/plugin-react'
import { VitePWA } from 'vite-plugin-pwa'
import { defineConfig } from 'vitest/config'

// https://vite.dev/config/
export default defineConfig({
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
})
