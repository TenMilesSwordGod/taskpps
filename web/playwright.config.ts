import { defineConfig } from '@playwright/test';

/**
 * Playwright e2e 测试配置（issue #206）。
 *
 * 设计决策（为什么这么写）：
 * - 使用 Vite dev server 作为 webServer，无需预构建，与开发体验一致。
 * - reuseExistingServer 在 CI 环境下为 false（启动独立 server），
 *   本地开发时复用已有 dev server 避免端口冲突。
 * - baseURL 指向 /e2e/workflow-editor 测试专页，绕过认证和 API 依赖。
 * - 仅配置 chromium 浏览器，减少环境依赖和安装时间。
 */
export default defineConfig({
  testDir: './e2e',
  timeout: 30000,
  expect: { timeout: 10000 },
  use: {
    baseURL: 'http://localhost:5173',
    headless: true,
    viewport: { width: 1440, height: 900 },
  },
  webServer: {
    command: 'npm run dev',
    url: 'http://localhost:5173',
    reuseExistingServer: !process.env.CI,
    timeout: 30000,
    // 绕过环境代理（curl 经 http_proxy 访问 localhost 会 502）
    env: {
      ...process.env,
      http_proxy: '',
      https_proxy: '',
      HTTP_PROXY: '',
      HTTPS_PROXY: '',
      no_proxy: 'localhost,127.0.0.1',
      NO_PROXY: 'localhost,127.0.0.1',
    },
  },
  projects: [
    {
      name: 'chromium',
      use: { browserName: 'chromium' },
    },
  ],
});
