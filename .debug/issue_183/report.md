# issue #183 验证报告：web UI 触发运行 400 `UnboundLocalError: get_pipelines_dir`

- Issue: http://10.98.72.23:8418/AM-SYS/taskpps/issues/183
- 角色: developer（快速路径 E；禅道 403 不可用，经用户批准跳过 zentao task/记录）
- 验证时间: 2026-09-13 16:26 (+08:00)
- 验证时 HEAD: `f16ff4d4c3657b4ea22cd113683b27a2d9eceeca`
- 结论: **根因成立；当前 main 已修复；生产部署代码与工作区一致；本次 0 行生产代码改动**

---

## 1. 结论摘要

| 项 | 结论 |
|----|------|
| 根因诊断 | ✅ 成立。旧版 `create_run` 中 `from taskpps.config import get_pipelines_dir` 是条件分支内的局部 import，导致该名字在整个函数作用域成为局部变量；不带 `project_id` 的请求走 else 分支时 import 未执行，函数内无条件调用 `get_pipelines_dir()` 抛 `UnboundLocalError` |
| 旧代码复现 | ✅ 用 409f536 真实 `create_run` + AST/exec 复现，包装后的错误消息与 issue 报告逐字一致 |
| 当前 main 已修复 | ✅ 现有回归测试 6 passed；独立脚本验证不传 `project_id` 正常创建 run |
| 生产部署 | ✅ `/opt/taskpps/server` 与工作区文件 `diff` 无差异，且无函数内局部 `get_pipelines_dir` import |
| 同类风险 | 扫描 `server/taskpps/` 85 个文件，1 处疑似（`agent_bootstrap.py:421`），人工判定为误报/安全 |
| 代码改动 | 无（修复在 `e480b9f` 已存在） |

---

## 2. 复现历史 bug（证明根因诊断正确）

**方法**（脚本 `.debug/issue_183/repro_unbound_local.py`）：
1. `git show 409f536:server/taskpps/services/pipeline_service.py` 提取旧文件（不改工作区 HEAD），用 AST 抠出其真实 `create_run` 函数体；
2. 注入最小 stub（`get_settings` / `ProjectRepository` 返回 1 个假项目 / 假 session），走「`project_id=None` → else 分支遍历项目」路径；
3. Part 1 另用等价最小函数直白展示 Python 作用域规则，与 Part 2 交叉印证。

**执行命令与关键输出**：

```bash
server/.venv/bin/python .debug/issue_183/repro_unbound_local.py
```

```
[Part 1] 等价最小函数
  -> UnboundLocalError: cannot access local variable 'get_pipelines_dir' where it is not associated with a value

[Part 2] 真实旧版 create_run（409f536, AST 提取）
  -> ValueError（生产 API 包装后返回的 400 detail）: 加载流水线失败:cannot access local variable 'get_pipelines_dir' where it is not associated with a value
  -> __cause__: UnboundLocalError: cannot access local variable 'get_pipelines_dir' where it is not associated with a value
  -> 根因判定: 匹配 UnboundLocalError(get_pipelines_dir)

REPRO OK: 历史 bug 已在旧版 create_run 上复现，根因 = UnboundLocalError('get_pipelines_dir')
```

Part 2 输出的 `ValueError` 消息与 issue 报告的 400 detail（`加载流水线失败:cannot access local variable 'get_pipelines_dir' ...`）**逐字一致**，异常链 `ValueError.__cause__ = UnboundLocalError` 证明根因诊断正确：

- 旧文件 409f536 中，模块级 L12-20 本已 `from taskpps.config import get_pipelines_dir`；
- 但 `create_run` 内 L160（`if project_id:` → `if project_workdir:` 分支内）又做了一次局部 `from taskpps.config import get_pipelines_dir`；
- Python 编译期把 `get_pipelines_dir` 视为整个 `create_run` 的局部变量，模块级 import 被遮蔽；
- 请求不带 `project_id`（旧前端 body `{"pipeline":"03-subpipelines.yaml","params":{}}`）→ L160 不执行 → L176 `get_pipelines_dir(proj.workdir)` 抛 `UnboundLocalError`，被 L190 `except Exception` 包装为 `ValueError("加载流水线失败: ...")` → API 返回 400。

---

## 3. 当前 main 已修复验证

### 3.1 现有回归测试

```bash
cd server && .venv/bin/python -m pytest tests/services/test_create_run_by_definition.py -q
# 6 passed in 1.34s
```

### 3.2 独立验证脚本（不传 project_id 的真实路径）

`server/tests/` 之外的独立脚本 `.debug/issue_183/verify_issue_183.py`：自建临时项目目录 + sqlite 库，注册 project/definition 后直接调用
`PipelineService().create_run(definition_id)`（**不传 project_id**，即旧 bug 触发形态）。

```bash
server/.venv/bin/python .debug/issue_183/verify_issue_183.py
# PASS: create_run(definition_id) 不传 project_id 正常返回 run_id=44a3e2fd98ec pipeline_name=deploy，无 UnboundLocalError
# exit=0
```

### 3.3 生产部署代码比对

```bash
diff server/taskpps/services/pipeline_service.py /opt/taskpps/server/taskpps/services/pipeline_service.py
# NO_DIFF（无差异）

grep -n "get_pipelines_dir" /opt/taskpps/server/taskpps/services/pipeline_service.py
# 19:    get_pipelines_dir,          ← 模块级 import（多行 import 的一部分）
# 194:            loader = PipelineLoader(base_dir=get_pipelines_dir(project_workdir))
# 221:            pipelines_dir=get_pipelines_dir(project_workdir) if project_workdir else None,
# 310:        pipelines_dir = get_pipelines_dir(Path(project_workdir) if project_workdir else None)
```

对两份文件进一步做「函数内局部 import」检查（`^[[:space:]]+(from|import) `），当前 main 与生产部署 L55~L1106 的局部 import 列表**完全相同**，且**均不含 `get_pipelines_dir`**；`create_run` 内的两个局部 import 为 `PipelineDefinitionRepository`（L168，函数顶层，先于使用）与 `get_settings`（L179，try 块内，使用点在同一块之后），均无遮蔽风险。

### 3.4 涉及 commit

| 角色 | commit | 日期 | 说明 |
|------|--------|------|------|
| 引入 | `cd63807` | 2026-06-10 | `feat(server): 引入 Project 模型，实现 code/project 解耦`，首次在 `create_run` 内加入局部 `from taskpps.config import get_pipelines_dir` |
| bug 快照 | `409f536` | 2026-07-03 | issue 报告时 main 的形态（局部 import 仍在，复现基线） |
| 修复 | `e480b9f` | 2026-07-13 | PR #191 `feat: Phase 2 - Pipeline URL UUID路由 + 快照存DB`，重构后删除全部局部 `get_pipelines_dir` import，统一为模块级 import；`create_run` 改为 definition_id 驱动，project_id 从 definition 解析，不再走「无 project_id 遍历项目」分支 |

---

## 4. 同类风险静态扫描（只报告，不修复）

**方法**（脚本 `.debug/issue_183/scan_local_import_shadow.py`）：AST 扫描 `server/taskpps/**/*.py`，对每个函数收集「局部 import 绑定」与「同名 Name 使用点」，并记录 import 所在的受控块容器路径；仅当使用点确实位于 import 所在块内（容器路径前缀匹配）且行号在后才判安全。该算法能覆盖 409f536 那种「使用行在 import 行之后、但位于互斥分支」的隐蔽形态，行号先后启发式会漏报。

**扫描器自检**（对 409f536 旧文件，应命中已知 bug）：

```
.debug/issue_183/old_pipeline_service_409f536.py:176 函数 create_run() 内局部 import 'get_pipelines_dir'（L160(条件块内)）；模块级同名绑定: import L12 → 危险使用行: [176, 213]
自检结果: 命中已知 bug（扫描器有效）
```

**当前生产代码扫描结果**：共 85 个文件，发现 1 处疑似风险：

| 位置 | 描述 | 判定 |
|------|------|------|
| `server/taskpps/services/agent_bootstrap.py:421` | 函数 `_get_external_ip()` 内局部 `import netifaces`（L417，`try` 块内），使用行 421/423/426/427 位于 try 块外 | **误报/非风险**。L418-419 `except ImportError: netifaces = None` 保证该名字在任何到达 L421 的路径上都已绑定（可选依赖标准写法），不会 UnboundLocalError |

**结论：除上述已判定安全的误报外，未发现同类 `UnboundLocalError` 风险；`get_pipelines_dir` 形态的风险在当前 main 已不存在。**

---

## 5. 证据文件清单（均在 `.debug/issue_183/`）

| 文件 | 说明 |
|------|------|
| `repro_unbound_local.py` | 历史 bug 最小复现（等价函数 + 409f536 真实 `create_run` AST/exec） |
| `verify_issue_183.py` | 当前 main 真实路径验证（不传 project_id） |
| `scan_local_import_shadow.py` | 同类风险 AST 扫描器（含旧文件自检） |
| `old_pipeline_service_409f536.py` | 从 git 提取的旧版文件（证据，保持原样未改） |
| `report.md` | 本报告 |
| `status.json` | 阶段状态 |

所有脚本经 `server/.venv/bin/ruff check` + `ruff format --check` 通过。

---

## 6. 偏差与不确定项

1. **zentao 跳过**：禅道当前 403 不可用，经用户批准本工单不建 zentao task、不写 zentao 记录，仅更新 status.json + Gitea 评论。
2. **复现脚本使用 stub 绕开真实 DB/settings**：仅用于在旧代码上触发作用域异常；异常发生在调用 `get_pipelines_dir` 处，与 DB 实现无关，且外层错误消息与真实 API 返回逐字一致，证据强度足够。
3. **生产运行进程未重启验证**：仅能确认磁盘代码 `/opt/taskpps/server` 与修复版一致（diff 无差异、无局部 import），无法从进程外确认运行中 gunicorn 已加载该文件；如需 100% 确认可重启服务后复测接口。
