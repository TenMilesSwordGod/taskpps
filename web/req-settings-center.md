# taskpps 设置中心（Settings Center）需求规格说明书（V2）

> 项目：taskpps（Task Pipeline Processing System）Web 控制台
> 版本：V2（设置中心）
> 作者：产品设计（PM）
> 最后更新：2026-07-14
> 关联文档：`web/req.md`（V1 需求规格，其中第 3 章明确「V1 不做 /settings」）

---

## 1. 概述

### 1.1 背景

V1 已交付仪表盘、流水线、运行历史三大模块，并将「插件」「服务器」作为两个**独立顶级导航项**直接暴露（见 `web/src/layouts/AppLayout.tsx` 的 `menuRoutes`：`/plugins`、`/servers`）。随着系统接入的**项目（Project）**数量增长，出现以下问题：

1. **项目无法在 UI 上启用/停用**：后端 `Project` 模型已具备 `active` 字段、`list_projects(active_only=True)` 默认按启用过滤、`update_project()` 已支持更新，但**缺少切换 `active` 的 API 与前端页面**。当前停用项目只能改数据库，运维门槛高。
2. **配置类入口分散**：「插件」「服务器」本质是"系统配置/资源"而非"业务视图"，与仪表盘、流水线等"业务数据视图"平级放在导航栏，认知负荷大、定位困难。
3. **缺少统一设置心智**：用户期望有一个集中入口管理"系统级开关与资源"，而非散落在各处。

### 1.2 V2 目标

新增一个**设置中心**，作为所有"系统级配置与资源"的统一入口，包含三个 Tab：

1. **项目**：以列表 + 开关形式管理各项目的**启用/停用**（核心新增能力）。
2. **插件**：迁入现有插件管理能力（类型筛选、启用开关、详情查看）。
3. **服务器**：迁入现有服务器（Agent）管理能力（分组、在线状态、探测、REPL），V1 **只读、不做启用/停用**。

> 设置中心的定位 = "系统配置 + 资源清单"，与"业务数据视图"（仪表盘/流水线/运行历史）在导航上明确分层。

### 1.3 V2 非目标（明确不做）

- 服务器（Agent）的启用/停用开关（V1 仅迁入只读视图，详见 Q1 决策）。
- 项目的新增/删除/重命名 CRUD（V1 仅做启用/停用；项目注册/删除仍走原 API 与 CLI）。
- 应用级配置（`taskpps.yaml` 的 `Settings` 模型，如 locale/executor 等）的可视化编辑。
- 用户、角色、权限、审计日志。
- 暗色主题、移动端适配（沿用 V1 约束）。

---

## 2. 信息架构与导航

### 2.1 导航变更

废弃原有的「插件」「服务器」两个顶级导航项，**新增「设置中心」一个顶级项**，内部用 Tabs 承载三个子模块。

```
侧边栏（AppLayout menuRoutes）变更为：
  /            仪表盘
  /pipelines   流水线
  /runs        运行历史
  /settings    设置中心   ← 新增（SettingOutlined 图标）
```

路由表（`web/src/routes.tsx`）变更：

```
/                      仪表盘
/pipelines             流水线索引
/pipelines/:projectId/:definitionId   流水线详情
/runs                  运行历史
/runs/:id              运行详情
/settings              设置中心（容器 + Tabs）
  ├─ /settings/projects   项目（默认 Tab）
  ├─ /settings/plugins    插件（复用）
  └─ /settings/servers    服务器（复用）
```

> 原 `/plugins`、`/servers` 路由**废弃**：`/settings` 加载后默认渲染项目 Tab；通过 `/settings/plugins`、`/settings/servers` 深链可直达对应 Tab。前端 `AppLayout` 菜单移除旧两项，仅保留「设置中心」。

### 2.2 设置中心页面结构

```
┌─────────────────────────────────────────────────────────────┐
│  面包屑  / 设置中心                                          │
├─────────────────────────────────────────────────────────────┤
│  [ 项目 ]  [ 插件 ]  [ 服务器 ]        ← AntD Tabs（顶部）     │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│   当前 Tab 内容区（懒加载，复用原 feature 组件）              │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

- Tabs 用 AntD `Tabs`，每个 Tab 内容区**复用**现有 `features/plugins/PluginListPage` 与 `features/servers/ServersPage` 组件（避免重复实现）。
- 项目 Tab 为本次**全新实现**。

---

## 3. 功能详细说明

### 3.1 项目 Tab（核心新增）

#### 3.1.1 展示内容

AntD `Table` 列出全部已注册项目（含被停用的），列定义：

| 列 | 说明 | 来源 |
|---|---|---|
| 名称 | `Project.name` | DB |
| 工作目录 | `Project.workdir` | DB |
| 状态 | **启用/停用 标签 + Switch 开关** | `Project.active` |
| 注册时间 | `registered_at` | DB |
| 最近使用 | `last_used_at` | DB |
| 操作 | 查看详情（可选，V1 可先留空或仅展示） | — |

#### 3.1.2 启用 / 停用 交互

- 每行「状态」列提供 `Switch` 开关。
- 关闭开关 = 停用项目；打开 = 启用项目。
- 切换时调用后端接口（见 4.1），成功后本地乐观更新行状态。
- **停用需二次确认**：弹出 `Modal.confirm`，文案提示"停用后该项目下的流水线、服务器、插件将从业务视图中隐藏，但数据保留"，用户确认后才真正下发。

#### 3.1.3 停用后的系统行为（产品规则，需与后端对齐）

- 业务视图（仪表盘统计、流水线列表、服务器列表、插件列表）**仅展示启用项目**（`list_projects(active_only=True)` 已支持）。
- 历史运行记录（`/runs`）**仍保留**停用项目的记录（历史不应被隐藏，仅"当前可操作资源"被过滤）。
- 停用不影响磁盘 `workdir` 与已落库数据，可随时重新启用。

#### 3.1.4 顶部工具栏

- 搜索框（按名称/工作目录过滤）
- 刷新按钮
- （可选 V1+）「仅看已停用」筛选 Segmented

### 3.2 插件 Tab（迁入复用）

- **直接复用** `features/plugins/PluginListPage`：类型 `Segmented` 筛选（触发器/通知器/执行器）、搜索框、表格「启用」`Switch`（调 `PATCH /api/plugins/{name}/toggle`）、详情弹窗。
- 仅做"搬家"，**不改动任何业务逻辑**，保证行为与原 `/plugins` 页完全一致。
- 顶部增加一句话说明："插件为全局资源，启用/停用即时生效"。

### 3.3 服务器 Tab（迁入复用，只读）

- **直接复用** `features/servers/ServersPage`：按项目分组展示 Agent 卡片、在线/离线筛选、搜索、探测主机信息、REPL。
- V1 **只读**：不做服务器的启用/停用开关（决策见 Q1）。复用现有只读能力即可。
- 顶部说明："服务器（执行节点）配置于各项目 `agents/` 目录，此处为只读资源清单"。

---

## 4. 数据接口

### 4.1 V2 需新增 / 变更的 API

| 端点 | 方法 | 说明 | 现状 |
|---|---|---|---|
| `/api/projects/{id}` | **PATCH** | 更新项目字段，重点支持切换 `active` | **缺失**（模型与 `update_project()` 已就绪，补端点即可） |
| `/api/projects/` | GET | 列出**全部**项目（含停用），供设置中心展示 | 已有，但默认 `active_only=True`，需新增 `active_only=false` 参数或独立端点 |

> 其余接口（插件 `GET /api/plugins/`、`PATCH /api/plugins/{name}/toggle`；服务器 `GET /api/agents/all`）均**已就绪，直接复用**。

### 4.2 接口细节补充

- `PATCH /api/projects/{id}` 请求体示例：`{ "active": false }`。
- `GET /api/projects/` 需支持返回停用项，建议在 `ProjectRepository.list_projects` 增加 `active_only: bool = True` 参数透传，或新增 `include_inactive` 参数，由设置中心显式请求全量。
- 统一返回 `ProjectResponse`（已含 `active` 字段），前端无需新增类型。

---

## 5. 前端影响面（实现指引，供研发参考）

> 本节为研发实现路径提示，非产品验收项。

- **路由**：`web/src/routes.tsx` 新增 `/settings` 懒加载页（`SettingsCenterPage`），内部 `Tabs` + 三个子视图；删除/重定向 `/plugins`、`/servers`。
- **布局**：`web/src/layouts/AppLayout.tsx` 的 `menuRoutes` 移除「插件」「服务器」，新增「设置中心」（`SettingOutlined`）。
- **项目 Tab 新组件**：`features/settings/ProjectsTab.tsx` + `api/projects.ts` 增加 `useUpdateProject`（react-query `useMutation` 调 PATCH）。
- **复用**：`features/plugins/PluginListPage`、`features/servers/ServersPage` 原样 import 进对应 Tab，无需改造。
- **ProjectContext**：`web/src/contexts/ProjectContext.tsx` 当前已定义但未挂载，可借设置中心统一接入"当前选中项目"状态（可选优化，非 V1 必做）。

---

## 6. 非功能需求

| 维度 | 要求 |
|---|---|
| 主题 | 亮色（与 V1 一致） |
| 响应式 | 桌面优先（≥1280px），不做移动端 |
| 国际化 | 中文为主，预留英文 |
| 性能 | 三个 Tab 懒加载，切换不重复拉取已加载数据（react-query 缓存复用） |
| 导航一致性 | 设置中心内三个 Tab 的列表/筛选/操作交互风格与原页面保持一致，用户无割裂感 |

---

## 7. 验收标准（V2 完工定义）

1. 侧边栏出现「设置中心」入口，原「插件」「服务器」入口消失。
2. 进入 `/settings`，默认显示「项目」Tab，列出全部项目（含停用项），并显示启用/停用状态。
3. 关闭某项目开关，弹确认框，确认后该项目状态更新为"停用"，且**业务视图（仪表盘/流水线/服务器/插件）中该项目资源不再出现**，历史运行记录仍保留。
4. 重新打开开关，项目恢复出现在业务视图。
5. 点击「插件」Tab，功能与原 `/plugins` 页完全一致（筛选、启用开关、详情）。
6. 点击「服务器」Tab，功能与原 `/servers` 页完全一致（分组、在线状态、探测、REPL）。
7. 通过 `/settings/plugins`、`/settings/servers` 深链可直达对应 Tab。
8. 三个 Tab 切换流畅，无重复网络请求造成的卡顿。

---

## 8. 决策记录（Q&A）

| 序号 | 问题 | 决策 |
|---|---|---|
| Q1 | 服务器移入设置中心后是否支持启用/停用？ | **否**。V1 仅迁入只读视图，复用现有 `ServersPage`；服务器启用/停用需后端新增持久化（当前 Agent 仅 YAML 配置、无 DB 模型），留待后续迭代。 |
| Q2 | 原「插件」「服务器」顶级菜单如何处理？ | **合并为 `/settings` 子路由**。废弃原 `/plugins`、`/servers` 顶级入口，统一收敛到设置中心 Tabs。 |
| Q3 | 项目 Tab 是否支持新增/删除项目？ | **否**。V1 仅做启用/停用；项目注册/删除沿用既有 API 与 CLI。 |
| Q4 | 停用项目是否影响历史运行记录？ | **不影响**。历史运行（`/runs`）保留全量；仅"当前可操作资源"按启用状态过滤。 |
| Q5 | 设置中心是否需要应用级配置（taskpps.yaml）编辑？ | **否**。V1 不做应用级配置 UI。 |

---

## 9. 风险与对策

| 风险 | 影响 | 对策 |
|---|---|---|
| `PATCH /api/projects/{id}` 端点缺失，需后端补 | 阻塞项目开关 | 后端改动极小（复用 `update_project()`），优先排期 |
| 停用项目后业务视图过滤逻辑不统一 | 出现"幽灵"资源 | 明确以 `list_projects(active_only=True)` 为唯一过滤口径，跨模块对齐 |
| 复用 `PluginListPage`/`ServersPage` 时组件耦合路由 | 搬移后路由错乱 | 改造为纯展示组件，去掉内部硬编码导航，由设置中心外壳接管路由 |
| 用户误停用项目导致资源"消失"引发困惑 | 支持工单 | 停用二次确认 + 业务视图提供"含停用项目"提示/入口（可选） |
| 历史运行记录与停用项目引用不一致 | 数据矛盾 | 运行记录存 `project_id` 快照，停用仅隐藏当前资源，不删历史 |

---

> 文档结束。待 Q1–Q5 决策确认后，本需求进入实现排期阶段。
