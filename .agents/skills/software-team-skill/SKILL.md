---
name: software-team-skill
description: 软件开发团队协作技能。融合 Gitea Issue 驱动开发和禅道（ZenTao）结构化项目管理，支持 5 种角色（manager/pm/developer/tester/uiux）在 4 种工单类型（新需求/缺陷/优化/其他任务）下的标准化协作流程。
license: MIT
metadata:
  depends_on: [zentao-cli]
  keywords: [software-team, gitea-issue, zentao, 禅道, role, 团队协作, manager, pm, developer, tester, uiux]
  version: 1.5.0
---

# 软件开发团队协作技能（software-team-skill, v1.5）

> **v1.0**：合并 `gitea-issue` 和 `zentao-team-skill` 为统一的 `software-team-skill`。
> Manager 是 main agent（唯一入口），PM/Developer/Tester/UIUX 是 sub-agent。
>
> **v1.2（issue #132）**：重构 zentao task 创建/关闭流程。
> - **Manager 创建全部 4 种 task**：`req task`（PM 规划）、`dev task`（Dev 实现）、`testtask`（QA/Tester 测试）、`uiux design task`（UIUX 设计，按需）
> - **各 sub-agent 关闭自己负责的 task**（PM finish req task / Dev finish dev task / QA or Tester finish testtask / UIUX finish uiux design task）
> - **Manager 仍不创建** story / bug / testcase / execution / project
> - PM 现在只建 story，**不再建 task**（task 由 Manager 统一建）
>
> **v1.3（简化快速路径）**：对"确定且简单"的工单提供快速通道。
> - **新增复杂度评估**：Manager 在类型识别后判断工单是否"简单"（单点修复/无歧义/无设计决策/无新 API）
> - **简化快速路径（分支 E）**：简单工单**只建 dev task**，跳过 PM story+req task、跳过 Tester zentao bug+testtask
> - **直接让 Dev 开发**：Manager 建 dev task → Developer 直接实现 → Manager 创建 PR → 验收
> - **不创建 req/bug 在 zentao**：快速路径不建 story、不建 zentao bug、不建 testtask（仅保留 dev task 作追踪）
> - 不确定"是否简单"时**走完整流程**（保守默认）
>
> **v1.2（issue #108 实战优化）**：优化 Dev/QA 协作流程。
> - **Dev 和 QA 串行工作**：Dev 先完成实现，QA 再编写测试用例并执行
> - **QA 发现 bug 时创建 zentao bug**：指派给 Dev，Dev 读取 zentao bug 并修复
> - **迭代修复循环**：QA 测试 → 发现 bug → Dev 修复 → QA 验证 → 循环直到所有测试通过
> - **Manager 创建 PR**：所有测试通过后，Manager 创建 PR 供用户审查
> - **Manager 不尝试测试**：Manager 只负责协调，不参与测试或修复
>
> **v1.4（issue #134 实战优化）**：PR 合并后 push main 到 GitHub。
> - **汇总验收前 push GitHub**：所有分支流程在 PR 合并后 → `git push github main` 推送 → 再关闭 zentao/gitea 对象
> - **Manager 负责 push**：Manager 在汇总验收阶段执行 push 操作
>
> **v1.5（issue #134 reopen 实战）**：QA/Tester 必须验证构建。
> - **QA/Tester 测试后必须验证 build**：运行 tests 后必须跑 `npm run build` / `npx tsc --noEmit` / 对应语言的构建检查，确认无编译错误才能 finish testtask
> - **不验证 build = QA/Tester 的失职**：TypeScript 编译错误（如 TS2322）不会被 vitest 捕获，QA 不跑 build 会导致用户部署失败
> - **所有涉及前端/web 代码变更的 testtask 都必须做 build check**
>
> **核心约定**：
> - **gitea issue 评论 = 极简**（链接 + 1-2 句状态）
> - **zentao 对象 comment = 详细**（用户故事、验收标准、方案对比、bug 详情、testcase 步骤、**bug 根因分析**）
> - **Manager 在 zentao 可创建 4 种 task（req/dev/test/uiux）+ 可改 task.assignedTo**，仍不创建 story / bug / testcase / execution / project
> - **PM 不创建 execution/project**，只复用用户已创建的最新 doing execution
> - **PM 不创建 task**（v1.2 起 task 由 Manager 统一建），只建 story
> - **各 sub-agent 自己关闭自己负责的 task**（不依赖 PM/Manager 帮忙 close）
> - **所有 testcase 必须可自动化执行**（pytest/vitest，可放入 CI）
> - **QA/Tester 完成后必须验证 build**（v1.5 起：跑 `npm run build` / `npx tsc --noEmit` 确认无编译错误）
> - **Dev 和 QA 串行工作**（v1.2 起：Dev 先完成，QA 再测试）
> - **QA 发现 bug 时创建 zentao bug 并指派给 Dev**（v1.2 起：迭代修复循环）
> - **Manager 创建 PR**（v1.2 起：所有测试通过后，Manager 创建 PR 供用户审查）

## 前置依赖

```bash
# 禅道 CLI
npm install -g zentao-cli

# 一次性 setup（为所有角色 login 到 per-role config 文件）
bash .agents/skills/software-team-skill/scripts/setup_role_configs.sh
```

## 第 0 步：角色识别与声明（强制前置）

**AI 必须在执行任何后续步骤前，先确定并声明角色。**

### 0.1 五种角色

| 角色 | 定位 | 识别信号 | 典型职责 |
|------|------|---------|---------|
| **manager** | main agent | `/skill software-team <url>` 触发 | 优先级决策、**创建 4 种 zentao task（req/dev/test/uiux）**、任务分配、状态汇总、验收审批 |
| **pm** | sub-agent | Manager 启动：拆需求/任务 | 建 zentao **story** + 写详细规划（spec/verify/comment）→ **finish 自己的 req task** |
| **developer** | sub-agent | Manager 启动：写代码 | TDD 实现、commit、push → **finish 自己的 dev task** |
| **tester** | sub-agent | Manager 启动：qa/bug | 新需求：推 zentao testcase + 写 `tests/` 测试代码 / 缺陷：复现 + 建 bug + 写测试 + 修复后验证 → **finish 自己的 testtask** |
| **uiux** | sub-agent | Manager 按需启动 | 设计稿、设计走查 → **finish 自己的 uiux design task** |

### 0.2 角色声明（必须输出）

确定角色后，**必须在回复开头输出**：

```
当前角色: <manager|pm|developer|tester|uiux>
```

> **禁止**：不声明就执行操作。

### 0.3 读取角色文件

声明角色后，**必须**读取对应角色的 `_base.md`：

```
roles/<role>/_base.md
```

### 0.4 角色越权

| 禁止行为 | 角色 |
|---------|------|
| 创建 zentao **story** / execution / project | developer, tester, uiux（**PM 仍可建 story**） |
| 创建 zentao **bug** | developer, pm, uiux（**Tester 可建 bug**） |
| 创建 zentao **testcase** | developer, pm, uiux（**Tester/QA 可建 testcase**） |
| 创建 zentao **task** | developer, tester, uiux, pm（**v1.2 起 task 由 Manager 统一建**） |
| 写 `src/` / `server/` / `web/src/` 生产代码 | manager, pm, tester, uiux |
| 关闭 gitea issue | developer, tester（sub-agent 模式） |
| 写 `tests/` 正式测试 | developer, pm, uiux |
| 决定项目进度（execution 切换） | 所有角色（等用户确认） |
| 绕过 Manager 直接操作 | pm, developer, tester, uiux |
| **关闭非自己负责的 zentao task** | 所有角色（v1.2 起 task 由 assignedTo 角色自己 close） |

---

## 4 种工单类型工作流

> **入口**：用户用 `/skill software-team <issue_url>` 触发。
> Manager (aimanager) 识别 issue 类型后，按对应分支流程协调 sub-agent。

### 类型识别

按 **label 优先 → 标题前缀兜底** 顺序判断：

| 匹配条件 | 类型 | 走哪条流程 |
|---------|------|-----------|
| label 含 `Kind/Requirement` 或 title 以 `[REQ]` 开头 | **新需求** | 分支 A |
| label 含 `Kind/Bug` 或 title 以 `[BUG]` 开头 | **缺陷** | 分支 B |
| label 含 `Kind/Optimize` 或 title 以 `[OPT]` 开头 | **优化** | 分支 C |
| label 含 `Kind/Task` 或 title 以 `[TASK]` 开头 | **其他任务** | 分支 D |

### 复杂度评估（v1.3 新增，类型识别后强制执行）

> Manager 识别类型后，**必须**判断该工单是否"简单"。简单 → 走**分支 E 快速路径**；非简单 → 走对应完整分支（A/B/C/D）。
> **不确定一律按"非简单"处理**，走完整流程（保守默认）。

**"简单"判定标准（需同时满足）**：

| 维度 | 简单（fast path） | 非简单（完整流程） |
|------|:--:|:--:|
| 改动范围 | 单点修复 / 1-2 文件 < 50 行 | 多模块 / 跨子系统 |
| 歧义性 | 需求/缺陷描述无歧义，方案唯一 | 需澄清、有多种实现 |
| 设计决策 | 无 UI 设计、无架构决策 | 需 UIUX 介入 / 架构调整 |
| 新增接口 | 无新 API / 无新对外契约 | 新增接口或对外行为变更 |
| 测试需求 | 改动可直接由现有测试覆盖 / 无需新 testcase | 需要专门设计 testcase（边界/并发/异常） |

**判定结果写入 status.json**：
```json
"complexity": "simple | full",
"complexity_reason": "单点修复 + 无歧义 + 无新 API（满足 5/5 维度）"
```

> 简化工单类型对照：
> - **简单的新需求 / 优化 / 其他任务** → 分支 E（跳过 PM story+req task）
> - **简单的缺陷** → 分支 E（跳过 Tester zentao bug+testtask，但 Dev 仍需写最小回归测试到 `.debug/`）

---

```
参与角色: Manager(建task) → PM(写story) → Developer(实现) → QA(测试) → [bug修复循环] → Manager(创建PR) → Manager(验收)
```

| 阶段 | 谁 | 做什么 |
|------|----|--------|
| 1. 触发 + 优先级 | **Manager** | 读 issue → 判断类型 → 打 `Priority/*` 标签 → 读 zentao execution/product 上下文 |
| 2. 建 task | **Manager** | **创建 4 种 zentao task**：`req task` (affair, →aipm) / `dev task` (devel, →aidev) / `testtask` (affair, →aitester) / `uiux design task` (design, →designer，按需) → gitea 打 项目/产品/执行/Task 标签 |
| 3. 写规划 | **PM** (sub) | 用 `create_story_for_review.py` 建 story（自动设 reviewer=admin）→ 写 spec/verify/comment（**v2 REST API PUT + reviewer=admin**）→ 发 gitea 极简评论通知 admin → **finish 自己的 req task**（`zentao task finish $REQ_TASK_ID --consumed=N`） |
| 4. 设计（按需）| **UIUX** (sub) | issue 含 `UI/Frontend`/`Kind/UI` label → 出设计稿 → PM 评审 → **finish 自己的 uiux design task** |
| 5. 实现 | **Developer** (sub) | TDD 实现 → commit → gitea 极简报告 → **finish 自己的 dev task** |
| 6. 测试 | **QA** (sub) | 推 zentao testcase → 写 `tests/` 测试代码实现（边界/异常/并发/环境 4 维度）→ 执行测试 → **必须跑 build 检查**（`npm run build` / `npx tsc --noEmit`）确认无编译错误 → **如果发现 bug → 创建 zentao bug + 指派给 Dev** → **finish 自己的 testtask** |
| 7. 修复循环 | **Developer** (sub) | 读 zentao bug → TDD 修复 → commit → **在 zentao bug comment 写根因分析 + 修复方案** |
| | **QA** (sub) | 跑测试验证修复 → 如果还有失败 → 重复步骤 7 |
| 8. 创建 PR | **Manager** | 所有测试通过后 → 创建 PR → gitea 极简评论通知用户审查 |
| 9. 汇总验收 | **Manager** | 用户审查通过、PR 合并 → `git push github main` 推送到 GitHub → **PM close zentao story** → Manager close gitea issue |

**协作关系**：
```Manager (main)
  ├── [建 4 task]  zentao: req/dev/test/(uiux)
  ├── PM (sub)             → create_story_for_review.py 建 story → v2 REST PUT spec/verify/comment → finish req task
  ├── UIUX (sub, 按需)     → 设计稿 → finish uiux design task
  ├── Developer (sub)      → TDD 实现 → finish dev task
  │                         ↓ (如果 QA 发现 bug)
  │                       读 zentao bug → TDD 修复 → commit
  └── QA (sub)             → zentao testcase + 写 tests/ → 执行测试
                              ↓ (如果发现 bug)
                            创建 zentao bug → 指派给 Dev → 验证修复
                              ↓ (所有测试通过)
                            finish testtask
                              ↓
                            Manager 创建 PR → 通知用户审查
```

**Task 默认设置**：

| task 名 | type | assignedTo | 关闭方式 |
|---------|------|------------|---------|
| `[PM 规划] <issue 标题>` | affair | aipm | PM：`zentao task finish $ID --consumed=<h>` |
| `[Dev 实现] <issue 标题>` | devel | aidev | Dev：`zentao task finish $ID --consumed=<h>` |
| `[QA Testcase + 测试] <issue 标题>` | affair | aitester | QA：`zentao task finish $ID --consumed=<h>` |
| `[UIUX 设计] <issue 标题>`（按需） | design | designer | UIUX：`zentao task finish $ID --consumed=<h>` |

> **v1.2 变更**：
> - Manager 创建所有 task（PM 不创建 task）
> - Dev 和 QA 串行工作（Dev 先完成，QA 再测试）
> - QA 发现 bug 时创建 zentao bug 并指派给 Dev
> - Dev 读取 zentao bug 并修复
> - 循环直到所有测试通过

---

### 分支 B：缺陷（Kind/Bug）

```
参与角色: Manager(建task) → Tester(建bug+写测试) → Developer(修复+根因) → Tester(验证) → Manager(创建PR) → Manager(验收)
```

| 阶段 | 谁 | 做什么 |
|------|----|--------|
| 1. 触发 + 优先级 | **Manager** | 读 issue → bug 默认 `Priority/High` → 准备 product/execution 上下文 |
| 2. 建 task | **Manager** | **创建 3 种 zentao task**：`testtask #1 调查` (affair, →aitester) / `dev task` (devel, →aidev) / `testtask #2 验证` (affair, →aitester) → gitea 打 项目/产品/执行/Task 标签 |
| 3. 建 bug + 写测试 | **Tester** (sub) | 复现 → `zentao bug create` → **写 `tests/` 自动化测试覆盖 bug 场景** → `zentao bug assign --assignedTo=aidev` → gitea 打 `Bug/<id>` → **finish 自己的 testtask #1（调查）** |
| 4. 修复 + 根因 | **Developer** (sub) | 读 zentao bug + tester 测试 → TDD 修复 → **在 zentao bug comment 写根因分析 + 修复方案 + commit** → **finish 自己的 dev task** |
| 5. Tester 验证 | **Tester** (sub) | 跑 `tests/` 确认 bug 修复 → **必须跑 build 检查**（`npm run build` / `npx tsc --noEmit`）→ 验证测试覆盖 → gitea 极简验证报告 → **finish 自己的 testtask #2（验证）** |
| 6. 创建 PR | **Manager** | Tester 验证通过后 → 创建 PR → gitea 极简评论通知用户审查 |
| 7. 汇总验收 | **Manager** | 用户审查通过、PR 合并 → `git push github main` 推送到 GitHub → **Tester close zentao bug** → Manager close gitea issue |

**协作关系**：
```
Manager (main)
  ├── [建 3 task]  zentao: testtask×2 + dev task
  ├── Tester (sub)      → 复现 + zentao bug create + 写 tests/ + finish testtask #1
  ├── Developer (sub)   → TDD 修复 + zentao bug 根因 + finish dev task
  └── Tester (sub)      → 验证修复 + finish testtask #2
                              ↓
                    Manager @用户 验收 → Tester close bug
```

**Task 默认设置**：

| task 名 | type | assignedTo | 关闭方式 |
|---------|------|------------|---------|
| `[Tester 调查] <issue 标题>` | affair | aitester | Tester（第一阶段）：`zentao task finish $ID --consumed=<h>` |
| `[Dev 修复] <issue 标题>` | devel | aidev | Developer：`zentao task finish $ID --consumed=<h>` |
| `[Tester 验证] <issue 标题>` | affair | aitester | Tester（第二阶段）：`zentao task finish $ID --consumed=<h>` |

> **v1.2 变更**：bug 类型不再由 PM 准备上下文（省去 PM 阶段）；testtask 由 Manager 建，Tester 自己 finish 调查 + 验证两个 testtask。bug 对象仍由 Tester 建（zentao bug create），与 task 分离。

---

### 分支 C：优化（Kind/Optimize）

```
参与角色: Manager(建task) → PM(写规划) → Developer → Manager(创建PR) → Manager(验收)
```

| 阶段 | 谁 | 做什么 |
|------|----|--------|
| 1. 触发 + 优先级 | **Manager** | 读 issue → 默认 `Priority/Medium` → 准备 context |
| 2. 建 task | **Manager** | **创建 2 种 zentao task**：`req task` (affair, →aipm) / `dev task` (devel, →aidev) → gitea 打 项目/产品/执行/Task 标签 |
| 3. 写规划 | **PM** (sub) | 读 zentao req task → 写 task desc（现状问题 + 优化目标 + 预期效果 + 验收标准） + comment → gitea 极简评论 → **finish 自己的 req task** |
| 4. 实现 | **Developer** (sub) | 读 zentao dev task → TDD 实现 → commit → zentao task comment 写实现思路 + commit → gitea 极简报告 → **finish 自己的 dev task** |
| 5. 创建 PR | **Manager** | Dev 完成后 → 创建 PR → gitea 极简评论通知用户审查 |
| 6. 汇总验收 | **Manager** | 用户审查通过、PR 合并 → `git push github main` 推送到 GitHub → Manager close gitea issue |

> 优化类型**不需要 QA 推 testcase**（无新增功能），**不涉及 UIUX**（除非 issue 有 `UI/` label）。

**Task 默认设置**：

| task 名 | type | assignedTo | 关闭方式 |
|---------|------|------------|---------|
| `[PM 规划] <issue 标题>` | affair | aipm | PM：`zentao task finish $ID --consumed=<h>` |
| `[Dev 实现] <issue 标题>` | devel | aidev | Dev：`zentao task finish $ID --consumed=<h>` |

> **v1.2 变更**：Manager 创建所有 task（PM 不创建 task），PM 只写 desc + finish req task。

---

### 分支 D：其他任务（Kind/Task）

```
参与角色: Manager(建task) → PM(写规划) → Developer → Manager(创建PR) → Manager(验收)
```

> 适用于杂项任务：文档更新、配置变更、脚本编写、依赖升级等。

| 阶段 | 谁 | 做什么 |
|------|----|--------|
| 1. 触发 + 优先级 | **Manager** | 读 issue → 默认 `Priority/Medium` |
| 2. 建 task | **Manager** | **创建 2 种 zentao task**：`req task` (affair, →aipm) / `dev task` (devel, →aidev) → gitea 打 项目/产品/执行/Task 标签 |
| 3. 写规划 | **PM** (sub) | 读 zentao req task → 写 task desc（任务说明 + 预期产出 + 验收条件） + comment → gitea 极简评论 → **finish 自己的 req task** |
| 4. 实现 | **Developer** (sub) | 读 zentao dev task → 执行 → commit → zentao task comment 写完成说明 + commit → gitea 极简报告 → **finish 自己的 dev task** |
| 5. 创建 PR | **Manager** | Dev 完成后 → 创建 PR → gitea 极简评论通知用户审查 |
| 6. 汇总验收 | **Manager** | 用户审查通过、PR 合并 → `git push github main` 推送到 GitHub → Manager close gitea issue |

> 不涉及 QA、UIUX，无需写 `tests/`。

**Task 默认设置**：

| task 名 | type | assignedTo | 关闭方式 |
|---------|------|------------|---------|
| `[PM 规划] <issue 标题>` | affair | aipm | PM：`zentao task finish $ID --consumed=<h>` |
| `[Dev 实现] <issue 标题>` | devel | aidev | Developer：`zentao task finish $ID --consumed=<h>` |

---

### 分支 E：简化快速路径（Simple）

> **触发条件**：Manager 在"复杂度评估"中判定为 **simple**（5 个维度全部满足）。
> 适用类型：新需求 / 优化 / 其他任务 / 缺陷 任一类型，判定为 simple 即走此路径。
> **核心：只建 dev task，跳过 PM story+req task、跳过 Tester zentao bug+testtask，直接让 Dev 开发。**

```
参与角色: Manager(建 dev task + 复杂度评估) → Developer(直接实现) → Manager(创建PR) → Manager(验收)
```

| 阶段 | 谁 | 做什么 |
|------|----|--------|
| 1. 触发 + 优先级 + 复杂度评估 | **Manager** | Tag audit → 识别类型 → **复杂度评估（写 status.json: complexity/reason）** → 打 `Priority/*` 标签 |
| 2. 建 task | **Manager** | **只建 1 种 zentao task**：`dev task` (devel, →aidev) → gitea 打 项目/产品/执行/Task 标签 → **不打** Story / Bug / TestCase 标签 |
| 3. 直接实现 | **Developer** (sub) | 直接读 issue + dev task（无 story、无 bug 对象）→ 在 `.debug/issue_<num>/` 写最小 TDD 验证（不写 `tests/`）→ commit → zentao task comment 写实现说明 → gitea 极简报告 → **finish 自己的 dev task** |
| 4. 创建 PR | **Manager** | Dev 完成后 → 创建 PR → gitea 极简评论通知用户审查 |
| 5. 汇总验收 | **Manager** | 用户审查通过、PR 合并 → `git push github main` 推送到 GitHub → Manager close gitea issue（**无 zentao story/bug 需 close**） |

**协作关系**：
```
Manager (main)
  ├── [复杂度评估 simple] → 写 status.json complexity=simple
  ├── [建 1 task]  zentao: dev task (→aidev)
  └── Developer (sub) → 直接读 issue + dev task → .debug TDD → commit → finish dev task
                        ↓
                Manager 创建 PR → 通知用户审查 → Manager close issue
```

**Task 默认设置**：

| task 名 | type | assignedTo | 关闭方式 |
|---------|------|------------|---------|
| `[Dev 实现] <issue 标题>` | devel | aidev | Developer：`zentao task finish $ID --consumed=<h>` |

**简化工单对照**：
| 原类型 | 跳过的环节 |
|--------|-----------|
| 简单的新需求 (A) | 跳过 PM 建 story + req task、跳过 QA testcase+tests/、跳过 UIUX、跳过 bug 修复循环 |
| 简单的缺陷 (B) | 跳过 Tester 建 zentao bug + 写 tests/、跳过 testtask×2、跳过 Tester 验证阶段 |
| 简单的优化 (C) | 跳过 PM req task + 写规划 |
| 简单的其他任务 (D) | 跳过 PM req task + 写规划 |

> **重要**：快速路径**仍保留 dev task 作追踪**；**不建** story / zentao bug / testcase / testtask。
> 对简单缺陷，Dev 仍需在 `.debug/issue_<num>/` 写最小回归脚本验证修复（不写 `tests/`，遵循 Dev 职责边界）。
> **v1.3 保守原则**：不确定是否简单 → 走完整流程（A/B/C/D）。仅在 5 维度全部满足时走 E。

---

### 工作流对比总览

| | 新需求 (A) | 缺陷 (B) | 优化 (C) | 其他任务 (D) | 简化快路径 (E) |
|------|:--:|:--:|:--:|:--:|:--:|
| Manager 触发 + 复杂度评估 | ✅ | ✅ | ✅ | ✅ | ✅ simple |
| Manager 建 req task | ✅ (→aipm) | ❌ | ✅ (→aipm) | ✅ (→aipm) | ❌ |
| Manager 建 dev task | ✅ (→aidev) | ✅ (→aidev) | ✅ (→aidev) | ✅ (→aidev) | ✅ (→aidev) |
| Manager 建 testtask | ✅ (→aitester) | ✅×2 (→aitester) | ❌ | ❌ | ❌ |
| Manager 建 uiux design task | 按需 (→designer) | 按需 | 按需 | ❌ | ❌ |
| PM 建 story | ✅ | ❌ | ❌ | ❌ | ❌ |
| PM finish req task | ✅ | — | ✅ | ✅ | ❌ |
| UIUX 设计 | 按需 | 按需(UI bug) | 按需 | ❌ | ❌ |
| **v1.2: Dev 先完成，QA 再测试** | ✅ | ✅ | ❌ | ❌ | ❌ |
| QA 推 testcase + 写 tests/ | ✅ | ❌ | ❌ | ❌ | ❌ |
| QA 发现 bug → 创建 zentao bug | ✅ | ❌ | ❌ | ❌ | ❌ |
| Dev 读 zentao bug → 修复 | ✅ | ❌ | ❌ | ❌ | ❌ |
| Tester 建 bug + 写测试 + 验证 | ❌ | ✅ | ❌ | ❌ | ❌ |
| **v1.3: Dev 直接实现（无 story/bug）** | — | — | — | — | ✅ |
| Dev 实现 + finish dev task | ✅ | ✅ | ✅ | ✅ | ✅ |
| **v1.2: Manager 创建 PR** | ✅ | ✅ | ✅ | ✅ | ✅ |
| Manager / PM / Tester close story/bug | PM close story | Tester close bug | — | — | 无需 close zentao 对象 |

> **v1.3 变更**：
> - 新增复杂度评估（type 识别后强制执行，简单 → 分支 E）
> - 简化快速路径（分支 E）：只建 dev task，跳过 PM/Tester/UIUX，Dev 直接实现
> - 不创建 story / zentao bug / testtask 在 zentao（保守默认走完整流程）
>
> **v1.2 变更**：
> - Dev 和 QA 串行工作（Dev 先完成，QA 再测试）
> - QA 发现 bug 时创建 zentao bug 并指派给 Dev
> - Dev 读取 zentao bug 并修复
> - 迭代循环直到所有测试通过
> - Manager 在最后创建 PR 供用户审查
> - Manager 不尝试测试，只负责协调

---

## 凭据配置

### Gitea 凭据（[credentials/gitea.ini](credentials/gitea.ini)）

```ini
[gitea]
host = http://10.98.72.23:8418
repo = AM-SYS/taskpps

[manager]
user = ai-manager
password = user@123

[pm]
user = ai-pm
password = user@123

[developer]
user = ai-developer
password = user@123

[tester]
user = ai-tester
password = user@123

[uiux]
user = ai-uiux
password = user@123
```

**Gitea 脚本调用**：所有脚本加 `--role <role>` 参数从 `credentials/gitea.ini` 加载凭据。

### Zentao 凭据（[credentials/zentao.ini](credentials/zentao.ini)）

```ini
[zentao]
host = http://10.98.72.23:9000/

[manager]
account = aimanager
password = User@123

[pm]
account = aipm
password = User@123

[developer]
account = aidev
password = User@123

[tester]
account = aitester
password = User@123

[uiux]
account = designer
password = CHANGE-ME   ; 占位，待用户填
```

**Zentao 登录**：运行期不调 `zentao login`，只设 `ZENTAO_URL` + `ZENTAO_CONFIG_FILE` 指向 `state/zentao-<role>.json`（由 `setup_role_configs.sh` 一次性生成）。

---

## Gitea 标签约定

> **目标**：让 issue 一眼看到关联的 zentao 对象 + 项目上下文。

| 命名空间 | 含义 | **必选?** | 谁打 | 何时打 |
|---------|------|----------|------|--------|
| `Kind/Requirement` / `Kind/Bug` / `Kind/Optimize` / `Kind/Task` | issue 类型（4 选 1） | **✅ 必选** | Manager（接手时 audit 补打） | Step 1.0 Tag Audit |
| `Priority/Critical` / `Priority/High` / `Priority/Medium` / `Priority/Low` | 优先级（4 选 1） | **✅ 必选** | Manager（接手时 audit 补打） | Step 1.0 Tag Audit |
| `项目/<name>` | zentao project | 必选 | **Manager** | Step 2 Manager 建 task 后 |
| `产品/<name>` | zentao product | 必选 | **Manager** | Step 2 Manager 建 task 后 |
| `执行/<name>` | zentao execution | 必选 | **Manager** | Step 2 Manager 建 task 后 |
| `Story/<id>` | zentao story | 必选（如有 story） | PM | Step A.3 PM 建 story 后 |
| `Task/<id>` | zentao task（req/dev/test/uiux） | 必选（如有 task） | **Manager** | Step 2 Manager 建 task 后 |
| `Bug/<id>` | zentao bug | 必选（仅 bug 类型） | Tester | Step 5 B.3 Tester 建 bug 后 |
| `TestCase/<id>` | zentao testcase | 可选 | QA | Step 5 A.5 QA 推 testcase 后 |
| `UI/Frontend` / `UI/Design` | UI 相关 | 可选 | issue 报告者 | issue 创建时 |
| `Status/Blocked` | 被阻塞 | 可选 | 报告者/Manager | 任何阶段 |
| `Test/Ready` | 实现 + testcase 就绪 | 可选 | Manager | 验收前 |
| `Reviewed/Confirmed` / `Reviewed/Invalid` / `Reviewed/Duplicate` / `Reviewed/Won't Fix` | 关闭原因 | **✅ 必选（关闭时）** | Manager | Step 8 关闭 issue |

```bash
# 打标签
python3 scripts/gitea/set_labels.py <issue_url> --add <label> --role <role>
# 读标签
python3 scripts/gitea/get_labels.py <issue_url> --names-only --role <role>
# ⚡ Tag Audit（Manager 接手时必跑）
python3 scripts/gitea/audit_labels.py <issue_url> --role manager [--auto-fix]
```

### ⚡ Tag Audit 强制流程（Manager 接手时第一件事）

> **v1.2 新增**：源自 issue #108 实战教训——用户打了非标准 `Kind/Feature` + 标题 `[DO NOT DEV]`，Manager 接手时没先做 tag audit，导致后续流程判断失误。

**触发时机**：Manager 收到 issue 后、Step 1 类型识别之前**第一件事**。

**核心命令**：

```bash
# 1) Dry-run：只审计不打
python3 scripts/gitea/audit_labels.py "$ISSUE_URL" --role manager

# 2) 自动补打缺失的 Kind / Priority
python3 scripts/gitea/audit_labels.py "$ISSUE_URL" --role manager --auto-fix
```

**审计规则**：

| 情况 | 决策 |
|------|------|
| 命中 `Kind/Requirement\|Bug\|Optimize\|Task` 中 1 个 | ✅ 合法，保留 |
| 命中多个标准 Kind | ⚠️ 警告，保留首个 |
| 命中**非标准** Kind（如 `Kind/Feature`） | ⚠️ 警告但继续，让 sub-agent 处理 |
| 缺 Kind + 标题以 `[REQ]/[BUG]/[OPT]/[TASK]` 开头 | → 推断并自动补打 |
| 缺 Kind + 无标题前缀 | ❌ 退出码 2，问用户 |
| 缺 Priority | → 按 kind 默认：bug=High，其他=Medium（可用 `--default-priority` 覆盖） |

**退出码**：

| 码 | 含义 | 动作 |
|----|------|------|
| 0 | 必要标签完备 | 继续 |
| 1 | 参数错误 | 修参数 |
| 2 | 缺 Kind 且无法推断 | 用 AskUserQuestion 问用户 |
| 3 | API 失败 | 重试或检查凭据 |
| 4 | 有缺失标签但没用 `--auto-fix` | Manager 必须用 `--auto-fix` 重跑 |

**写 status.json**：

```json
{
  "tag_audit": {
    "audited_at": "2026-06-24T16:30:00+08:00",
    "decided_kind": "Kind/Requirement",
    "decided_priority": "Priority/Medium",
    "auto_fixes": ["Kind/Requirement", "Priority/Medium"],
    "warnings": ["工单有非标准 Kind 标签 Kind/Feature ..."]
  }
}
```

**为什么必做**：

1. **避免 sub-agent 误判类型**——issue #108 的 `Kind/Feature` 让 PM/Manager 走错分支
2. **避免漏打 Priority**——有些用户从不主动打 priority，audit 强制补
3. **审计报告可追溯**——所有标签变更记录在 `status.json`
4. **统一性**——所有 issue 在禅道/工单系统里看起来一致，方便看板上筛选

## Gitea Issue vs Zentao 评论约定

| | Gitea Issue | Zentao Object Comment |
|------|-------------|----------------------|
| **风格** | **极简**（链接 + 1-2 句状态） | **详细**（专业完整内容） |
| PM | `[PM 进度] story #N 完成` | 用户故事、验收标准、方案对比（≥3 方案 + 6 维评分） |
| Dev | `[Developer 完成报告] commit + branch` | 实现思路（task）/ **根因分析 + 修复方案**（bug）、TDD 进度、修改文件列表 |
| QA | `[QA Testcase 就绪]` + 链接 | testcase 步骤、覆盖维度、测试代码位置 |
| Tester | `[Tester Bug 报告]` / `[Tester 验证通过]` + 链接 | 复现步骤、期望/实际、影响范围 / 验证结果 + 覆盖确认 |
| UIUX | `[UIUX 设计就绪]` + 链接 | 设计稿链接、设计决策、交互说明 |
| Manager | `[Manager 进度/请验收/已关闭]` | **可创建 zentao task**（v1.2 起）；仍不写其他 zentao 对象（story/bug/testcase）的 comment |

---

## status.json 协议

`.debug/issue_<num>/status.json` 是 Manager 和所有 sub-agent 之间的唯一共享状态。

```json
{
  "issue": 123,
  "issue_url": "http://...",
  "type": "requirement | bug | optimize | task",
  "complexity": "simple | full",
  "complexity_reason": "单点修复 + 无歧义 + 无新 API（满足 5/5 维度）",
  "priority": "high | medium | low | critical",
  "phase": "identified → manager_approved → manager_created → pm_started → ... → closed | fast_dev_done | fast_ready",
  "product": 1,
  "product_name": "Taskpps",
  "execution": 5,
  "project_name": "v1.0",
  "story": 42,

  "tasks": {
    "req": 11,
    "dev": 12,
    "test_investigate": 13,
    "test_verify": 14,
    "uiux": 15
  },
  "bug_id": null,

  "manager": {"decision": "priority|assign|approve", "priority": "...", "decided_at": "..."},
  "pm": {"status": "planned|done", "story_id": 42, "req_task_id": 11, "finished_at": "...", "zentao_filled": {"spec_len": 1765, "verify_len": 540, "method": "v2 REST PUT spec+verify+reviewer=admin"}},
  "dev": {"status": "started|done|fix_done", "commit": "abc1234", "branch": "feat/issue-123", "dev_task_id": 12},
  "qa": {"status": "testcase-ready|verified", "zentao_testcases": [100,101], "testtask_id": 13, "test_files": ["tests/<模块>/test_*.py"]},
  "tester": {"status": "test-code-written|verified|cannot-reproduce", "zentao_bug_id": 89, "testtask_investigate_id": 13, "testtask_verify_id": 14, "test_files": ["tests/<模块>/test_bug_*.py"]},
  "uiux": {"status": "design-ready|approved", "design_url": "http://...", "uiux_task_id": 15}
}
```

**task 字段（v1.2）**：
- `tasks.req` (number|null): PM 规划 task ID（affair 类型，→aipm）
- `tasks.dev` (number|null): Dev 实现/修复 task ID（devel 类型，→aidev）
- `tasks.test_investigate` (number|null): QA/Tester 测试调查 task ID（affair，→aitester）
- `tasks.test_verify` (number|null): Tester 验证 task ID（affair，→aitester；仅 bug 类型用）
- `tasks.uiux` (number|null): UIUX 设计 task ID（design，→designer；仅 UI 类 issue 用）

> **v1.0 → v1.2 字段变更**：
> - 移除顶层 `task_dev` 字段（替换为 `tasks.dev`）
> - 移除 `pm.task_ids` 数组（替换为 `pm.req_task_id`）
> - 新增 `tasks.*` 子对象统一管理 4 种 task
> - `pm.req_task_id` / `dev.dev_task_id` / `qa.testtask_id` / `tester.testtask_*_id` / `uiux.uiux_task_id` 各自记录自己负责的 task ID

**写入规则**：每个角色**只写自己的字段** + 可写顶层 `phase`（推到自己阶段）。
- Manager 写：`manager`、`tasks.*`、`phase`（推到 manager_* / ready_for_user / closed）
- PM 写：`pm`、`story`、`project_name`、`execution_name`、`product_name`
- Dev 写：`dev`
- QA 写：`qa`
- Tester 写：`tester`、`bug_id`
- UIUX 写：`uiux`

---

## Tester 测试自动化工作流（v1.2）

> **v1.2 新增**：全项目 testcase 映射、@pytest.mark.zentao 标记、测试单驱动的结果上传。

### 测试用例全景

| 来源 | 语言/框架 | 用例数 | 映射文件 | Zentao 标题前缀 |
|------|----------|--------|---------|---------------|
| **server** | Python / pytest | 1,136 | `server/tests/zentao_testcase_map.json` | `[server] [TC-SXXXX]` |
| **web** | TypeScript / Vitest | 170 | `web/src/zentao_testcase_map.json` | `[web] [TC-WXXXX]` |
| **cli** | Go / go test | 77 | `cli/zentao_testcase_map.json` | `[cli] [TC-CXXXX]` |
| **execution_agent** | Go / go test | 75 | `execution_agent/zentao_testcase_map.json` | `[execution_agent] [TC-AXXXX]` |
| **总计** | | **1,458** | | |

[用例库链接](http://10.98.72.23:9000/index.php?m=caselib&f=browse&libID=1)

### testcase 结构

每条 zentao testcase 包含 3 步：

```
步骤1: 前置条件: 来源: server; Epic: Agent管理; Feature: Agent信号量与并发控制
步骤2: 场景: 场景 A：一个 task 期望顺序执行...
步骤3: 执行: test_sequential_task_waits_for_busy_agent() → 预期: ...
```

### domain 区分

testcase 按 **来源/域** 两级组织，标题带来源前缀。涉及多域的联动测试（scenario / integration / functional）归入对应 domain module，steps 描述中注明依赖的其他域。

### @pytest.mark.zentao 标记

每条 server 测试函数有对应的 Zentao ID 标记：

```python
@pytest.mark.zentao("TC-S0001", domain="server/agent", priority="P1")
async def test_sequential_task_waits_for_busy_agent():
    ...
```

标记注册在 `server/pyproject.toml` 的 `[tool.pytest.ini_options]` → `markers`。

### AI-Tester 工作流命令

**Step 1: 创建测试单**（tester 启动时先做）

```bash
# 全量回归
python3 .agents/skills/software-team-skill/scripts/zentao/create_and_run_testtask.py \
  --scope all --issue-num <N>

# 单域测试（仅跑涉及的 domain）
python3 .agents/skills/software-team-skill/scripts/zentao/create_and_run_testtask.py \
  --scope server/agent,server/executors --issue-num <N>

# 仅创建测试单不跑测试
python3 .agents/skills/software-team-skill/scripts/zentao/create_and_run_testtask.py \
  --scope server/agent --issue-num <N> --skip-run
```

**scope 取值**：

| scope | 场景 | 描述 |
|-------|------|------|
| `all` | 迭代验证 | 全项目全量回归（所有 4 个来源） |
| `server/<domain>` | 单 issue | 仅 server 的某个域 |
| `web/<domain>` | 前端变更 | web 的某个 feature |
| `cli/<domain>` | CLI 变更 | cli 的某个 package |
| `execution_agent/<domain>` | Agent 变更 | execution_agent 的某个 package |
| 逗号分隔多域 | 跨域联动 | `server/agent,server/executors,server/services` |

**Step 2-5: 自动执行**

脚本自动完成：跑测试 → 解析报告 → 上传结果到 testtask → 输出 Gitea 评论。

**Gitea 评论格式**（极简，由脚本生成到 `state/last_testtask_comment.md`）：

```markdown
## ✅ Tester 测试完成

- **Testtask**: [#42](http://10.98.72.23:9000/testtask-view-42.html)
- **结果**: 110/1136 passed, 0 failed, 26 skipped
- **Scope**: `server/agent,server/executors`
- **用例库**: http://10.98.72.23:9000/index.php?m=caselib&f=browse&libID=1
```

### 结果上传

通过 `POST /api.php/v1/testcases/{id}/results` 上传每条结果（含 `task`, `case`, `version`, `result`, `real`）。结果聚合在 testtask 视图可查。

### 已知限制

1. **用例关联到测试单** — Zentao REST API 不支持 `linkCase`，需手动在 Web UI 关联 testcase 到 testtask
2. **Zentao module 树** — REST API 无 module 管理端点，testcase 统一放用例库，用 title 前缀 + domain 字段区分
3. **keywords 字段** — zentao-cli 不支持 `--keywords` 参数，标题已含来源/域信息故可省略
4. **Go/TS 报告解析** — `report_parsers.py` 已支持，但 `create_and_run_testtask.py` 目前对 Go/TS 项目有完整解析+上传路径，`npx vitest` / `go test` 需在本地环境可用

### 新增/更新 testcase 流程

**新功能开发：先建 testcase，再写代码**

```bash
# 1. 在 Zentao 手动建 testcase（或用 batch_create_testcases.py）
zentao testcase create --productID=3 --title="[server] [TC-S2000] 新功能 | Feature: 描述" \
  --pri=2 --type=unit --module=0

# 2. 在 Python 代码中写测试函数 + marker
# server/tests/xxx/test_new_feature.py
@pytest.mark.zentao("TC-S2000", domain="server/xxx", priority="P1")
async def test_new_feature():
    ...

# 3. 更新映射文件
# 手动编辑 server/tests/zentao_testcase_map.json，添加:
# "xxx/test_new_feature.py::test_new_feature": {"tc_local_id": "TC-S2000", "zentao_id": <id>, ...}

# 4. AI-Tester 运行时自动上传结果
python3 .agents/skills/software-team-skill/scripts/zentao/create_and_run_testtask.py \
  --scope server/xxx --issue-num <N>
```

---

## 通用禁止事项

- **不要在对话里明文显示密码**（shell 变量传递，不 echo）
- **运行期不要调 `zentao login`**（用 per-role `ZENTAO_CONFIG_FILE`）
- **不要跨角色越权**（v1.2 起：manager 只可建 4 种 task；developer/PM/tester/uiux 不可建 task；每个角色只可 close 自己 assignedTo 的 task）
- **不要在 gitea 写大段内容**（写 zentao）
- **不要创建 execution/project**（用户创建，Manager/PM 都只复用）
- **不要决定项目进度**（等用户在 gitea 评论确认）
- **不要擅自 close zentao 对象**（v1.2 起：task 由 assignedTo 角色自己 finish；story/bug 等用户"已验收"后 PM/Tester close）
- **不要 assumption 用户角色**（不确定时问）
- **不要省略 zentao url**（所有 gitea 评论必须带链接）

## 技术约束速查

> 写 zentao 内容时直接照以下命令，不调用 CLI `--pick=`/`--comment=`/`--data=`。

| 操作 | 正确命令 |
|------|---------|
| 写 spec/verify + 保留 reviewer | `curl -X PUT "$ZENTAO_URL/api.php/v2/stories/$ID" -H "Token: $TOKEN" -H "Content-Type: application/json" -d '{"spec":"<h2>...</h2>","verify":"<h3>...</h3>","reviewer":"admin","comment":"PM 规划完成"}'` |
| 验证 spec/verify 已写入 | `curl -s "$ZENTAO_URL/api.php/v1/stories/$ID" -H "Token: $TOKEN" \| python3 -c "import sys,json;d=json.load(sys.stdin);assert len(d.get('spec',''))>0"` |
| 读 story action 历史 | `python3 scripts/zentao/get_story_actions.py $ID` |
| body 字段(spec/verify/desc) | **必须用 HTML**（tag: `<h2>`, `<p>`, `<table>`, `<ul>` 等） |
| comment 字段 | **用 markdown**（表格 `\|--\|` 也可用） |
| token 过期刷新 | `bash scripts/setup_role_configs.sh --check` |
| Manager 读 zentao 受限 | `export ZENTAO_CONFIG_FILE="state/zentao-pm.json"` |

---

## 快速自检（AI 接续会话时必做）

1. `zentao --version` 确认 CLI 可用
2. 读 `credentials/gitea.ini` + `credentials/zentao.ini` 确认目标角色凭据存在
3. 确认 `state/zentao-<role>.json` 存在（否则跑 `setup_role_configs.sh`）
4. 读 `roles/<role>/_base.md` 了解权限边界
5. 输出角色声明，再开始执行
6. 读上文"技术约束速查"确认写 zentao 的正确方式
