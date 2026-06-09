import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tsconfigPaths from 'vite-tsconfig-paths';

// https://vite.dev/config/
export default defineConfig({
  build: {
    sourcemap: 'hidden',
    chunkSizeWarningLimit: 1024,
    rollupOptions: {
      output: {
        // 拆分 vendor 提升缓存命中率 + 减少首屏 JS 体积
        manualChunks: {
          'react-vendor': ['react', 'react-dom', 'react-router-dom'],
          'query-vendor': ['@tanstack/react-query'],
          'antd-vendor': ['antd', '@ant-design/icons'],
          'flow-vendor': ['@xyflow/react', 'dagre'],
          'chart-vendor': ['dayjs', 'html-to-image', 'react-window', 'zustand'],
        },
      },
    },
  },
  plugins: [
    react(),
    tsconfigPaths(),
  ],
  resolve: {
    alias: {
      '@': '/src',
    },
  },
  server: {
    proxy: {
      '/api': {
        target: 'http://localhost:26521',
        changeOrigin: true,
      },
    },
  },
})
