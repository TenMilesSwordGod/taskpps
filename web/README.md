# Taskpps Web UI

React + TypeScript + Vite 构建的 Taskpps 前端界面。

## 功能概览

- 流水线列表：按项目 / 文件夹两级分组，工具栏「新建」支持新建流水线、创建文件夹、注册项目目录（需登录）
- 流水线详情：YAML 编辑、可视化 DAG 编排、触发运行
- 运行历史、服务器（Agent）、插件中心

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
