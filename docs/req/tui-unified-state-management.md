# TUI 统一状态管理架构重构方案

## 问题背景

当前 TUI 架构基于 Bubble Tea 的 **Elm-like Model-Update-View 模式**，但存在严重的**状态分散管理**问题。

### 当前架构

```
┌─────────────────────────────────────────────┐
│                  Model (主状态)               │
│  runs[]  focusedPanel  rightTab  errMsg      │
│         ↓ 手动推送                            │
│  ┌──────────┐  ┌──────────┐  ┌───────────┐  │
│  │ RunList  │  │RunDetail │  │ LogViewer │  │
│  │ .runs[]  │  │ .run*    │  │ .content  │  │
│  │ .cursor  │  │ .cursor  │  │ .loading  │  │
│  └──────────┘  └──────────┘  └───────────┘  │
│         ↑ 各自独立状态，无统一入口              │
└─────────────────────────────────────────────┘
```

### 已发现的具体 Bug（P0-P1）

| 优先级 | Bug 描述 | 根本原因 |
|--------|---------|---------|
| P0 | 边框颜色状态泄漏：focusedPanel 变化后边框永远灰色 | 状态修改未回滚 |
| P0 | 状态栏 Runs 计数与列表数据不同步 | renderFooter 和 runList.View() 读取不同数据源 |
| P0 | 快捷键提示不随展开/折叠状态更新 | Footer 未感知 HasExpanded() 变化 |
| P0-P1 | 无数据变化时仍然完全重渲染 | 每次 TICK 都完整重建 View 字符串 |
| P1 | 详情视图无明显光标指示 | 详情视图渲染未与列表视图统一 |

### 根本原因

**所有问题指向同一个架构缺陷：没有一个统一的状态管理机制。** 三个核心反模式：

1. **State Leak（状态泄漏）**：组件修改了状态但没有被正确回滚
2. **State Desync（状态不同步）**：数据更新只触发了部分 UI 组件重新渲染
3. **State Disconnect（状态脱离）**：视图状态（展开/折叠）与快捷键提示状态没有关联

---

## 重构目标

引入一个不可变的 `AppState` 结构体，作为**唯一的数据真相源**（Single Source of Truth），实现：

- 所有组件从同一个 `AppState` 派生视图
- 所有状态变更通过 `Update()` 产生一个新的 `AppState`
- `View()` 变为纯函数，相同输入必然产生相同输出
- `AppState` 可比较 → 相同状态自动跳过渲染

---

## 架构设计

### 数据流

```
用户输入 / 网络事件
        │
        ▼
   ┌──────────────────────┐
   │  Update(msg, state)  │ ──→ (newState, cmd)
   └──────────────────────┘
        │
        ▼
   ┌──────────────────────┐
   │   View(state)        │ ──→ string
   │   (纯函数，无副作用)   │
   └──────────────────────┘
        │
        ▼
     终端输出
```

### AppState 结构

```go
// AppState 是不可变的全局状态快照
// 每次 Update() 都返回一个新的 AppState
type AppState struct {
    // ── 数据层
    Runs     []models.Run
    RunsHash string

    SelectedRun  *models.Run
    RunHash      string
    SelectedTask *models.TaskRun

    // ── 交互层
    FocusedPanel PanelFocus
    RightTab     RightPanelTab

    // ── 组件渲染状态（从数据层和交互层派生）
    RunListCursor  int
    DetailExpanded map[int]bool
    SubExpanded    map[string]bool
    DetailCursor   int

    // ── 日志
    LogContent  string
    LogLoading  bool

    // ── 全局
    ErrorMsg string
    Quit     bool

    // ── 布局
    Width  int
    Height int
    Ready  bool
    Dims   layoutDims
}
```

### View 层：纯函数渲染

```go
// 组件 View 从 Model 方法变为纯函数
func renderRunList(state AppState) string
func renderRunDetail(state AppState) string
func renderLogViewer(state AppState) string

// viewport 滚动逻辑也是纯函数
func runListCursorLine(state AppState) int
func detailCursorLine(state AppState) int
```

---

## 分阶段实施计划

### Phase 1：引入 AppState，保持向后兼容

**目标**：最小破坏性变更，建立 AppState 作为第二份"真相源"，验证一致性。

**步骤**：
1. 新建 `cli/tui/state.go`，定义 `AppState` 结构体
2. 在 `Model` 中添加 `state AppState` 字段
3. 已完成的 handler（`runsFetchedMsg`、`runFetchedMsg` 等）中**双写**：同时更新 AppState 和旧的组件字段
4. 添加一个 `assertStateConsistency()` 调试函数，运行时检测 AppState 和旧字段是否一致

**文件变更**：
- 新增 `cli/tui/state.go`
- 修改 `cli/tui/model.go`：添加 state 字段
- 修改 `cli/tui/update.go`：msg handler 双写
- 不影响 `view.go` 和 `components/`

**风险**：极低，AppState 是纯增量代码。

---

### Phase 2：组件去模型化

**目标**：将 `RunListModel`、`RunDetailModel`、`LogViewerModel` 从 Bubble Tea 子模型变为纯渲染函数。

**步骤**：
1. 将 `RunListModel.Update()` → `updateRunList(state AppState, msg tea.KeyMsg) AppState`
2. 将 `RunListModel.View()` → `renderRunList(state AppState) string`
3. 将 `RunDetailModel.Update()` → `updateRunDetail(state AppState, msg tea.KeyMsg) AppState`
4. 将 `RunDetailModel.View()` → `renderRunDetail(state AppState) string`
5. 将 `LogViewerModel.View()` → `renderLogViewer(state AppState) string`
6. `Update()` 改为调用纯函数更新 AppState：
   ```go
   func (m Model) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
       newState, cmd := m.state.Update(msg)
       m.state = newState
       return m, cmd
   }
   ```

**文件变更**：
- 重写 `cli/tui/components/run_list.go`：移除 Model 结构体，导出纯函数
- 重写 `cli/tui/components/run_detail.go`：同上
- 重写 `cli/tui/components/log_viewer.go`：同上
- 重写 `cli/tui/view.go`：从 AppState 渲染

**风险**：中。组件代码变化大，但都是**机械性转换**（方法 → 函数），逻辑不变。

---

### Phase 3：清理冗余

**目标**：删除旧代码，统一数据流。

**步骤**：
1. 从 `Model` 中删除旧的组件字段（`runList`、`runDetail`、`logViewer`）
2. 删除 `components/` 中的 `Model` 结构体定义
3. 移除 `view.go` 中的视图缓存包变量（AppState 天然可比较）
4. 移除 `assertStateConsistency()` 调试函数
5. `View()` 完全使用 `renderFromState()`
6. 更新所有测试：构造 AppState 快照代替构造完整 Model

**文件变更**：
- 修改 `cli/tui/model.go`：删除组件字段
- 修改 `cli/tui/view.go`：移除缓存变量
- 删除 `cli/tui/components/*.go` 中的 Model 声明
- 更新 `cli/tui/golden_test.go` 和所有测试

**风险**：高。测试需要全面重写。建议 Phase 2 完成后先过一遍全部测试再做 Phase 3。

---

## 架构对比

| 维度 | 当前方案 | 新方案 |
|------|---------|--------|
| **数据源** | 3 处（m.runs, runList.runs, view 中直接读） | 1 处（AppState.Runs） |
| **状态泄漏** | 组件各自持有状态，回滚困难 | AppState 不可变，每次是完整快照 |
| **数据重复** | m.runs 和 m.runList.runs 两份 | 只有 state.Runs |
| **渲染条件** | 每次都重建 View 字符串 | AppState 可比较 → 相同状态跳过 |
| **调试** | 需要检查 4 个结构体 | 只需看 AppState 一个地方 |
| **测试** | 需要构造完整 Model + 子组件 | 只需构造 AppState 快照 |
| **代码量估计** | ~1200 行 | ~950 行（减少约 20%） |

---

## 风险评估

| 风险项 | 等级 | 缓解措施 |
|--------|------|---------|
| Phase 1 引入新字段与现有逻辑冲突 | 低 | 纯增量代码，先双写后切流 |
| Phase 2 viewport 滚动逻辑迁移遗漏 | 中 | viewport 是 bubbles 库组件，迁移是参数重组而非重写 |
| Phase 3 测试重写工作量大 | 中 | 先在 Phase 2 保留旧测试，Phase 3 用 TDD 方式重写 |
| 重构期间引入新 Bug | 中 | 每个 Phase 结束后运行全量测试 + 手动 watch 测试 |

---

## 建议执行路径

1. **立即执行 Phase 1**（工作量约 1-2 小时）：风险最低，建立 AppState 基础设施
2. **评估后执行 Phase 2**（工作量约 3-4 小时）：阶段性交付，每个组件独立转换
3. **按需执行 Phase 3**（工作量约 2-3 小时）：纯清理工作，不影响功能

总工作量估算：6-9 小时，分 3 次可交付增量。
