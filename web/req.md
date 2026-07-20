# taskpps Web UI 需求规格说明书（V1）

> 项目：taskpps（Task Pipeline Processing System）服务器配套前端
> 版本：V1（最小可用版本）
> 作者：设计阶段
> 最后更新：2026-06-08

---

## 1. 概述

### 1.1 背景

taskpps 是一套基于 Python（FastAPI 风格）实现的流水线执行服务器，通过 YAML 描述流水线（Pipeline），由任务（Task）构成 DAG，按依赖顺序执行。当前已具备完整的 CLI、Agent、API，但缺少可视化 Web 控制台，运维和开发人员只能通过命令行或直接查看日志来了解流水线状态。

### 1.2 V1 目标

为 taskpps 服务器提供一个最小可用的 Web UI，使使用者能够：

1. **总览面板（Index Panel）**：快速了解所有流水线及其任务执行进度。
2. **DAG 可视化**：以图形化方式查看流水线结构，支持缩放、平移、节点拖拽。
3. **属性面板（Properties Panel）**：查看任务节点的属性，可拖拽调整大小、可最小化/最大化。
4. **图片导出**：将当前流水线或运行结果一键导出为 PNG / SVG 图片。

> **关于编辑（V1 / V2 边界）**：V1 仅查看，不支持保存回 YAML。但底层要为 V2 预留扩展：
> - 状态层、数据模型、表单组件按"查看 + 编辑"双模式设计，V1 通过 `editable=false` 全局开关禁用写入路径。
> - 选中节点后的属性面板使用 AntD `Form disabled`（V1 灰显），V2 打开开关即可编辑。
> - 写操作 API（PUT / PATCH）V1 不调用但保留封装，便于 V2 接入。

### 1.3 V1 非目标（明确不做）

- 流水线的可视化编辑与保存回 YAML
- 触发器（Trigger）的 CRUD UI
- Agent 节点管理 UI
- 用户与权限管理
- 多租户、审计日志
- 流水线版本对比、Git 历史
- API Key 鉴权与登录

---

## 2. 技术选型

### 2.1 推荐方案

| 类别 | 选型 | 理由 |
|---|---|---|
| 基础框架 | React 18 + TypeScript | 生态成熟，类型安全 |
| 构建工具 | Vite | 启动快，原生 ESM |
| UI 组件库 | Ant Design 5 | 用户指定，企业级风格 |
| DAG 画布 | React Flow（`@xyflow/react` v12） | 业界事实标准 |
| 画布上层封装 | **@ant-design/pro-flow** | AntD 官方出品，与 AntD 主题无缝衔接 |
| 服务端状态 | @tanstack/react-query | 缓存、轮询、SSE 友好 |
| 本地状态 | Zustand | 轻量、零样板 |
| 路由 | React Router 6 | 标配 |
| 图片导出 | html-to-image | 配合 React Flow 输出 PNG |
| 时间处理 | dayjs | AntD 内置依赖 |

### 2.2 三个备选库的对比

| 库 | 优点 | 缺点 | 结论 |
|---|---|---|---|
| **@ant-design/pro-flow** | AntD 官方维护，开箱即用，与 AntD 主题/组件原生融合 | 社区案例相对少 | **V1 主推** |
| **@kingpa/fast-flow** | 内置节点库侧边栏、设置面板和自动布局，搭积木式 | 第三方，迭代节奏不确定 | 备选 |
| **react-flow-design** | 类钉钉审批流风格 | 需要手动配合 AntD 集成，无流水线领域原语 | 不推荐 |

**决策建议**：首选 `@ant-design/pro-flow`；若定制上限不足，回退到「React Flow + AntD 组件」——所有 UI 资产（卡片、抽屉、表单）保持不变，仅替换画布外壳。

---

## 3. 信息架构与路由

```
/                       仪表盘（健康状态、最近运行、流水线计数）
/pipelines              流水线索引面板（Pipeline List）
/pipelines/:file        流水线详情（DAG 画布 + 属性面板）
/runs                   运行历史（表格）
/runs/:id               运行详情（任务进度 + 实时日志）
```

V1 不做：/triggers、/agents、/settings。

---

## 4. 功能详细说明

### 4.1 仪表盘（/）

- 顶部四张统计卡片：流水线总数、今日运行数、运行中数量、失败数量。
- 中部：最近 10 条运行记录（时间、流水线名、状态 Tag、耗时、跳转链接）。
- 右侧：服务器健康状态指示灯（绿色/红色 + 延迟）。

### 4.2 流水线索引面板（/pipelines）

#### 4.2.1 展示内容

AntD `Table` 列出全部已加载的流水线（需后端新增 `GET /api/pipelines/` 端点）：

| 列 | 说明 |
|---|---|
| 名称 | 流水线 `name` |
| 文件 | YAML 文件名（点击进入详情） |
| 任务数 | 该流水线下的任务总数 |
| 子流水线数 | `pipelines:` 段数 |
| 最近运行 | 时间 + 状态 Tag |
| 成功率 | 近 30 天统计 |
| 操作 | 查看 / 触发运行 / 导出图片 |

#### 4.2.2 顶部工具栏

- 搜索框（按名称/文件过滤）
- 刷新按钮
- 「触发运行」按钮（弹出 `Modal`，选择 params）

### 4.3 流水线详情（/pipelines/:file）

#### 4.3.1 页面布局

```
┌─────────────────────────────────────────────────────────────┐
│  面包屑  / Pipelines / pipeline-ci-git-nexus.yaml            │
├──────────────────────────────┬──────────────────────────────┤
│                              │                              │
│   DAG 画布（React Flow）      │   属性面板（Properties）       │
│   - 缩放 / 平移 / 缩略图       │   - 拖拽调整宽度              │
│   - 子流水线作为分组节点       │   - 最大化 / 最小化按钮        │
│   - 任务节点按类型着色         │   - Tab 切换                  │
│   - 依赖箭头                   │   - 选中节点后填充表单         │
│                              │                              │
├──────────────────────────────┴──────────────────────────────┤
│  工具栏：[导出 PNG] [导出 SVG] [复制到剪贴板] [触发运行]        │
└─────────────────────────────────────────────────────────────┘
```

#### 4.3.2 层级模型与节点设计

**层级结构**：

| 层级 | 名称 | 形态 | 说明 |
|------|------|------|------|
| L0 | Pipeline | 淡灰虚线边界框（画布根） | 内含 SubPipeline / Post 父容器 / Start / End |
| L1 | SubPipeline | 蓝色虚线边界容器 | 仅含 Task，不可直接放原子行为 |
| L2 | Task | 绿色虚线边界容器 | 多原子容器，内部含 CMD/STEP/PLUGIN/INVOKE 原子节点 |
| L2 | Post 父容器 | 红色虚线边界容器（根层级） | 内含 on_fail/on_success/always 子容器 |
| L3 | Post 子容器 | Post 父容器内的钩子 | 多个原子节点，仅支持线性链式，无出端口 |
| L3 | 原子行为 | 叶子节点 | CMD / STEP / PLUGIN / INVOKE，1 in + 1 out |

**节点类型**：

- **SubPipelineNode**：蓝色虚线框容器，显示子流水线名与任务数。
- **TaskNode**：绿色虚线框容器，显示任务名及内部原子计数。
- **PostContainerNode**：红色虚线框，含 on_fail/on_success/always 三个子容器插槽。
- **StartEndNode**：Start/End 哨兵节点。
- **原子节点**（通过选中 Task 容器后在属性面板中查看/编辑）：

  | 类型 | 来源 | 视觉特征 |
  |---|---|---|
  | CMD | YAML `command`/`commands` | 等宽字体，命令式图标 |
  | STEP | YAML `steps` 列表项 | 多步骤图标，紫色 |
  | PLUGIN | YAML `plugin` | 插件图标 |
  | INVOKE | YAML `invoke` | 调用图标，蓝色 |

- 节点状态色（运行视图下）：pending=灰、running=蓝（脉冲）、success=绿、failed=红、skipped=黄。

#### 4.3.3 边（Edges）

- **SubPipeline 间依赖**：`depends_on` → 蓝色虚线箭头。
- **Task 间依赖**：`depends_on` → 灰色实线箭头（有 when 条件时中间插入决策菱形节点，yes=绿色实线、no=灰色虚线）。
- **原子间顺序**：Task/Post 容器内部原子按 YAML 列表顺序 + `execution_strategy` 决定执行顺序（隐式），不渲染节点间连线。
- **Post 从属关系**：Post 父容器底部虚线箭头连接到根层级（表示"后处理阶段"）。

#### 4.3.4 属性面板（Properties Panel）

**采用方案 A：可调分割栏** ✅

- 使用 AntD `Splitter`（v5.21+）实现左右拖拽改变宽度。
- 面板头部提供两个按钮：
  - **最小化**：折叠为右侧 40px 宽的图标条，悬停展开。
  - **最大化**：宽度变为 70vw，再次点击恢复上次宽度。
- 用户偏好（当前宽度、是否最大化）持久化到 `localStorage`，key 按 `pipeline:file` 维度隔离。
- 默认宽度 420px，最小 320px，最大 70vw。

**面板内容（Tab 结构）——选中 Task 容器时**：

| Tab | 字段 |
|---|---|
| 基本 | 名称、类型（只读）、描述 |
| 策略 | execution_strategy、when、on_failure（执行策略） |
| 环境变量 | Key-Value 动态列表 |
| 依赖 | 多选（其他 Task 名） |
| 高级 | timeout、retry、端口管理 |

**选中原子节点时**：直接复用 YAML 原始字段，不做独立定义。

> **V1 编辑策略**：所有表单项 `disabled` 灰显，但保留「复制为 YAML」按钮方便排错。V2 通过 `editable` 全局开关放开 `disabled` 即可，无需重构面板。

#### 4.3.5 工具栏

- 触发运行（弹出 params 表单）
- 导出 PNG
- 导出 SVG
- 复制图片到剪贴板
- 自动布局（调用 dagre / elk 进行层级布局）
- 适应窗口

#### 4.3.6 右键菜单

**在 Task 内部空白处右键**（新增原子）：
```text
┌──────────────────────┐
│ 添加原子行为 ▶        │
│  ├ ⌨ CMD             │
│  ├ ⚙ STEP            │
│  ├ 🧩 PLUGIN         │
│  └ 🔗 INVOKE         │
├──────────────────────┤
│ 删除 Task            │
│ 属性...              │
└──────────────────────┘
```

**在画布空白处右键**：
```text
┌──────────────────────┐
│ 添加 SubPipeline      │
│ 适应窗口              │
│ 自动布局              │
└──────────────────────┘
```

#### 4.3.7 验证规则

- **Task 非空**：Task 内部至少包含 1 个原子行为节点，且进/出端子必须连通（保存时）。
- **Post 子容器非空**：每个 Post 子容器内至少 1 个原子行为，进端口已路由连通（保存时）。
- **Post 子容器无分叉**：Post 子容器内部仅允许线性链式拓扑（保存时检测）。
- **原子列表顺序合法**：Task/Post 内部原子列表不能为空循环引用（保存时检测）。

### 4.4 运行历史（/runs）

- AntD `Table`，列：run_id、流水线名、状态、开始时间、耗时、触发方式（手动/触发器）。
- 顶部过滤：状态、流水线名、时间范围。
- 行点击 → 跳转 `/runs/:id`。

### 4.5 运行详情（/runs/:id）

#### 4.5.1 上半部分：实时任务进度

- 复用 `PipelineGraph` 组件，将节点颜色映射为 `TaskStatus`。
- 节点旁显示耗时与退出码（hover tooltip）。

#### 4.5.2 下半部分：实时日志

- 通过 `EventSource` 订阅 `GET /api/runs/{id}/logs` 的 SSE 流。
- 虚拟滚动列表（`react-window`）。
- 支持按任务名过滤、暂停自动滚动、搜索关键字。

#### 4.5.3 操作

- 取消运行（POST `/api/runs/{id}/cancel`）
- 导出当前运行截图（含状态着色）

---

## 5. 图片导出功能

### 5.1 静态导出

- 入口：流水线详情工具栏。
- 原理：React Flow 暴露 `getRectOfNodes` + `getTransformForBounds`，结合 `html-to-image` 的 `toPng` / `toSvg`。
- 输出：与画布同比例的 PNG（默认 2x DPI）或 SVG（矢量）。
- 包含：水印（taskpps logo + 流水线名 + 时间戳，可关闭）。

### 5.2 运行视图导出

- 入口：运行详情工具栏。
- 区别：节点叠加状态色和耗时标签。

### 5.3 复制到剪贴板

- 优先用 `ClipboardItem` + `toBlob`；失败时回退为下载。

---

## 6. 数据接口

### 6.1 复用现有 API

参见 `server/docs/api.md`：

- `GET  /api/runs/`
- `GET  /api/runs/{id}`
- `GET  /api/runs/{id}/logs`（SSE）
- `POST /api/runs/{id}/cancel`
- `POST /api/runs/`（触发运行）

### 6.2 V1 需新增的 API（后端可自由新增）

| 端点 | 说明 |
|---|---|
| `GET /api/pipelines/` | 列出已加载的流水线（name、file、task count、subpipeline count、最近运行摘要） |
| `GET /api/pipelines/{file}` | 返回该 YAML 解析后的完整 JSON（与 `PipelineYAML` schema 对齐） |

> 若后端暂不提供，V1 的索引面板可降级为：从 `/api/runs/` 聚合出流水线列表（不含未运行过的）。

### 6.3 鉴权

V1 **不启用** API Key 鉴权（假设后端 `api_key` 未配置或为空）。

- 前端 axios 拦截器**不注入** `X-API-Key`。
- 不提供 `/settings` 路由。
- V2 再视情况引入。

> 若后端实际开启了 `api_key`，需在请求 URL 拼接或环境变量注入，此为部署侧问题，不在 V1 范围。

### 6.4 CORS

- 后端需在 `taskpps.yaml` 或启动参数中允许前端源（如 `http://localhost:5173` 开发、`http://<server-host>` 生产）。

---

## 7. 非功能需求

| 维度 | 要求 |
|---|---|
| 浏览器 | Chrome / Edge / Firefox / Safari 近 2 年版本 |
| 响应式 | 桌面优先（≥1280px），不做移动端适配 |
| 主题 | **仅亮色**（暗色留待 V2） |
| 国际化 | 中文为主，预留英文（`ConfigProvider` + `zh_CN`） |
| 性能 | 100 节点规模的 DAG 渲染流畅（<16ms 帧） |
| 打包产物 | < 1.5 MB（gzip 后） |
| 部署 | Vite 构建产物由 `taskpps` Python 服务器以 `StaticFiles` 同进程挂载托管 |

---

## 8. 项目结构（建议）

```
web/
├── public/
├── src/
│   ├── api/                # axios 封装 + react-query hooks
│   ├── components/         # 通用 AntD 包装组件
│   ├── features/
│   │   ├── pipelines/      # 列表 / 画布 / 属性面板
│   │   └── runs/           # 表格 / 详情 / 日志
│   ├── layouts/            # ProLayout 外壳
│   ├── stores/             # zustand stores
│   ├── theme/              # AntD 主题配置
│   ├── utils/              # 工具函数
│   ├── routes.tsx
│   ├── main.tsx
│   └── App.tsx
├── index.html
├── package.json
├── tsconfig.json
├── vite.config.ts
└── README.md
```

后端侧（与前端构建协同）：

```
server/taskpps/
├── main.py                 # 启动时挂载 web/dist 为 StaticFiles（仅生产模式）
├── api/
│   ├── pipelines.py        # 新增：GET /api/pipelines/、GET /api/pipelines/{file}
│   └── ...（既有）
```

---

## 9. 验收标准（V1 完工定义）

1. 打开 `/`，能看到统计卡片、最近运行、健康状态。
2. 打开 `/pipelines`，能列出全部流水线，点击进入详情。
3. 详情页能看到 DAG 画布：缩放、平移、缩略图、节点拖拽、依赖箭头。
4. 点击节点，右侧属性面板正确显示该节点的所有字段。
5. 属性面板的宽度可拖拽调整，宽度偏好记忆；最小化/最大化按钮可用。
6. 点击「导出 PNG」可下载包含完整 DAG 的图片。
7. 点击「触发运行」可弹窗设置 params 并提交。
8. `/runs/:id` 页面能通过 SSE 实时接收日志，节点状态实时变色。
9. 页面在亮色主题下样式无错乱。
10. 后端启动后，Vite 构建产物可通过 `taskpps` 同进程访问（`http://host:26521/` 即可打开 UI）。

---

## 10. 决策记录（所有 Q 全部确认）

| 序号 | 问题 | 决策 |
|---|---|---|
| Q1 | V1 是否含编辑保存？ | **否**。V1 只读；底层按"查看 + 编辑"双模式设计，通过 `editable=false` 全局开关禁用写入路径，V2 打开开关即可。 |
| Q2 | 属性面板采用 A 还是 B？ | **A：可调分割栏**（AntD `Splitter`）。 |
| Q3 | V1 是否启用 API Key 鉴权？ | **否**。V1 不实现鉴权流程，依赖后端 `api_key` 未配置或部署侧解决。 |
| Q4 | 是否需要暗色主题？ | **否**。V1 仅亮色，留待 V2。 |
| Q5 | 部署方式 | **Vite 构建产物 + Python 服务器 `StaticFiles` 同进程挂载** |
| Q6 | 后端能否新增 `GET /api/pipelines/...`？ | **是**。后端可自由新增所需 API（`pipelines.py` 已在结构中标记）。 |
| Q7 | 是否需要多流水线对比 / 版本切换？ | **否**。不在 V1 范围。 |

> 全部 7 个问题已确认，文档可定稿进入实现阶段。

---

## 11. 风险与对策

| 风险 | 影响 | 对策 |
|---|---|---|
| `@ant-design/pro-flow` 文档不足 | 集成延期 | 准备回退方案：直接用 React Flow |
| 大量节点渲染卡顿 | 用户体验差 | 启用 React Flow 的 `onlyRenderVisibleElements`、按需虚拟化 |
| SSE 在反向代理下被缓冲 | 日志不实时 | 文档明确禁用 nginx proxy_buffering（V1 不经 Nginx，但保留此条以备部署变化） |
| CORS 未配置 | 前端无法调 API | V1 启动前与后端确认 CORS 白名单 |
| Python 静态文件与 SPA 路由冲突 | 刷新 404 | 后端 SPA fallback：未匹配 `/api/` 或静态资源时回退到 `index.html` |

> 文档结束。V1 进入实现阶段。
