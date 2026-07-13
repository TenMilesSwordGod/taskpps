from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from taskpps.domain.context import ExecutionContext
from taskpps.domain.pipeline import ResolvedPipeline, ResolvedTask
from taskpps.engine.runner import PipelineRunner
from taskpps.main import app as _app
from taskpps.schemas.pipeline import OptionsYAML


def _setup_config(tmp_project):
    import taskpps.config as cfg

    cfg.set_project_root(tmp_project)
    cfg._settings = None
    cfg.load_settings(str(tmp_project / "taskpps.yaml"))


def make_pipeline(name="test", tasks=None, options=None):
    if tasks is None:
        tasks = [ResolvedTask(name="t1", task_type="command", command="echo hi")]
    return ResolvedPipeline(name=name, tasks=tasks, options=options or OptionsYAML())


class TestPipelineTraversal:
    @pytest.mark.zentao("TC-S0075", domain="server/integration", priority="P1")
    def test_sequential_tasks(self):
        tasks = [
            ResolvedTask(name="clone", task_type="command", command="git clone"),
            ResolvedTask(name="build", task_type="command", command="make"),
            ResolvedTask(name="deploy", task_type="command", command="kubectl apply"),
        ]
        pipeline = ResolvedPipeline(name="ci", tasks=tasks, options=OptionsYAML(on_failure="fail"))
        ctx = ExecutionContext(pipeline=pipeline, run_id="traversal-1")
        runner = PipelineRunner(run_id="traversal-1", pipeline=pipeline, context=ctx)
        assert runner.run_id == "traversal-1"

    @pytest.mark.zentao("TC-S0076", domain="server/integration", priority="P0")
    def test_dag_traversal(self):
        tasks = [
            ResolvedTask(name="a", task_type="command", command="echo a"),
            ResolvedTask(name="b", task_type="command", command="echo b", depends_on=["a"]),
            ResolvedTask(name="c", task_type="command", command="echo c", depends_on=["a"]),
            ResolvedTask(name="d", task_type="command", command="echo d", depends_on=["b", "c"]),
        ]
        pipeline = ResolvedPipeline(name="dag-test", tasks=tasks, options=OptionsYAML())
        ctx = ExecutionContext(pipeline=pipeline, run_id="dag-1")
        runner = PipelineRunner(run_id="dag-1", pipeline=pipeline, context=ctx)
        assert runner.run_id == "dag-1"

    @pytest.mark.zentao("TC-S0077", domain="server/integration", priority="P0")
    def test_on_failure_fail(self):
        tasks = [
            ResolvedTask(name="step1", task_type="command", command="echo step1"),
            ResolvedTask(name="step2", task_type="command", command="echo step2", depends_on=["step1"]),
        ]
        pipeline = ResolvedPipeline(name="halt-test", tasks=tasks, options=OptionsYAML(on_failure="fail"))
        assert pipeline.options.on_failure == "fail"

    @pytest.mark.zentao("TC-S0078", domain="server/integration", priority="P0")
    def test_on_failure_continue(self):
        tasks = [
            ResolvedTask(name="step1", task_type="command", command="echo step1"),
            ResolvedTask(name="step2", task_type="command", command="echo step2", depends_on=["step1"]),
        ]
        pipeline = ResolvedPipeline(name="continue-test", tasks=tasks, options=OptionsYAML(on_failure="continue"))
        assert pipeline.options.on_failure == "continue"


class TestWorkspacePropagation:
    @pytest.mark.zentao("TC-S0079", domain="server/integration", priority="P1")
    def test_workspace_env(self):
        pipeline = ResolvedPipeline(
            name="test",
            tasks=[ResolvedTask(name="t1", task_type="command", command="echo", env={"WS": "/workspace"})],
            options=OptionsYAML(env={"GLOBAL": "1"}),
        )
        ctx = ExecutionContext(pipeline=pipeline, run_id="ws-1", env={"CLI": "2"})
        task = pipeline.tasks[0]
        task_env = ctx.get_task_env(task)
        assert task_env.get("WS") == "/workspace"
        assert task_env.get("GLOBAL") == "1"
        assert task_env.get("CLI") == "2"

    @pytest.mark.zentao("TC-S0080", domain="server/integration", priority="P2")
    def test_workspace_priority(self):
        pipeline = ResolvedPipeline(
            name="test",
            tasks=[ResolvedTask(name="t1", task_type="command", command="echo", env={"KEY": "task"})],
            options=OptionsYAML(env={"KEY": "pipeline"}),
        )
        ctx = ExecutionContext(pipeline=pipeline, run_id="ws-2", env={"KEY": "cli"})
        task = pipeline.tasks[0]
        task_env = ctx.get_task_env(task)
        assert task_env["KEY"] == "cli"


class TestPipelineLoading:
    @pytest.mark.zentao("TC-S0081", domain="server/integration", priority="P2")
    def test_load_and_resolve_pipeline(self, setup_project, tmp_project):
        _setup_config(tmp_project)
        from taskpps.domain.pipeline import ResolvedPipeline
        from taskpps.loaders.pipeline_loader import PipelineLoader

        loader = PipelineLoader(tmp_project / "pipelines")
        spec = loader.load("deploy.yaml")
        pipeline = ResolvedPipeline.from_yaml(spec, "deploy.yaml")
        assert pipeline.name == "deploy"
        assert len(pipeline.tasks) == 2
        assert pipeline.tasks[0].name == "step1"
        assert pipeline.tasks[1].depends_on == ["step1"]

    @pytest.mark.zentao("TC-S0082", domain="server/integration", priority="P2")
    def test_load_with_agent_resolution(self, setup_project, tmp_project):
        from taskpps.loaders.agent_loader import AgentLoader
        from taskpps.loaders.pipeline_loader import PipelineLoader

        loader = PipelineLoader(tmp_project / "pipelines")
        spec = loader.load("deploy.yaml")
        assert spec.name == "deploy"
        assert len(spec.tasks) == 2

        agent_loader = AgentLoader(tmp_project / "agents")
        agent = agent_loader.load("staging-server")
        assert agent["host"] == "127.0.0.1"

    @pytest.mark.zentao("TC-S0083", domain="server/integration", priority="P2")
    def test_credential_loading(self, setup_project, tmp_project):
        from taskpps.loaders.credential_loader import CredentialLoader

        cred_loader = CredentialLoader(tmp_project / "credentials")
        cred = cred_loader.load("default-cred")
        assert cred["password"] == "testpass"


class TestIntegrationEndToEnd:
    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0084", domain="server/integration", priority="P0")
    async def test_full_run_flow(self, setup_project, tmp_project, db_engine):
        _setup_config(tmp_project)
        transport = ASGITransport(app=_app)

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            create_resp = await client.post(
                "/api/runs/",
                json={"pipeline": "deploy.yaml", "params": {}},
            )
            assert create_resp.status_code in (200, 201)
            run_id = create_resp.json()["id"]

            get_resp = await client.get(f"/api/runs/{run_id}")
            assert get_resp.status_code == 200
            data = get_resp.json()
            assert data["id"] == run_id
            assert data["pipeline_name"] == "deploy"

            list_resp = await client.get("/api/runs/")
            assert list_resp.status_code == 200
            list_data = list_resp.json()
            assert list_data["total"] >= 1

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0085", domain="server/integration", priority="P2")
    async def test_triggers_endpoint(self, setup_project, tmp_project, db_engine):
        _setup_config(tmp_project)
        transport = ASGITransport(app=_app)

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            create_resp = await client.post(
                "/api/plugins/triggers/",
                json={"type": "cron", "config": {"schedule": "0 * * * *"}, "definition_id": "deploy.yaml"},
            )
            assert create_resp.status_code in (200, 201)

            list_resp = await client.get("/api/plugins/triggers/")
            assert list_resp.status_code == 200
            triggers = list_resp.json()
            assert isinstance(triggers, list)


class TestCoverageGaps:
    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0086", domain="server/integration", priority="P2")
    async def test_main_app_startup(self, setup_project, tmp_project):
        _setup_config(tmp_project)
        transport = ASGITransport(app=_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/api/health")
            assert resp.status_code == 200

    @pytest.mark.zentao("TC-S0087", domain="server/integration", priority="P2")
    def test_event_bus_singleton(self):
        from taskpps.events.bus import get_event_bus

        bus1 = get_event_bus()
        bus2 = get_event_bus()
        assert bus1 is bus2

    @pytest.mark.zentao("TC-S0088", domain="server/integration", priority="P2")
    def test_event_bus_subscribe_and_emit(self):
        from taskpps.events.bus import get_event_bus

        bus = get_event_bus()
        called = []

        def handler(sender, **kwargs):
            called.append(kwargs)

        bus.on("test_event", handler)
        bus.emit("test_event", data={"key": "value"})
        assert len(called) == 1
        bus.off("test_event", handler)

    @pytest.mark.zentao("TC-S0089", domain="server/integration", priority="P2")
    def test_event_bus_unsubscribe(self):
        from taskpps.events.bus import get_event_bus

        bus = get_event_bus()
        called = []

        def handler(sender, **kwargs):
            called.append(kwargs)

        bus.on("test_event", handler)
        bus.off("test_event", handler)
        bus.emit("test_event", data={"key": "value"})
        assert len(called) == 0

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0090", domain="server/integration", priority="P1")
    async def test_create_run_pipeline_not_found(self, setup_project, tmp_project, db_engine):
        _setup_config(tmp_project)
        transport = ASGITransport(app=_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/api/runs/",
                json={"pipeline": "nonexistent.yaml", "params": {}},
            )
            assert resp.status_code in (400, 404, 422)

    @pytest.mark.asyncio
    @pytest.mark.zentao("TC-S0091", domain="server/integration", priority="P1")
    async def test_cancel_run_not_found(self, setup_project, tmp_project, db_engine):
        _setup_config(tmp_project)
        transport = ASGITransport(app=_app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/api/runs/nonexistent/cancel")
            assert resp.status_code in (400, 404)

    @pytest.mark.zentao("TC-S0092", domain="server/integration", priority="P2")
    def test_events_bus_emit(self):
        from taskpps.events.bus import get_event_bus

        bus = get_event_bus()
        caught = {}

        def handler(sender, **kwargs):
            caught["data"] = kwargs

        bus.on("test_event", handler)
        bus.emit("test_event", data={"key": "value"})
        assert caught.get("data") == {"data": {"key": "value"}}
        bus.off("test_event", handler)

    @pytest.mark.zentao("TC-S0093", domain="server/integration", priority="P2")
    def test_events_bus_multiple_handlers(self):
        from taskpps.events.bus import get_event_bus

        bus = get_event_bus()
        results = []

        def handler1(sender, **kwargs):
            results.append(("h1", kwargs))

        def handler2(sender, **kwargs):
            results.append(("h2", kwargs))

        bus.on("test_event", handler1)
        bus.on("test_event", handler2)
        bus.emit("test_event", data={"key": "value"})
        assert len(results) == 2
        bus.off("test_event", handler1)
        bus.off("test_event", handler2)

