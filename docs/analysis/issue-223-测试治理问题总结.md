# issue #223 测试治理：存量问题总结（2026-09-13）

> 分支：`test/issue-223-test-quality-governance`
> 范围：server / execution_agent / web（按用户确认，CLI 不纳入本轮；Zentao 服务 403，映射先落本地 pending）

## 一、本轮已完成

| 提交 | 端 | 内容 |
|---|---|---|
| `ae60873` | execution_agent | 修复非 root 必失败红测试（改为可控子进程）；删除 38 条注水/重复、重写 10 条、新增 34 条有效用例；覆盖率 agent 46.6%→84.9%、cmd 19.9%→59.6%；修复 `executor.go` stdout/result 消息顺序竞态（`-race` 可复现）；映射 90 条（active 40 + pending 50） |
| `e1e228a` | server | 无验证测试 49 候选→11（余下均为审计判定保留的合理 smoke）；跨文件重复测试体 10 组/22 函数→1 组/2 函数；修复 HEAD 上 8 个测试文件缺 `import pytest`（导致 `pytest tests/` 收集中断，CI 从未真正跑完）；映射 1771 条（active 1117 + pending 654），僵尸/重复 ID/未映射/marker 冲突全部为 0；退役映射 65 条记录在 `scripts/test_governance/retired_mappings.json` |

治理工具：`scripts/test_governance/check_mapping_consistency.py`（跨端映射一致性校验）、`backfill_pending_mappings.py`（Zentao 恢复后回填 pending 用例）。

## 二、存量失败分类（HEAD 基线即失败，本机归因 175/176）

本机全量 `pytest tests/`：176 failed / 1606 passed。逐一归因后的类别：

| # | 类别 | 数量（约） | 代表用例 | 根因 | 性质 |
|---|---|---|---|---|---|
| 1 | **JWT 未登录 401** | ~105 | `tests/api/test_agents.py::test_try_connect`、`tests/functional/test_retry_functional.py::test_retry_full_flow` | issue #204 JWT 中间件对 POST/PUT/DELETE 强制鉴权，大量 API/functional/integration/scenario/artifacts 测试未登录就调用写接口 | 测试债（产品行为符合 #204 spec） |
| 2 | **definition_id 变更未同步** | 34 | `tests/services/test_pipeline.py::TestPipelineServiceMore::test_create_run_with_config_env` | 2026-07 起 `create_run` 只收 UUID，部分测试仍传文件名 → `ValueError: Definition not found` | 测试债 |
| 3 | **loader 返回 None 解引用** | 13 | `tests/loaders/test_loaders.py::TestPipelineLoader::test_load`（`spec.tasks[0]`） | `spec` 为 None，需确认 loader 是否真实返回 None | **待定位（疑似产品缺陷）** |
| 4 | **pydantic schema 过期** | 9 | `tests/schemas/test_schemas.py` | 构造参数与现 schema 不符被 ValidationError 拒绝 | 测试债 |
| 5 | **mock 目标已不存在** | 2+ | `tests/api/test_agents.py`（patch `taskpps.api.agents.manager`/`AgentBootstrap`） | 重构后模块属性移除，测试未更新 | 测试债 |
| 6 | **其他待定位** | 若干 | `tests/agent/test_service.py::test_parses_lscpu_cores_threads`（`memory.percent` 解析为 0）、`tests/integration/test_integration.py:124`（NoneType has no len）、`test_create_run_stores_snapshot_in_db`（顺序相关） | 环境或产品逻辑待查 | **疑似真 bug / 状态泄漏** |

## 三、高风险候选（建议优先定位）

1. `taskpps/services/agent_service.py` 的 `_probe_remote_host_info` 内存解析：mock 提供 `MemAvailable` 却得到 `percent=0`
2. `tests/integration` 中返回 None 的链路（`len(None)`）
3. 全局状态/DB 泄漏导致的顺序相关失败（`test_create_run_stores_snapshot_in_db` 单跑通过）
4. `taskpps/main.py:292` 日志仍称 "No API key configured — all API endpoints are accessible without authentication"（API key 机制已被 JWT 取代，误导运维）

## 四、遗留治理缺口（未做）

- server S2：`POST /api/agents/check-stream`、`POST /api/agents/update-deploy`、`GET /api/runs/{id}/result` 3 个路由无测试；错误 `detail` 断言 244 处 status 仅 17 处 detail；api/auth.py 硬编码中文与 `t()` 混用
- web：`zentao_testcase_map.json` 170 条 vs 实际测试函数 874 个；1 条映射指向已不存在文件
- 映射回填：server 654 + agent 50 条 pending，待 Zentao 恢复后执行 `backfill_pending_mappings.py`

## 五、复现命令

```bash
# 全量回归（本机存量失败见上表）
cd server && .venv/bin/python -m pytest tests -q

# 映射一致性（应 0 违规）
server/.venv/bin/python scripts/test_governance/check_mapping_consistency.py server --source-root server/tests
server/.venv/bin/python scripts/test_governance/check_mapping_consistency.py execution_agent --source-root execution_agent

# agent 端
cd execution_agent && go test ./... -count=1 -cover
```
