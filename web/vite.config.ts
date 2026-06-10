import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tsconfigPaths from 'vite-tsconfig-paths';

// https://vite.dev/config/
export default defineConfig({
  build: {
    // 关闭源码映射体积警告：开发环境 sourcemap 很有用，生产可关掉
    sourcemap: false,
    // 1.5MB 阈值放宽：单 chunk > 2MB 警告
    chunkSizeWarningLimit: 1500,
    // 用 esbuild 做压缩：比 terser 快 20-40x
    minify: 'esbuild',
    target: 'es2020',
    cssCodeSplit: true,
    // 关闭压缩大小评估可让 build 更快
    reportCompressedSize: false,
    rollupOptions: {
      output: {
        // 拆分 vendor 提升缓存命中率 + 减少首屏 JS 体积
        manualChunks(id) {
          if (!id.includes('node_modules')) return undefined
          if (id.includes('react-flow') || id.includes('@xyflow') || id.includes('dagre')) {
            return 'flow-vendor'
          }
          if (id.includes('@ant-design') || id.includes('antd') || id.includes('rc-')) {
            return 'antd-vendor'
          }
          if (id.includes('@tanstack')) {
            return 'query-vendor'
          }
          if (id.includes('html-to-image')) {
            return 'image-vendor'
          }
          if (id.includes('react-window')) {
            return 'window-vendor'
          }
          if (id.match(/[\\/]node_modules[\\/](react|react-dom|react-router|react-router-dom|scheduler)[\\/]/)) {
            return 'react-vendor'
          }
          if (id.match(/[\\/]node_modules[\\/](dayjs|lucide-react|zustand|clsx|axios)[\\/]/)) {
            return 'misc-vendor'
          }
          return 'vendor'
        },
      },
    },
  },
  esbuild: {
    // 生产环境剥离 console/debugger；error 保留以防关键日志丢失
    drop: process.env.NODE_ENV === 'production' ? ['console', 'debugger'] : [],
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
