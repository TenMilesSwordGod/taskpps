# ppsctl TUI 测试需求文档

> 目标: 构建一套分层防御的 TUI 稳定性测试体系, 系统性覆盖 "UI 错位/渲染混乱/并发崩溃" 等典型问题, 将缺陷发现在测试阶段而非生产环境。

---

## 目录

1. [测试架构总览](#1-测试架构总览)
2. [测试分层策略](#2-测试分层策略)
   - [L1: 组件单元测试](#l1-组件单元测试)
   - [L2: 边界条件测试](#l2-边界条件测试)
   - [L3: 布局与渲染快照测试 (Golden Files)](#l3-布局与渲染快照测试-golden-files)
   - [L4: 交互流程集成测试](#l4-交互流程集成测试)
   - [L5: 模糊测试 (Fuzzing)](#l5-模糊测试-fuzzing)
   - [L6: 终端模拟器兼容性测试](#l6-终端模拟器兼容性测试)
3. [测试基础设施](#3-测试基础设施)
4. [现有测试覆盖评估与差距分析](#4-现有测试覆盖评估与差距分析)
5. [测试用例清单](#5-测试用例清单)
6. [实施路线图](#6-实施路线图)

---

## 1. 测试架构总览

### 1.1 分层防御模型

```
┌──────────────────────────────────────────────────┐
│  L6  终端兼容性测试 (bubbleterm CI矩阵)           │  ← 真实环境
├──────────────────────────────────────────────────┤
│  L5  模糊测试 (go test -fuzz)                     │  ← 未知极端输入
├──────────────────────────────────────────────────┤
│  L4  交互流程集成测试 (Update + View 全链路)       │  ← 用户行为模拟
├──────────────────────────────────────────────────┤
│  L3  布局快照测试 (Golden Files)                   │  ← 渲染输出回归
├──────────────────────────────────────────────────┤
│  L2  边界条件测试 (窗口/文本/并发)                 │  ← 崩溃预防
├──────────────────────────────────────────────────┤
│  L1  组件单元测试 (状态/方法/输出)                 │  ← 基础正确性
└──────────────────────────────────────────────────┘
```

### 1.2 被测组件

| 组件 | 源文件 | 职责 |
|:--|:--|:--|
| `Model` (顶层) | `tui/model.go`, `tui/view.go`, `tui/update.go` | 总控 TUI: 初始化、消息路由、布局、渲染 |
| `RunListModel` | `tui/components/run_list.go` | 左侧运行列表: 光标导航、状态渲染、截断 |
| `RunDetailModel` | `tui/components/run_detail.go` | 右侧运行详情: 任务树展开/折叠、状态高亮 |
| `LogViewerModel` | `tui/components/log_viewer.go` | 日志查看器: 滚动、行缓冲、自动滚底 |
| Styles + Tooling | `tui/components/styles.go` | 颜色/图标/进度条/截断工具函数 |

---

## 2. 测试分层策略

### L1: 组件单元测试

> 目标: 验证每个 Bubble Tea 组件的基本行为——Init、Update、View 方法在不同状态组合下的正确性。

#### 2.1.1 RunListModel 测试需求

| 测试场景 | 输入 | 预期输出/行为 |
|:--|:--|:--|
| 空列表渲染 | `SetRuns(nil)` | View 包含 `"(no runs)"` |
| 正常列表渲染 | 3 个 Run (不同状态) | View 包含 ID 前缀、管道名、状态图标 |
| 光标上下边界 | `cursor=0` + `KeyUp` | 光标停留在 0 |
| 光标下下边界 | `cursor=len-1` + `KeyDown` | 光标停留在 `len-1` |
| 光标溢出回退 | `cursor=5`, `SetRuns([2 runs])` | `cursor` 自动调整为 1 |
| 超窄宽度截断 | `SetSize(20, 10)` + 超长 ID 和管道名 | View 不 panic、无溢出序列 |
| 所有状态渲染 | pending/running/success/failed/cancelled 各一个 | 每种状态图标正确 (○/▶/✔/✘/✕) |
| SelectedRun 空列表 | `runs=[]` | `SelectedRun()` 返回 nil |
| 非法 SetCursor | `SetCursor(-1)`, `SetCursor(1000)` | 光标不变、不 panic |

#### 2.1.2 RunDetailModel 测试需求

| 测试场景 | 输入 | 预期输出/行为 |
|:--|:--|:--|
| nil run 渲染 | `SetRun(nil)` | View 包含 `"select a run"` 提示 |
| 正常详情渲染 | run 含 3 个 task | View 包含 ID、管道名、任务列表 |
| 空任务渲染 | run.Tasks=[] | View 包含 `"no tasks"` |
| 展开单个任务 | `expanded[0]=true` | View 包含 taskType、exit code 详情行 |
| 展开含时间戳的任务 | 含 StartedAt/FinishedAt | View 包含 `"start:"` 和 `"end:"` |
| 展开/折叠全部 | `ExpandAll()` / `CollapseAll()` | `HasExpanded()` 返回正确状态 |
| 光标越界回退 | `cursor=10`, `SetRun([2 tasks])` | cursor 调整为 2 (超出调整为 len) |

#### 2.1.3 LogViewerModel 测试需求

| 测试场景 | 输入 | 预期输出/行为 |
|:--|:--|:--|
| 空日志渲染 | 无 content、未 SetSize | View 包含 `"(no output)"` |
| 短日志渲染 | `SetContent("hello")` 、 `SetSize(80,10)` | View 包含 `"hello"` |
| 超长内容渲染 | 5000+ 行 | 缓冲区不溢出、滚动正常工作 |
| 追加内容 | `AppendContent("a")` + `AppendContent("b")` | content = `"a\nb"` |
| PageUp/Down 滚动 | content 20 行、size 10 行 | 可见区域正确移动 |
| Home/End 滚动 | 如上 | Home 跳到顶部、End 跳到底部 |
| 非 key 消息不影响内容 | `WindowSizeMsg` | content 不变 |
| SetSize 后 ready=true | `SetSize(80,20)` | `m.ready == true` |

#### 2.1.4 Styles 工具函数测试需求

| 测试场景 | 输入 | 预期输出 |
|:--|:--|:--|
| StatusIcon 所有状态 | "running"/"pending"/"success"/"failed"/"skipped"/"cancelled" | ▶/○/✔/✘/⊘/✕ |
| StatusIcon 未知状态 | "unknown" | "?" |
| TruncateLine 正常 | "hello world", 20 | "hello world" |
| TruncateLine 截断 | "hello world", 5 | "he..." |
| TruncateLine 极小宽度 | "abc", 1 | "" |
| MakeProgressBar 全完成 | done=5, running=0, total=5, barW=5 | "█████" (绿色) |
| MakeProgressBar 混合 | done=3, running=1, total=5, barW=5 | "███▓░" |
| MakeProgressBar 零总计 | total=0 | "" |
| FormatTime nil | nil | "-" |
| FormatTime 正常 | "2024-01-15T10:30:00Z" | "01-15 10:30" |

---

### L2: 边界条件测试

> 目标: 在极端条件 (窗口尺寸、文本长度、并发) 下验证程序不崩溃、不产生异常输出。

#### 2.2.1 窗口尺寸边界

| 测试场景 | 参数 | 验证点 |
|:--|:--|:--|
| 极小窗口 | `WindowSizeMsg{Width: 10, Height: 5}` | View 不 panic, 不产生超长行 |
| 20x8 小窗口 | `WindowSizeMsg{Width: 20, Height: 8}` | 布局计算不产生负数尺寸 |
| 正常窗口 | `WindowSizeMsg{Width: 80, Height: 24}` | left=28%, right=72% 比例 |
| 宽窗口 | `WindowSizeMsg{Width: 240, Height: 60}` | left≥14, right≥20 最小约束满足 |
| 动态缩放链 | 80→20→240→80→10→200 连续 resize | 每次 resize 后 View 都可渲染 |
| 首次 resize 触发 ready | 模型 received 首个 WindowSizeMsg | `m.ready` 变为 true |
| 非标准尺寸 | `WindowSizeMsg{Width: 0, Height: 0}` | 不 panic, View 有降级输出 |
| 单列布局触发 | `Width < 42` 左右最小宽度之和+分隔符+边框 | 布局参数 clamping 生效 |

#### 2.2.2 文本内容边界

| 测试场景 | 输入 | 验证点 |
|:--|:--|:--|
| 超长 Run ID | `"abcdefghijklmnopqrstuvwxyz1234567890"` | RunList View 截断正确、包含 `"..."` |
| 超长管道名 | `strings.Repeat("X", 200)` | 不换行溢出 |
| 超长错误消息 | `errMsg` = 500 字符 | Footer 截断为 20 字符 + `"ERR:"` |
| 空 run 列表 | `runs = []` | View 显示空状态提示 |
| nil tasks 切片 | `Run.Tasks = nil` | RunDetail 不 panic |
| 空字符串管道名 | `PipelineName = ""` | 渲染不崩溃 |
| 单字符 ID | `ID = "a"` | 显示正常、StatusIcon 不被截断 |
| 超长日志行 | 单行 1000+ 字符、无换行 | LogViewer 不水平溢出 |

#### 2.2.3 并发稳定性测试

| 测试场景 | 方法 | 验证点 |
|:--|:--|:--|
| `go test -race` 基础 | 对所有 `*_test.go` 启用 race detector | 无 data race 报告 |
| 批量消息注入 | 并行发送 `runsFetchedMsg` + `runFetchedMsg` + `tickMsg` | 无竞态、状态一致 |
| 高频率 tick | 模拟 100 次 `tickMsg` Update 调用 | 无 goroutine 泄漏 |
| 状态合并并发 | 并发调用 `mergeRuns()` | 无 data race |

#### 2.2.4 状态机边界

| 测试场景 | 输入序列 | 预期行为 |
|:--|:--|:--|
| 未 ready 时按键 | 未收到 WindowSizeMsg 前按 q | View 显示 "Initializing..." 后 quit |
| quit=true 后 View | `m.quit = true` | `View()` 返回 "" |
| 面板焦点边界 | RunList 上按 `h`、RightPanel 上按 `l` | 焦点不变 |
| 空管道的 p/n 导航 | `runs=[]` 时按 p 或 n | 不崩溃、无操作 |
| 空任务的 Enter | RunDetail 无 task 时按 Enter | 不切换 tab |
| 刷新键双重触发 | `r` 键 | 同时返回 fetchRuns + fetchRun 两个 cmd |
| Esc 多层回退 | Logs→Detail→RunList→Quit | 步步回退正确 |

---

### L3: 布局与渲染快照测试 (Golden Files)

> 目标: 通过文本快照 (Golden Files) 捕获任何意外的 UI 输出变化, 让布局回归一目了然。

#### 2.3.1 快照测试设计原则

1. **确定性输出**: 测试中禁用颜色 (可通过 lipgloss `SetColorProfile(ascii)` 或注入 `nilRenderer`)、固定时间戳、固定窗口尺寸
2. **可重复**: 每次运行产生相同输出, 不受环境变量和 CI 机器影响
3. **可审阅**: 更新 Golden File 后必须 `git diff` 审阅变更

#### 2.3.2 快照场景矩阵

| 场景 | 窗口 | runs 数据 | 焦点 | 右面板 tab | Golden 文件名 |
|:--|:--|:--|:--|:--|:--|
| 初始化状态 | 120x40 | 0 | RunList | - | `init_loading.golden` |
| 空运行列表 | 120x40 | 0 (ready) | RunList | Detail | `empty_runs.golden` |
| 3 个 run 正常 | 120x40 | 3 runs | RunList | Detail | `normal_runs_focus_left.golden` |
| 选中 run 详情 | 120x40 | 3 runs | RightPanel | Detail (expanded) | `run_detail_expanded.golden` |
| 日志标签页 | 120x40 | 3 runs | RightPanel | Logs | `log_viewer.golden` |
| 窄终端 | 80x25 | 3 runs | RunList | Detail | `narrow_terminal.golden` |
| 宽终端 | 200x50 | 5 runs | RightPanel | Detail | `wide_terminal.golden` |
| 错误状态 | 120x40 | 1 run + errMsg | RunList | Detail | `error_state.golden` |
| 多管道名混排 | 120x40 | 5 runs (different names) | RunList | Detail | `mixed_pipelines.golden` |
| 多种任务状态 | 120x40 | 1 run (5 tasks all statuses) | RightPanel | Detail | `all_task_statuses.golden` |

#### 2.3.3 Golden File 测试方法

```go
// 使用简单字符串比对或第三方库如 gotest.tools/v3/golden
func TestGoldenSnapshot(t *testing.T) {
    tests := []struct {
        name     string
        setup    func(m *Model)
        golden   string
    }{/* ... */}

    for _, tt := range tests {
        t.Run(tt.name, func(t *testing.T) {
            m := makeTestModel()
            // 1. 强制确定性配置
            lipgloss.SetColorProfile(termenv.Ascii)
            m.ready = true
            m.width, m.height = 120, 40
            m.resizeComponents()
            tt.setup(&m)

            got := m.View()
            // 2. 去除 ANSI 转义序列 确保纯文本比对
            got = stripANSI(got)

            // 3. 与 Golden File 比对
            golden.Assert(t, got, "tui/testdata/"+tt.golden)
        })
    }
}
```

更新 Golden Files 命令: `go test ./tui/ -update`

#### 2.3.4 快照去噪 (De-noising)

| 噪声源 | 处理方式 |
|:--|:--|
| ANSI 颜色/样式转义序列 | `stripANSI()` 或设置 `termenv.Ascii` |
| 动态运行 ID | 使用 mock 数据, 固定 ID 字符串 |
| 时间戳 | `FormatTime` 传入固定时间字符串 |
| 动态管道名 | 测试中固定 `PipelineName` |
| 运行时状态 (2s 刷新) | 将 `refreshInterval` 替换为常量 |
| 光标位置标记 | View 中通常不含光标, 无需处理 |

#### 2.3.5 Golden Files 维护规范

- 存储在 `cli/tui/testdata/` 目录
- 文件命名: `{TestName}_{scenario}.golden`
- 提交 PR 包含 `.golden` 变更时, 必须在 PR 描述中附上 `diff` 输出
- 仅通过 `go test -update` 更新, 严禁手动编辑

---

### L4: 交互流程集成测试

> 目标: 模拟真实用户在 TUI 中的完整操作序列, 验证 Update→View 全链路的正确性。

#### 2.4.1 关键交互流程

| 流程 | 操作序列 | 验证点 |
|:--|:--|:--|
| **浏览运行列表** | init → ↓↓→ Enter → 查看详情 | focus 转移、fetchRun 被调用 |
| **切换标签页** | Enter 进入 Detail → `t` 切换到 Logs → `t` 切回 Detail | tab 切换正确、fetchLogs 被调用 |
| **任务展开/折叠** | 进入 Detail → `c` 展开 → `c` 折叠 | `HasExpanded()` 状态正确 |
| **日志滚动** | 进入 Logs → PgDown → PgDown → PgUp → Home | 滚动位置正确 |
| **管道导航** | 进入 RightPanel → `n` → `n` → `p` | SelectedRun 切换、fetchRun 触发 |
| **Esc 多层回退** | RightPanel(Logs) → Esc → RightPanel(Detail) → Esc → RunList → Esc → Quit | 每层行为正确 |
| **刷新流程** | 按 `r` → 数据更新 | fetchRuns + fetchRun 同时返回 |
| **错误恢复** | fetchRuns 返回 error → 按 `r` 重试 | errMsg 更新、重试后清除 |
| **自动聚焦目标** | `NewModel(c, "run-123")` → init 获取 runs 包含 "run-123" | 自动跳到 RightPanel Detail |
| **目标 run 不存在** | `NewModel(c, "missing")` → runs 不包含 | targetRunID 保留、不崩溃 |

#### 2.4.2 Mock Client 接口

为支持完整的集成测试, 需要抽象 HTTP Client, 使其可在测试中替换为 mock:

```go
// client/interface.go (建议新增)
type ClientInterface interface {
    ListRuns(pipeline string, status string, limit int) (*models.RunListResponse, error)
    GetRun(id string) (*models.Run, error)
    GetLogs(runID, taskName string, tail int) (map[string]string, error)
    CancelRun(id string) error
    // ... 其他方法
}
```

当前 `Model` 直接持有 `*client.Client`, 改持接口后可注入 mock 实现。

---

### L5: 模糊测试 (Fuzzing)

> 目标: 用自动生成的随机输入发现人力编写的测试覆盖不到的崩溃路径。

#### 2.5.1 Fuzz 目标

| 函数 | Fuzz 入口 | 验证内容 |
|:--|:--|:--|
| `Model.Update()` | 随机 `FuzzMsg` 包装任意 `string` 作为 KeyMsg Runes | 不 panic |
| `TruncateLine(line, width)` | 随机 line + width (含负数) | 返回值长度 ≤ width 或符合截断规则 |
| `MakeProgressBar(done, run, total, barW)` | 随机 4 个 int (含负数、零) | 不 panic、返回合理的条形 |
| `FormatTime(t)` | 随机 string 指针 | 不 panic |
| `StatusIcon(status)` | 随机 string | 返回定义内的图标或 "?" |
| `mergeRuns(existing, new)` | 随机 Run 切片 | 不 panic、ID 匹配的行保留 Tasks |

#### 2.5.2 Fuzz 测试示例

```go
func FuzzModelUpdate(f *testing.F) {
    // 种子语料
    f.Add("q")
    f.Add("\x00")
    f.Add(strings.Repeat("a", 1000))

    f.Fuzz(func(t *testing.T, input string) {
        m := makeTestModel()
        m.ready = true
        m.width, m.height = 120, 40
        m.resizeComponents()

        msg := tea.KeyMsg{Type: tea.KeyRunes, Runes: []rune(input)}
        newM, _ := m.Update(msg)
        // 核心: 确保 View 不会 panic
        _ = newM.View()
    })
}

func FuzzTruncateLine(f *testing.F) {
    f.Add("hello", 10)
    f.Add("hello", 0)
    f.Add("hello", -1)

    f.Fuzz(func(t *testing.T, line string, width int) {
        result := components.TruncateLine(line, width)
        if width > 0 && len(line) <= width {
            if result != line {
                // 当原始行 ≤ 宽度时, 不应截断
                t.Skip() // fuzzy 容忍
            }
        }
        _ = result
    })
}
```

运行: `go test -fuzz=FuzzModelUpdate -fuzztime=30s ./tui/`

---

### L6: 终端模拟器兼容性测试

> 目标: 验证 ANSI 转义序列在不同终端模拟器中的渲染一致性。

#### 2.6.1 测试策略

| 方法 | 适用场景 | 成本 |
|:--|:--|:--|
| **bubbleterm headless 模拟** | 本地测试, 验证 ANSI 序列被正确记录 | 低 |
| **CI 矩阵多终端** | 自动化回归, 覆盖多种终端 | 中 |
| **真实终端手动验证** | 发版前最终检查 | 高 (人工) |

#### 2.6.2 bubbleterm 集成

```go
// 使用 bubbleterm 捕获渲染中间态
func TestConsoleCompat(t *testing.T) {
    bt := bubbleterm.New()
    // 注入 nilRenderer 避免真正渲染
    p := tea.NewProgram(makeTestModel(),
        tea.WithOutput(bt),
        tea.WithoutRenderer(),  // nil renderer
    )

    // 发送消息并检查捕获的 ANSI 序列
    p.Send(tea.WindowSizeMsg{Width: 80, Height: 24})
    // 验证 bt 的渲染缓冲区中的特定序列
}
```

> **注意**: bubbleterm/bubbletea 生态中对 nilRenderer 和 headless 测试的支持仍在发展中, 建议先采用 L1-L4 策略，L6 作为远期增强项。

#### 2.6.3 CI 兼容性矩阵

```yaml
# .gitea/.gitea/workflows/tui-test.yaml
jobs:
  tui-test:
    strategy:
      matrix:
        os: [ubuntu-22.04, macos-13]
        go: ["1.21", "1.22"]
    steps:
      - run: go test -race -count=1 ./tui/...
      - run: go test -race -count=1 ./tui/components/...
```

---

## 3. 测试基础设施

### 3.1 测试辅助工具

| 工具/函数 | 位置 | 用途 |
|:--|:--|:--|
| `makeTestModel()` | `tui/update_test.go` | 创建带 mock client 的测试 Model |
| `stripANSI()` | 新增 `tui/testutil/` | 去除 ANSI 转义序列 |
| `assertGolden()` | 新增 `tui/testutil/` | Golden file 断言封装 |
| Mock `Client` | 新增 `client/mock/` | HTTP 请求 mock |
| `teatest` (第三方) | charmbracelet/x/exp/teatest | Bubble Tea 集成测试框架 |

### 3.2 建议目录结构

```
cli/
├── tui/
│   ├── testdata/              # Golden Files 存储
│   │   ├── view_*.golden
│   │   ├── run_list_*.golden
│   │   └── run_detail_*.golden
│   ├── testutil/              # 测试辅助函数
│   │   ├── helpers.go         # makeTestModel, stripANSI, assertGolden
│   │   └── fixtures.go        # 预制数据 (runs, tasks)
│   ├── model_test.go
│   ├── view_test.go
│   ├── update_test.go
│   ├── golden_test.go         # Golden files 测试
│   ├── fuzz_test.go           # Fuzz 测试
│   ├── boundary_test.go       # 边界条件测试
│   └── integration_test.go    # 集成流程测试
├── client/
│   └── mock/
│       └── client.go          # Mock HTTP Client
```

### 3.3 测试运行命令

```bash
# 运行所有 TUI 测试
go test ./cli/tui/... -v

# 运行带 race 检测
go test -race ./cli/tui/...

# 更新 Golden Files
go test ./cli/tui/ -update

# 运行 Fuzz 测试 (30s)
go test -fuzz=FuzzModelUpdate -fuzztime=30s ./cli/tui/

# 查看覆盖率
go test -coverprofile=coverage.out ./cli/tui/...
go tool cover -html=coverage.out
```

---

## 4. 现有测试覆盖评估与差距分析

### 4.1 已覆盖 (当前 16 个测试文件)

| 维度 | 现状 |
|:--|:--|
| 组件基础方法测试 | ✅ RunList, RunDetail, LogViewer 的 Init/SetRuns/SetSize/View/Update |
| 键盘事件处理 | ✅ q/esc/enter/tab/p/n/c/r/b/t 全部有覆盖 |
| 面板焦点切换 | ✅ focusNext/focusPrev/dispatchKey |
| 窗口 resize | ✅ WindowSizeMsg 基础测试 |
| 视图渲染 | ✅ 空状态/带数据/带错误/不同宽度的 View 测试 |
| 样色工具函数 | ✅ icons/styles/truncate/formatTime 有基础测试 |
| Tick 轮询 | ✅ tickMsg 触发 refresh 命令 |

### 4.2 待补齐 (Gap)

| 维度 | 缺失内容 |
|:--|:--|
| **Golden Files 快照** | 完全缺失——无法检测意外的渲染回归 |
| **边界窗口测试** | 仅有 80/200 两种宽度, 缺少 10x5/20x8/0x0 等极值 |
| **边界文本测试** | 缺少超长 ID(200 字符)、单行无换行 1000 字符、空字段组合 |
| **并发测试** | 没有 `-race` 覆盖、没有并发消息注入 |
| **Mock Client** | 所有测试直接使用真实 `client.New(cfg)`, 依赖后端 |
| **Fuzz 测试** | 完全缺失——fuzz 文件为零 |
| **错误状态链** | 缺少 fetchRuns 失败→retry→成功的完整链路 |
| **mergeRuns 边界** | 空 existing、空 newRuns、ID 完全不重叠时的合并 |
| **TruncateLine 极值** | width=0、负数 width、超长 line 无 Unicode 字符 |
| **Footer 渲染** | 当 errMsg + statusStr + hints 总宽度超过 width 时的 overflow |

---

## 5. 测试用例清单

### 5.1 高优先级 (P0 — 必须实现)

- [ ] **P0-1**: 创建 `tui/testutil/fixtures.go`, 提取公共 mock 数据
- [ ] **P0-2**: 实现 `client/mock/client.go`, 可注入预制响应
- [ ] **P0-3**: 补齐窗口尺寸边界: 10x5、20x8、0x0、42 (最小有效宽度)
- [ ] **P0-4**: Golden Files 快照测试 (至少 10 个核心场景)
- [ ] **P0-5**: `go test -race` 通过全部 TUI 测试
- [ ] **P0-6**: 超长文本边界: RunID 200 字符, PipelineName 200 字符, 单行日志 1000 字符
- [ ] **P0-7**: mergeRuns 边界测试: 空切片、完全无交集、部分重叠

### 5.2 中优先级 (P1 — 应该实现)

- [ ] **P1-1**: Fuzz Model.Update 和 TruncateLine
- [ ] **P1-2**: 完整交互流程集成测试 (浏览→选择→展开→查看日志→回退)
- [ ] **P1-3**: 错误恢复链路测试 (API 失败→显示错误→手动重试→成功)
- [ ] **P1-4**: Footer 溢出测试 (errMsg+hints+status 总宽度 > 终端宽度)
- [ ] **P1-5**: 高频率 tick 并发测试 (模拟 100 次随机消息注入)

### 5.3 低优先级 (P2 — 远期规划)

- [ ] **P2-1**: bubbleterm headless 终端模拟器兼容测试
- [ ] **P2-2**: CI 多 OS 矩阵 (Ubuntu + macOS)
- [ ] **P2-3**: 性能基准测试 (benchmark View 渲染耗时)
- [ ] **P2-4**: 内存泄漏检测 (长时间运行 TUI 的 goroutine 计数)

---

## 6. 实施路线图

```
Phase 1 (Week 1): 基础设施搭建
├── 创建 testutil 包 (helpers + fixtures)
├── 创建 mock client
├── 重构现有测试使用 makeTestModel + mock
└── 将 refreshInterval 设计为可注入

Phase 2 (Week 2): 边界测试 + 快照
├── 补齐所有窗口尺寸边界测试
├── 补齐超长文本边界测试
├── 实现 Golden Files 快照测试
└── 生成首批 10+ 个 .golden 文件

Phase 3 (Week 3): 并发 + 集成 + Fuzz
├── 全部测试通过 -race
├── 补完交互流程集成测试
├── 实现 Fuzz 测试
└── CI 配置 race detector

Phase 4 (Week 4+): 远期增强
├── bubbleterm 兼容性测试 (如果库成熟)
├── 性能 benchmark
└── CI 多 OS 矩阵
```

---

## 附录 A: 关键设计决策

| 决策点 | 选择 | 理由 |
|:--|:--|:--|
| 快照比对粒度 | **纯文本 Golden Files** 而非像素级 | TUI 输出本质是文本, Golden Files 维护成本远低于视觉回归 |
| 是否引入第三方 golden 库 | **可先自行实现** | 核心逻辑仅为 `os.ReadFile + cmp.Diff`, 保持依赖最小化 |
| Mock 粒度 | **接口抽象 client** | Model 持接口而非具体 `*client.Client`, 所有测试受益 |
| 颜色处理 | **测试时禁用** | `lipgloss.SetColorProfile(termenv.Ascii)` + `stripANSI` 双重保障 |
| 并发测试方式 | **-race + 消息批量注入** | 不必引入额外测试框架, Go 原生工具即可覆盖 |

## 附录 B: 参考资源

- [Bubble Tea Testing Tutorial](https://charm.sh/blog/tui-testing/)
- [Bubble Tea nilRenderer](https://pkg.go.dev/github.com/charmbracelet/bubbletea#WithoutRenderer)
- [gotest.tools/v3/golden](https://pkg.go.dev/gotest.tools/v3/golden)
- [Go Fuzzing Guide](https://go.dev/doc/security/fuzz/)
- [Go Race Detector](https://go.dev/doc/articles/race_detector)
