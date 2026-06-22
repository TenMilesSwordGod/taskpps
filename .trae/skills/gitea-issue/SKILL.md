---
name: "gitea-issue"
description: "Gitea 工单驱动开发工作流。当用户提供 Gitea 工单 URL 时自动触发，获取工单内容并按 TDD 流程完成开发、提交和推送。"
---

# Gitea Issue 驱动开发工作流

根据 Gitea 工单内容，按标准化流程完成开发、测试、提交和推送。

## 触发条件

当用户提供 Gitea 工单 URL 时触发，格式如：
- `gitea-issue: http://homeserver02.sh.nas.com:8418/AM-SYS/taskpps/issues/90`
- 或直接给出 URL：`http://.../issues/XX`

## 工作流程

### 第 1 步：获取工单内容

使用脚本获取工单详情和所有评论：

```bash
python3 .trae/skills/gitea-issue/scripts/fetch_issue.py "<issue_url>"
```

如果需要 JSON 格式（便于程序解析）：

```bash
python3 .trae/skills/gitea-issue/scripts/fetch_issue.py "<issue_url>" --format json
```

**重要**：必须获取所有评论，评论中可能包含用户反馈、补充说明或需求变更。

### 第 2 步：分析需求

获取工单后，仔细分析：

1. **工单类型**：Bug 修复 / 新功能 / 优化 / 重构
2. **影响范围**：前端 / 后端 / 全栈
3. **关键需求**：提取核心要求，不要遗漏
4. **评论要点**：评论中的反馈和补充说明

如果需求不明确或有歧义，**必须**使用 AskUserQuestion 工具向用户确认，提供至少 3 个备选项。

### 第 3 步：制定计划

使用 TodoWrite 工具创建任务列表，包含：

1. 需求分析结果
2. 代码修改计划（列出要修改的文件和原因）
3. 测试计划（先写测试，再写代码 — TDD）
4. 验证步骤

### 第 4 步：TDD 开发

严格遵循 TDD 原则：

1. **先写测试**：根据需求编写测试用例
2. **运行测试**：确认测试失败（红灯）
3. **编写代码**：实现功能使测试通过
4. **运行测试**：确认测试通过（绿灯）
5. **重构**：优化代码，确保测试仍通过

测试运行方式：
- 后端：`cd server && python -m pytest tests/<相关测试文件> -v`
- 前端：`cd web && npx vitest run src/<相关测试文件>`

### 第 5 步：代码质量检查

完成开发后，运行 lint 和类型检查：

```bash
# 后端
cd server && ruff check . && ruff format --check .

# 前端
cd web && npx tsc --noEmit
```

### 第 6 步：提交和推送

完成开发并通过测试、lint 检查后，默认自动提交并推送到 Gitea，无需额外询问用户：

```bash
# 提交变更
git add <具体文件>
git commit -m "fix/feat/refactor: 简要描述 (#工单号)"

# 推送到 Gitea（默认推送到 origin）
git push origin <branch>
```

**注意**：
- 默认推送到 `origin`（Gitea），不推送到 `github`
- 仅在用户明确要求时才推送到 GitHub
- 提交信息格式：`类型: 描述 (#工单号)`，类型包括 fix/feat/refactor/docs/test
- 如果工作区没有变更，跳过提交直接推送

### 第 7 步：在工单下添加评论

**每次完成工单后，必须默认在工单下添加评论**，总结完成的工作：

```bash
python3 .trae/skills/gitea-issue/scripts/comment_issue.py "<issue_url>" "评论内容"
```

评论内容模板：
```
已完成 [Bug修复/新功能/优化]，提交 commit: `<commit_message>`

[简要说明修改了什么文件、做了哪些改动]

[如涉及测试：所有 X 个测试已通过]
已推送到 origin/<branch>。
```

示例：
```bash
python3 .trae/skills/gitea-issue/scripts/comment_issue.py \
  "http://homeserver02.sh.nas.com:8418/AM-SYS/taskpps/issues/90" \
  "已完成 Bug 修复，提交 commit: \`fix: 修复变量替换问题 (#90)\`

修改了 \`server/taskpps/engine/pipeline_loader.py\`，新增 \`project_workdir\` 参数支持。
所有测试已通过，已推送到 origin/main。"
```

也可以从文件读取评论内容：
```bash
python3 .trae/skills/gitea-issue/scripts/comment_issue.py "<issue_url>" --file comment.md
```

### 第 8 步：前端验证（如涉及前端）

如果工单涉及前端修改，使用 MCP 工具操作浏览器验证：

1. 确认开发服务器正在运行
2. 使用 MCP TalkToFigma 工具检查 UI（如适用）
3. 验证功能是否符合预期
4. 检查响应式布局和交互

## 需要用户确认的场景

以下情况**必须**使用 AskUserQuestion 工具向用户确认，并提供至少 3 个备选项：

1. **需求不明确**：工单描述有歧义，需要确认具体实现方式
2. **技术方案选择**：有多种实现方案，需要用户选择
3. **影响范围确认**：修改可能影响其他功能，需要确认
4. **设计决策**：UI/UX 相关的选择（颜色、布局、交互方式等）

## 可用辅助 Skill

- **grill-me**：当需要深入讨论技术方案或设计决策时使用
- **ui-ux-pro-max**：当涉及 UI/UX 设计时使用
- **no-fallback-no-mock**：确保代码质量，避免静默降级
- **find-skills**：查找其他可能有用的 skill

## 工具使用指南

### Gitea API 信息

- Gitea 服务器：`http://10.98.72.23:8418`
- 仓库：`AM-SYS/taskpps`
- Git remote `origin`：Gitea（默认推送目标）
- Git remote `github`：GitHub（仅用户明确要求时推送）
- 认证：URL 中已嵌入凭据，无需额外 Token

### MCP TalkToFigma

当需要操作 Figma 设计稿或检查前端 UI 时使用：

1. 先用 `get_document_info` 获取文档信息
2. 用 `get_selection` 获取当前选中
3. 用 `read_my_design` 读取设计
4. 根据需要进行操作

## 完整示例

用户输入：`http://homeserver02.sh.nas.com:8418/AM-SYS/taskpps/issues/87`

1. 获取工单：
```bash
python3 .trae/skills/gitea-issue/scripts/fetch_issue.py "http://homeserver02.sh.nas.com:8418/AM-SYS/taskpps/issues/87"
```

2. 分析：Bug — 变量替换不成功，`${agent:X.host}` 未被替换

3. 制定计划：修改 `pipeline_loader.py`，新增 `project_workdir` 参数

4. TDD 开发：
   - 先写测试 `test_agent_variable_substitution_with_project_dir`
   - 运行测试确认失败
   - 修改代码
   - 运行测试确认通过

5. Lint 检查：`ruff check . && ruff format --check .`

6. 提交推送：`git push origin main`

7. 工单评论：
```bash
python3 .trae/skills/gitea-issue/scripts/comment_issue.py \
  "http://homeserver02.sh.nas.com:8418/AM-SYS/taskpps/issues/87" \
  "已完成 Bug 修复，提交 commit: \`fix: 修复变量替换问题 (#87)\`

修改了 \`pipeline_loader.py\`，新增 \`project_workdir\` 参数。
所有测试已通过，已推送到 origin/main。"
```

8. 前端验证：如涉及前端，用 MCP 工具检查
