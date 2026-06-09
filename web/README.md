# Taskpps Web UI

React + TypeScript + Vite 构建的 Taskpps 前端界面。

## 技术栈

- **框架** — React 18 + TypeScript
- **构建** — Vite + SWC
- **UI** — Ant Design 5 + Pro Layout
- **状态** — TanStack React Query
- **流程图** — React Flow（@xyflow/react）
- **HTTP** — Axios

## 开发

```bash
npm install
npm run dev          # → http://localhost:5173
npm run build        # 生产构建
npm run check        # TypeScript 类型检查
npm run lint         # ESLint
```

## 环境变量

| 变量 | 默认值 | 说明 |
|:--|:--|:--|
| `VITE_API_BASE` | `http://localhost:26521` | 后端 API 地址 |

## 目录结构

```
web/src/
├── api/       # API 调用
├── components/# 通用组件
├── hooks/     # 自定义 hooks
├── pages/     # 页面
├── types/     # TypeScript 类型
└── utils/     # 工具函数
```
