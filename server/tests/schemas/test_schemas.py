from taskpps.models.trigger import TriggerType
from taskpps.schemas.pipeline import InvokeSpec, OptionsYAML, PipelineYAML, TaskYAML
from taskpps.schemas.run import CleanRequest, CreateRunRequest
from taskpps.schemas.trigger import CreateTriggerRequest


@pytest.mark.zentao("TC-S0672", domain="server/schemas", priority="P1")
def test_invoke_spec():
    spec = InvokeSpec(task="module.func", args=[1, 2], kwargs={"key": "val"})
    assert spec.task == "module.func"
    assert spec.args == [1, 2]
    assert spec.kwargs == {"key": "val"}


@pytest.mark.zentao("TC-S0673", domain="server/schemas", priority="P2")
def test_task_yaml_command():
    t = TaskYAML(name="test", command="echo hello")
    assert t.get_task_type() == "command"
    assert t.command == "echo hello"
    assert t.invoke is None


@pytest.mark.zentao("TC-S0674", domain="server/schemas", priority="P1")
def test_task_yaml_invoke():
    t = TaskYAML(name="test", invoke=InvokeSpec(task="mod.fn"))
    assert t.get_task_type() == "invoke"


@pytest.mark.zentao("TC-S0675", domain="server/schemas", priority="P2")
def test_options_yaml_defaults():
    o = OptionsYAML()
    assert o.on_failure == "fail"
    assert o.host is None
    assert o.timeout is None


@pytest.mark.zentao("TC-S0676", domain="server/schemas", priority="P2")
def test_pipeline_yaml():
    p = PipelineYAML(
        name="test",
        options=OptionsYAML(env={"KEY": "VAL"}),
        tasks=[TaskYAML(name="step1", command="echo hi")],
    )
    assert p.name == "test"
    assert len(p.tasks) == 1
    assert p.options.env["KEY"] == "VAL"


@pytest.mark.zentao("TC-S0677", domain="server/schemas", priority="P2")
def test_create_run_request():
    req = CreateRunRequest(pipeline="deploy.yaml", params={"key": "val"})
    assert req.pipeline == "deploy.yaml"
    assert req.params == {"key": "val"}


@pytest.mark.zentao("TC-S0678", domain="server/schemas", priority="P2")
def test_create_run_request_defaults():
    req = CreateRunRequest(pipeline="deploy.yaml")
    assert req.params == {}


@pytest.mark.zentao("TC-S0679", domain="server/schemas", priority="P1")
def test_clean_request():
    req = CleanRequest(older_than=7)
    assert req.older_than == 7
    assert req.force is False

    req2 = CleanRequest(force=True)
    assert req2.force is True


@pytest.mark.zentao("TC-S0680", domain="server/schemas", priority="P2")
def test_create_trigger_request():
    req = CreateTriggerRequest(type=TriggerType.CRON, config={"schedule": "0 * * * *"}, pipeline_file="deploy.yaml")
    assert req.type == TriggerType.CRON
    assert req.enabled is True

