# Server 测试用例重构需求

## 背景

对 `server/tests/` 下所有测试用例进行全面清点和梳理，去除重复/低价值用例，按标准用例格式整理，为后续测试重构提供基础。

## 清点结果

| 项目 | 数量 |
|------|------|
| 原始总数 | 1203 |
| 去重后保留 | 1136 |
| 移除 Duplicate | 66 |
| 移除 Weak | 1 |

## 按 Epic 分布

| Epic | 数量 |
|------|------|
| 任务执行 | 253 |
| 流水线管理 | 173 |
| Agent管理 | 170 |
| 域模型 | 151 |
| 配置管理 | 109 |
| 运行管理 | 132 |
| 数据持久化 | 58 |
| 插件系统 | 32 |
| 事件系统 | 21 |
| 安全认证 | 16 |
| 国际化 | 13 |
| 应用框架 | 8 |

## 按测试类型分布

| 类型 | 数量 |
|------|------|
| Unit | 565 |
| Integration | 278 |
| Scenario | 131 |
| Boundary | 128 |
| Functional | 34 |

## 按优先级分布

| 优先级 | 数量 |
|--------|------|
| P0 | 51 |
| P1 | 499 |
| P2 | 586 |

## DB 使用情况

| 类型 | 数量 |
|------|------|
| 使用内存DB（in-memory SQLite） | 467 |
| 纯单元测试（无DB） | 669 |

## 已移除的重复用例（66条）

主要集中在：
- `plugins/test_plugins.py`：test_is_abstract / test_interface 各重复 4 次
- `models/test_models.py`：3 组测试各重复 3 次
- `loaders/test_boundary.py`：9 个函数名重复
- `config/test_config.py`：test_defaults 重复 4 次
- `schemas/test_schemas_boundary.py`：3 个函数名重复

## 已移除的低价值用例（1条）

- `test_naming.py::test_word_lists_size`：仅检查列表长度，无实际验证价值

## 完整用例清单

完整用例清单见 `server/tests/TEST_CASE_CLEAN.json`（1136条），每条包含：
- `id`：用例编号（TC-001 ~ TC-1136）
- `epic`：所属 Epic
- `feature`：功能模块
- `story`：用户故事/验证场景
- `test_name`：测试函数名
- `file`：所在文件
- `domain`：代码域
- `test_type`：Unit / Integration / Scenario / Boundary / Functional
- `priority`：P0 / P1 / P2
- `db_usage`：是否使用内存DB

## 重构任务

- [ ] 按 domain 整理测试文件结构，确保每个 domain 目录职责清晰
- [ ] 为每个 P0/P1 用例补充详细的 test steps
- [ ] 统一命名规范（test_功能_场景_预期结果）
- [ ] 合并重复覆盖的测试
- [ ] 补充缺失的边界测试
- [ ] 确保所有 Integration 测试使用内存DB（in-memory SQLite）
- [ ] 清理无用的 mock 和 setup 代码
