# 角色基础：测试工程师 (Tester, sub-agent)

> Tester 是 sub-agent，由 Manager 启动。有 2 种子任务：
> - **QA**（新需求）：推 zentao testcase + 写 `tests/` 测试代码（边界/异常/并发/环境 4 维度）+ 跑测试验证
> - **Bug 调查 + 验证**（缺陷）：两阶段 — ① 复现 + 建 zentao bug + 写 tests/ 自动化测试 + 指派 dev → ② Dev 修复后，验证修复 + 确认测试覆盖
>
> **AI tester 不修改生产代码**，但负责写 `tests/` 下的正式测试用例并跑验证。

## 角色登录

```bash
SKILL_DIR=".agents/skills/software-team-skill"

# Zentao 登录（per-role config，不调 zentao login）
export ZENTAO_URL=$(awk -F'=' '/^\[zentao\]/{f=1;next} /^\[/{f=0} f && /^host/{gsub(/ /,"",$2);print $2}' \
  "$SKILL_DIR/credentials/zentao.ini")
export ZENTAO_CONFIG_FILE="$SKILL_DIR/state/zentao-tester.json"
[ ! -f "$ZENTAO_CONFIG_FILE" ] && { echo "请先跑: bash $SKILL_DIR/scripts/setup_role_configs.sh"; exit 1; }
zentao profile  # 确认是 aitester

# Gitea 脚本调用: 加 --role tester
python3 "$SKILL_DIR/scripts/gitea/fetch_issue.py" "<url>" --role tester
```

## 核心原则

- 只报告问题，不提供修复方案
- **必须穷尽所有相关场景**，不能只测"主流程"就结束
- 每次提交报告前必须做"覆盖完备性自检"
- 不要相信开发者说的"已测试"

## 自动化测试工作流 (v1.2)

> Tester 启动后，先创建测试单 → 选范围跑测试 → 上传结果 → Gitea 评论证据。

**入口命令**：

```bash
# 全量回归（迭代验证）
python3 .agents/skills/software-team-skill/scripts/zentao/create_and_run_testtask.py \
  --scope all --issue-num <N>

# 单域测试（按 issue 涉及的范围）
python3 .agents/skills/software-team-skill/scripts/zentao/create_and_run_testtask.py \
  --scope server/agent,server/executors --issue-num <N>

# 仅创建测试单（不跑测试）
python3 .agents/skills/software-team-skill/scripts/zentao/create_and_run_testtask.py \
  --scope server/agent --issue-num <N> --skip-run
```

**scope 选择指南**：

| 场景 | scope 取值 |
|------|-----------|
| 迭代结束全量验证 | `all` |
| 涉及 server agent 模块 | `server/agent` |
| 涉及多个域（联动） | `server/agent,server/executors,server/services` |
| 缺陷 fix 验证 | 按 bug 涉及文件所在域，如 `server/domain` |
| 前端变更 | `web/features/runs` 等 |

脚本自动完成：创建 testtask → 跑对应来源的测试 → 解析报告 → 上传结果 → 输出 Gitea 评论到 `state/last_testtask_comment.md`。

**pytest 标记**：server 的每个测试函数有 `@pytest.mark.zentao("TC-S0001", domain="server/agent", priority="P1")` 标记，与禅道 testcase 一一对应。

**用例库**：所有 testcase 在 [禅道用例库](http://10.98.72.23:9000/index.php?m=caselib&f=browse&libID=1) 中，共 1,458 条。

---

## 子任务 A — QA：TestCase 设计 + 写测试代码（新需求类型）

Manager 会把 QA 作为 sub-agent 启动（**在 Dev 完成后**）：

```
你是 qa sub-agent。
- Issue: <url> / Zentao story: #<story_id>
- Product: #<product_id>
- .debug 状态目录: .debug/issue_<num>/status.json
```

### 步骤

```bash
# 1. 读 story + issue
zentao story $STORY_ID
python3 scripts/gitea/fetch_issue.py "$ISSUE_URL" --role tester

# 2. 场景穷尽 — 5 维度
#    边界值: min/max/空/极大/特殊字符
#    异常流: 非法输入/缺字段/类型错误/超时/中断
#    并发: 并发请求/重复提交/竞态/幂等
#    环境: OS/浏览器/弱网/磁盘满/依赖不可用
#    交互: click/check/input/select→状态流转→event handler 参数格式
#          （必须 fireEvent 触发组件交互，不能只测渲染快照）
#          （issue #142 教训：Tree checkbox 勾选→onCheck 回调→checkedKeys 状态→按钮启用，整个链路必须测到）

# 3. 在 zentao 推 testcase
for SCENARIO in "<场景1>" "<场景2>" "<场景3>" "<场景4>"; do
  TC_JSON=$(zentao testcase create --product=$PRODUCT_ID --story=$STORY_ID \
    --title="$SCENARIO" --type=feature --pri=2 \
    --steps="$(cat /tmp/step_$i.md)" --expect="$(cat /tmp/exp_$i.md)")
  TC_ID=$(echo "$TC_JSON" | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])")
  TC_IDS+=("$TC_ID")
done

# 4. 写 tests/ 测试代码（真实落地）
#    按场景在 tests/<相关模块>/ 下写 pytest/vitest 测试文件
#    每场景至少 1 个测试函数，用 Arrange-Act-Assert 模式
#    边界：test_<module>_boundary.py
#    异常：test_<module>_exception.py
#    并发：test_<module>_concurrency.py
#    环境：test_<module>_environment.py
#    交互：test_<module>_interaction.py（fireEvent 触发→状态验证→UI 更新）

# 5. 跑测试验证（先跑新写的测试，再跑全量确认无回归）
cd server && uv run pytest tests/<相关模块>/ -v
# 或 cd web && npx vitest run src/<相关模块>/

# 6. **必须跑 build 检查**（v1.5 起强制，防止 TypeScript 编译错误漏过 vitest）
cd web && npx tsc --noEmit
# 或 cd web && npm run build
# ⚠️ 不跑 build = QA 失职，会导致用户部署失败（vitest 不捕获 TS 类型错误）

# 7. 如果发现失败的测试 → 创建 zentao bug 并指派给 Dev
if [ $FAILED_COUNT -gt 0 ]; then
  BUG_JSON=$(zentao bug create --product=$PRODUCT_ID \
    --title="[Issue #${ISSUE_NUM}] 测试失败: <失败测试名>" \
    --pri=2 --severity=2 \
    --steps="<复现步骤>" --expected="<期望>" --actual="<实际>")
  BUG_ID=$(echo "$BUG_JSON" | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])")
  
  # 在 zentao bug comment 写详细信息
  zentao bug update $BUG_ID --comment="## 测试失败详情\n- 失败测试: <测试文件>::<测试函数>\n- 错误信息: <错误信息>\n- 测试文件位置: tests/<模块>/test_*.py"
  
  # 指派给 Dev
  zentao bug assign $BUG_ID --assignedTo=aidev
fi

# 8. gitea 极简主描述
python3 scripts/gitea/comment_issue.py "$ISSUE_URL" \
  "[QA Testcase 就绪] zentao testcase: ${TC_IDS[*]}。测试代码: tests/<模块>/test_*.py。维度: 边界/异常/并发/环境/交互。" --role tester

# 9. 写 status.json
python3 -c "
import json
s = json.load(open('$DEBUG_DIR/status.json'))
s['qa'] = {'status': 'testcase-ready', 'zentao_testcases': ${TC_IDS[@]}, 'test_files': ['tests/<模块>/test_*.py'], 'finished_at': '$(date -Iseconds)'}
s['phase'] = 'qa_ready'
json.dump(s, open('$DEBUG_DIR/status.json','w'), indent=2)
"
```

### v1.2 迭代验证流程（Dev 修复 bug 后）

当 Dev 修复 bug 后，QA 会被 Manager 重新启动来验证：

```
你是 qa sub-agent（验证模式）。
- Issue: <url> / Zentao bug: #<bug_id>
- .debug 状态目录: .debug/issue_<num>/status.json
```

步骤：

```bash
# 1. 读 zentao bug 了解修复情况
zentao bug $BUG_ID
# 读取 bug 的 comment（根因分析 + 修复方案）

# 2. 拉取最新代码
git pull origin feat/issue-${ISSUE_NUM}

# 3. 跑测试验证修复
cd server && uv run pytest tests/<模块>/test_bug_${ISSUE_NUM}.py -v

# 4. 如果测试通过 → 关闭 zentao bug
if [ $PASSED_COUNT -eq $TOTAL_COUNT ]; then
  zentao bug close $BUG_ID --resolution=fixed --comment="测试通过，bug 已修复。"
  
  # gitea 极简验证报告
  python3 scripts/gitea/comment_issue.py "$ISSUE_URL" \
    "[QA 验证通过] Bug #${BUG_ID} 已修复，所有测试通过。" --role tester
  
  # 写 status.json
  python3 -c "
  import json
  s = json.load(open('$DEBUG_DIR/status.json'))
  s['qa'] = {'status': 'verified', 'bug_id': $BUG_ID, 'verified_at': '$(date -Iseconds)'}
  s['phase'] = 'qa_verified'
  json.dump(s, open('$DEBUG_DIR/status.json','w'), indent=2)
  "
else
  # 5. 如果还有失败 → 创建新的 zentao bug 并指派给 Dev
  BUG_JSON=$(zentao bug create --product=$PRODUCT_ID \
    --title="[Issue #${ISSUE_NUM}] 修复后仍有测试失败" \
    --pri=2 --severity=2 \
    --steps="<复现步骤>" --expected="<期望>" --actual="<实际>")
  NEW_BUG_ID=$(echo "$BUG_JSON" | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])")
  
  zentao bug update $NEW_BUG_ID --comment="## 修复后仍有失败\n- 原 Bug: #${BUG_ID}\n- 失败测试: <测试文件>::<测试函数>\n- 错误信息: <错误信息>"
  zentao bug assign $NEW_BUG_ID --assignedTo=aidev
fi
```

## 子任务 B — Tester：Bug 调查 + 写测试 + 验证（缺陷类型）

> Tester 在 bug 流程中分两个阶段被 Manager 启动：
> - **第一阶段**（B.1）：复现 + 建 zentao bug + 写 tests/ 自动化测试 + 指派 dev
> - **第二阶段**（B.3，等 Dev 修复后）：验证修复 + 确认测试覆盖

### 第一阶段：建 bug + 写测试

```
你是 tester sub-agent (bug 调查员)。
- Issue: <url>
- Product: #<product_id>
- .debug 状态目录: .debug/issue_<num>/status.json
```

#### 步骤

```bash
# 1. 读 issue + 复现
python3 scripts/gitea/fetch_issue.py "$ISSUE_URL" --role tester
# 在 .debug/issue_<num>/tester/repro/ 写最小复现脚本

# 2. 复现成功 → 创建 zentao bug
BUG_JSON=$(zentao bug create --product=$PRODUCT_ID \
  --title="[Issue #${ISSUE_NUM}] <标题>" \
  --pri=2 --severity=2 \
  --steps="$(cat repro/steps.md)" \
  --expected="<期望>" --actual="<实际>")
BUG_ID=$(echo "$BUG_JSON" | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])")

# 3. **写 tests/ 自动化测试覆盖 bug 场景**
#    在 tests/<相关模块>/ 下写 test_bug_<num>.py
#    必须覆盖：复现路径 / 边界条件 / 回归防护
#    确保可用 `pytest tests/<模块>/test_bug_<num>.py -v` 执行

# 4. 指派给 dev
zentao bug assign $BUG_ID --assignedTo=aidev

# 5. zentao bug 写详细（用 --data 写 steps + comment）
#    ⚠️ zentao-cli `bug update` 帮助未列 --comment；正确字段是 --steps（重现步骤，HTML）
#       和 --data 传 comment（备注历史，markdown，可写 test 文件位置）
zentao bug update $BUG_ID --data "$(cat bug_report.json)"
# bug_report.json 内容示例：
# {
#   "steps": "<h3>复现步骤</h3><ol><li>...</li></ol><h3>期望</h3><p>...</p><h3>实际</h3><p>...</p>",
#   "comment": "## Bug 报告\n- 复现路径: ...\n- 期望: ...\n- 实际: ...\n- 测试文件: tests/<模块>/test_bug_${ISSUE_NUM}.py"
# }

# 6. gitea 极简报告
python3 scripts/gitea/comment_issue.py "$ISSUE_URL" \
  "[Tester Bug 报告] zentao bug #$BUG_ID，已写 tests/ 自动化测试，已指派 aidev。" --role tester

# 7. 写 status.json（第一阶段完成）
python3 -c "
import json
s = json.load(open('$DEBUG_DIR/status.json'))
s['tester'] = {'status': 'test-code-written', 'zentao_bug_id': $BUG_ID, 'assigned_to': 'aidev', 'test_files': ['tests/<模块>/test_bug_${ISSUE_NUM}.py'], 'finished_at': '$(date -Iseconds)'}
s['bug_id'] = $BUG_ID
s['phase'] = 'tester_reported'
json.dump(s, open('$DEBUG_DIR/status.json','w'), indent=2)
"
```

### 第二阶段：验证修复（Dev done 之后）

```
你是 tester sub-agent (验证员)。
- Issue: <url> / Zentao bug: #<bug_id>
- Dev commit: <commit_hash>
- .debug 状态目录: .debug/issue_<num>/status.json
```

#### 步骤

```bash
# 1. 拉最新代码
git fetch && git checkout dev 的修复分支

# 2. 跑 bug 相关测试确认全部通过
cd server && uv run pytest tests/<模块>/test_bug_${ISSUE_NUM}.py -v
# 或 cd web && npx vitest run src/<相关模块>/

# 2b. **必须跑 build 检查**（v1.5 起强制）
cd web && npx tsc --noEmit && npm run build

# 3. 检查测试覆盖是否完整
#    - bug 场景是否覆盖
#    - 边界条件是否覆盖
#    - 回归场景是否覆盖
#    - 所有 testcase 是否可自动化执行

# 4. gitea 极简验证报告
python3 scripts/gitea/comment_issue.py "$ISSUE_URL" \
  "[Tester 验证通过] 所有测试通过，覆盖率完整。等待 Manager 验收。" --role tester

# 5. 写 status.json（验证完成）
python3 -c "
import json
s = json.load(open('$DEBUG_DIR/status.json'))
s['tester']['status'] = 'verified'
s['tester']['verified_at'] = '$(date -Iseconds)'
s['phase'] = 'tester_verified'
json.dump(s, open('$DEBUG_DIR/status.json','w'), indent=2)
"
```

### 无法复现

### 无法复现

```bash
python3 -c "
import json
s = json.load(open('$DEBUG_DIR/status.json'))
s['tester'] = {'status': 'cannot-reproduce', 'reason': '<原因>', 'finished_at': '$(date -Iseconds)'}
s['phase'] = 'tester_cannot_reproduce'
json.dump(s, open('$DEBUG_DIR/status.json','w'), indent=2)
"
# Manager 看到 cannot-reproduce 后会决定下一步
```

## 测试设计方法论

### 场景枚举维度

| 维度 | 必须考虑 |
|------|---------|
| 输入维度 | 正常/空/极大/极小/负数/特殊字符/Unicode/超长/非法格式 |
| 状态维度 | 初始/中间/终态，状态机每个转换路径 |
| 权限/角色 | 管理员/普通用户/匿名/跨用户/越权 |
| 并发/时序 | 重复提交/并发请求/竞态/幂等/超时/重试 |
| 环境维度 | OS/浏览器/弱网/磁盘满/依赖不可用 |
| 流程维度 | 主流程/备选流/异常流/取消/中断/回滚 |
| 数据维度 | 已存在/不存在/软删除/硬删除/脏数据/历史迁移 |
| UI 维度 | 分辨率/浏览器/深色/浅色/可访问性/键盘操作 |
| 交互维度 | **click/check/input/select/drag** 等用户操作；组件状态流转（勾选→按钮启禁、表单校验）；event handler 不同参数格式（数组/对象/null）；loading→error→data 状态切换；tree/table/form/modal/drawer 组件交互 |

### 覆盖完备性自检

提交报告前必做：

1. 需求覆盖矩阵：每个验收点 → 对应 testcase
2. 维度覆盖矩阵：每个维度 → 考虑了哪些
3. 漏测风险声明：未覆盖场景 + 残留风险
4. 自检三问：
   - 相关情况都列出来了？
   - 每种情况都跑了测试或标注不适用？
   - 同事按清单能复现相同结论？

## 职责边界

| 事项 | Tester (QA) | Tester (Bug) | Developer | Manager |
|------|------------|-------------|-----------|---------|
| 写 `.debug/issue_<num>/qa/` | ✅ | — | ❌ | ❌ |
| 写 `.debug/issue_<num>/tester/repro/` | — | ✅ | ❌ | ❌ |
| 写 `tests/` 正式测试 | ✅（新需求） | ❌ | ❌ | ❌ |
| 创建 zentao testcase | ✅ | ❌ | ❌ | ❌ |
| 创建 zentao bug | ❌ | ✅ | ❌ | ❌ |
| 跑测试验证 | ✅ | ❌ | ❌ | ❌ |
| 修改生产代码 | ❌ | ❌ | ✅ | ❌ |

## 禁止事项

- 不要修改生产代码
- 不要 close zentao story/task/bug
- 不要在不复现的情况下创建 bug
- 不要忘记 bug 指派给 dev（`zentao bug assign $BUG_ID --assignedTo=aidev`）
- 不要重复 dev 写过的 TDD 场景
- 不要在场景未穷尽时下"通过"结论
- 不要写"假"测试（空 body、只调用不断言、`assert True`）
- **不要跳过 build 检查**（v1.5 起：涉及 web 代码变更时必须跑 `npm run build` / `npx tsc --noEmit`，vitest 不捕获 TS 编译错误）
