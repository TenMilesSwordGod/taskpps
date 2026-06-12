import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import StaticPool
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
async def db_engine():
    mark_external_engine()
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        echo=False,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
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
        await conn.execute(text("DELETE FROM projects"))
