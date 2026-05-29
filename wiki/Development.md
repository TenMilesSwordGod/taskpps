# 开发指南

## 环境搭建

```bash
# Python 后端
cd server
uv sync --dev                # 安装所有依赖(含开发依赖)

# Go CLI
cd cli
go mod download
```

## 运行测试

```bash
cd server

# 运行所有测试
uv run pytest tests/ -v

# 带覆盖率报告
uv run pytest tests/ --cov=taskpps --cov-report=term-missing

# 特定测试文件
uv run pytest tests/test_engine.py -v

# 特定测试函数
uv run pytest tests/test_engine.py::test_pipeline_success -v
```

项目目标为 **100% 测试覆盖率**。测试覆盖情况见 `server/docs/testcases.md`。

## 项目约定

### 代码规范
- Python 3.10+ 类型注解,async-first
- Pydantic v2 校验
- SQLModel 数据模型
- 函数/方法不超过 80 行
- 禁止在代码中添加注释(代码即文档)

### 包结构

```
taskpps/
├── __init__.py         # 版本导出
├── __main__.py         # `python -m taskpps` 入口
├── main.py             # FastAPI 应用创建、生命周期、CLI 入口
├── config.py           # 配置模型、项目目录工具函数
├── i18n.py             # 国际化 (zh/en)
├── version.py          # __version__ = "0.1.0"
├── api/                # REST API 路由
│   ├── health.py
│   ├── runs.py
│   └── triggers.py
├── db/                 # 数据库
│   ├── engine.py       # 异步引擎、会话工厂
│   └── repository.py   # CRUD 仓库
├── domain/             # 领域模型
│   ├── pipeline.py     # 流水线领域对象
│   ├── dag.py          # DAG 拓扑排序
│   └── context.py      # 执行上下文
├── engine/             # 执行引擎
│   └── runner.py       # PipelineRunner
├── events/             # 事件总线
│   └── bus.py
├── executors/          # 执行器
│   ├── base.py         # 抽象基类
│   ├── local.py        # 本地 Shell
│   ├── ssh.py          # SSH 远程
│   └── invoke.py       # Python 函数
├── loaders/            # 配置加载器
│   ├── pipeline_loader.py
│   ├── agent_loader.py
│   └── credential_loader.py
├── middleware/          # FastAPI 中间件
│   └── auth.py         # API 密钥认证
├── models/             # 数据模型
│   ├── run.py          # PipelineRun, TaskRun
│   └── trigger.py      # Trigger
├── plugins/            # 插件
│   ├── base.py         # 插件基类
│   └── cron_trigger.py # Cron 触发器
├── schemas/            # Pydantic 模式
│   ├── pipeline.py     # YAML 解析
│   ├── run.py          # API 请求/响应
│   └── trigger.py      # 触发器模式
└── services/           # 业务逻辑
    ├── pipeline_service.py
    ├── trigger_service.py
    └── plugin_manager.py
```

### 测试规范
- 测试文件命名:`test_<module>.py`
- fixture 集中在 `conftest.py`
- 使用临时目录和 SQLite 内存数据库
- 每个模块一个测试文件(复杂模块可拆分 `test_<module>_extra.py`)
