import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool
from sqlmodel import SQLModel

from taskpps.db.engine import get_engine, reset_engine, set_engine
from taskpps.main import app


@pytest.fixture(scope="session")
def tmp_project(tmp_path_factory):
    project_dir = tmp_path_factory.mktemp("project")
    pipelines_dir = project_dir / "pipelines"
    pipelines_dir.mkdir()
    agents_dir = project_dir / "agents"
    agents_dir.mkdir()
    credentials_dir = project_dir / "credentials"
    credentials_dir.mkdir()
    tasks_dir = project_dir / "tasks"
    tasks_dir.mkdir()
    plugins_dir = project_dir / "plugins"
    plugins_dir.mkdir()

    config_yaml = project_dir / "taskpps.yaml"
    config_yaml.write_text(
        "server:\n  host: 127.0.0.1\n  port: 26521\n"
        "executor:\n  default_timeout: 60\n  max_workers: 4\n"
        "env:\n  GLOBAL_VAR: global_value\n"
        "plugins:\n  paths: ['plugins']\n"
        "triggers: []\n"
    )

    deploy_yaml = pipelines_dir / "deploy.yaml"
    deploy_yaml.write_text(
        "name: deploy\n"
        "options:\n"
        "  env:\n"
        "    APP_ENV: staging\n"
        "  timeout: 60\n"
        "  on_failure: fail\n"
        "tasks:\n"
        "  - name: step1\n"
        "    command: echo hello\n"
        "  - name: step2\n"
        "    command: echo world\n"
        "    depends_on: [step1]\n"
    )

    simple_yaml = pipelines_dir / "simple.yaml"
    simple_yaml.write_text(
        "name: simple\n"
        "options:\n"
        "  on_failure: continue\n"
        "tasks:\n"
        "  - name: task-a\n"
        "    command: echo a\n"
        "  - name: task-b\n"
        "    command: echo b\n"
    )

    fail_yaml = pipelines_dir / "fail_test.yaml"
    fail_yaml.write_text(
        "name: fail_test\n"
        "options:\n"
        "  on_failure: fail\n"
        "tasks:\n"
        "  - name: will-fail\n"
        "    command: exit 1\n"
        "  - name: after-fail\n"
        "    command: echo should not run\n"
        "    depends_on: [will-fail]\n"
    )

    continue_yaml = pipelines_dir / "continue_test.yaml"
    continue_yaml.write_text(
        "name: continue_test\n"
        "options:\n"
        "  on_failure: continue\n"
        "tasks:\n"
        "  - name: will-fail\n"
        "    command: exit 1\n"
        "  - name: independent\n"
        "    command: echo ok\n"
    )

    cycle_yaml = pipelines_dir / "cycle.yaml"
    cycle_yaml.write_text(
        "name: cycle\n"
        "options: {}\n"
        "tasks:\n"
        "  - name: a\n"
        "    command: echo a\n"
        "    depends_on: [b]\n"
        "  - name: b\n"
        "    command: echo b\n"
        "    depends_on: [a]\n"
    )

    timeout_yaml = pipelines_dir / "timeout_test.yaml"
    timeout_yaml.write_text(
        "name: timeout_test\noptions: {}\ntasks:\n  - name: slow-task\n    command: sleep 30\n    timeout: 2\n"
    )

    invoke_yaml = pipelines_dir / "invoke_test.yaml"
    invoke_yaml.write_text(
        "name: invoke_test\noptions: {}\ntasks:\n  - name: hello\n    invoke:\n      task: sample_tasks.hello\n"
    )

    diamond_yaml = pipelines_dir / "diamond.yaml"
    diamond_yaml.write_text(
        "name: diamond\n"
        "options:\n"
        "  on_failure: fail\n"
        "tasks:\n"
        "  - name: a\n"
        "    command: echo a\n"
        "  - name: b\n"
        "    command: echo b\n"
        "    depends_on: [a]\n"
        "  - name: c\n"
        "    command: echo c\n"
        "    depends_on: [a]\n"
        "  - name: d\n"
        "    command: echo d\n"
        "    depends_on: [b, c]\n"
    )

    multi_sub_yaml = pipelines_dir / "multi_sub.yaml"
    multi_sub_yaml.write_text(
        "name: multi_sub\n"
        "options:\n"
        "  on_failure: fail\n"
        "pipelines:\n"
        "  - name: build\n"
        "    tasks:\n"
        "      - name: compile\n"
        "        command: echo compile\n"
        "      - name: test\n"
        "        command: echo test\n"
        "        depends_on: [compile]\n"
        "  - name: deploy\n"
        "    depends_on: [build]\n"
        "    tasks:\n"
        "      - name: upload\n"
        "        command: echo upload\n"
        "      - name: restart\n"
        "        command: echo restart\n"
        "        depends_on: [upload]\n"
    )

    continue_diamond_yaml = pipelines_dir / "continue_diamond.yaml"
    continue_diamond_yaml.write_text(
        "name: continue_diamond\n"
        "options:\n"
        "  on_failure: continue\n"
        "tasks:\n"
        "  - name: a\n"
        "    command: echo a\n"
        "  - name: b\n"
        "    command: exit 1\n"
        "    depends_on: [a]\n"
        "  - name: c\n"
        "    command: echo c\n"
        "    depends_on: [a]\n"
        "  - name: d\n"
        "    command: echo d\n"
        "    depends_on: [b, c]\n"
    )

    sample_tasks = tasks_dir / "sample_tasks.py"
    sample_tasks.write_text("def hello():\n    print('hello from invoke')\n    return 'hello'\n")

    agent_yaml = agents_dir / "staging-server.yaml"
    agent_yaml.write_text("host: 127.0.0.1\nport: 22\nusername: test\n")

    agent_list_yaml = agents_dir / "ssh.yaml"
    agent_list_yaml.write_text(
        "agents:\n"
        "  - id: api-agent-a\n"
        "    host: 127.0.0.1\n"
        "    port: 22\n"
        "    name: API Agent A\n"
        "    type: local\n"
        "  - id: api-agent-b\n"
        "    host: 10.0.0.1\n"
        "    port: 22\n"
        "    name: API Agent B\n"
        "    type: ssh-key\n"
    )

    cred_yaml = credentials_dir / "default-cred.yaml"
    cred_yaml.write_text("password: testpass\n")

    return project_dir


@pytest.fixture(autouse=True)
def setup_project(tmp_project):
    import taskpps.config as cfg

    cfg._project_root = tmp_project
    cfg._server_home = tmp_project
    cfg._project_workdir = tmp_project
    cfg._settings = None
    cfg.load_settings(str(tmp_project / "taskpps.yaml"))
    yield


@pytest_asyncio.fixture
async def db_engine(tmp_path):
    mark_external_engine()
    # 使用文件数据库 + NullPool，避免内存数据库在 engine.dispose() 后被销毁，
    # 导致孤儿后台任务报 "no such table" 错误。每个测试有独立的临时文件，
    # 仍然保持隔离性。
    db_file = tmp_path / "test.db"
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{db_file}",
        echo=False,
        connect_args={"check_same_thread": False},
        poolclass=NullPool,
    )
    set_engine(engine)
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    yield engine
    await engine.dispose()
    reset_engine()


def mark_external_engine():
    from taskpps.main import mark_external_engine as _mark

    _mark()


@pytest_asyncio.fixture
async def client(db_engine):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture
async def clean_db(db_engine):
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.execute(text("DELETE FROM task_retry_records"))
        await conn.execute(text("DELETE FROM task_runs"))
        await conn.execute(text("DELETE FROM runs"))
        await conn.execute(text("DELETE FROM triggers"))
        await conn.execute(text("DELETE FROM pipeline_definitions"))
        await conn.execute(text("DELETE FROM projects"))


# Phase 2 (2026-07): 辅助函数 — 通过文件名获取 definition_id
# 所有 create_run 测试从 pipeline="xxx.yaml" 改为 definition_id=UUID
# 若项目未注册则自动注册，确保列表API能同步 pipeline_definitions
async def resolve_def_id(client: AsyncClient, file_name: str) -> str:
    """调用列表API同步pipeline_definitions，返回指定文件的definition_id"""
    resp = await client.get("/api/pipelines/")
    assert resp.status_code == 200
    items = resp.json().get("items", [])
    for item in items:
        if item.get("file") == file_name and item.get("id"):
            return item["id"]
    raise AssertionError(
        f"Definition not found for {file_name}. "
        f"Ensure the project is registered in DB (call ProjectRepository.create_project first) "
        f"and the YAML file exists in the pipelines directory. "
        f"Available items: {[(i.get('file'), i.get('id')) for i in items]}"
    )
