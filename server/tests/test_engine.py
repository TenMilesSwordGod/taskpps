from taskpps.domain.context import ExecutionContext
from taskpps.domain.pipeline import ResolvedPipeline, ResolvedTask
from taskpps.engine.runner import PipelineRunner, get_active_runner
from taskpps.schemas.pipeline import OptionsYAML


def test_get_active_runner_empty():
    result = get_active_runner("nonexistent")
    assert result is None


def test_pipeline_runner_init():
    pipeline = ResolvedPipeline(
        name="test",
        tasks=[ResolvedTask(name="t1", task_type="command", command="echo hi")],
        options=OptionsYAML(),
    )
    ctx = ExecutionContext(pipeline=pipeline, run_id="test123")
    runner = PipelineRunner(run_id="test123", pipeline=pipeline, context=ctx)
    assert runner.run_id == "test123"
    assert runner._cancelled is False
    assert runner._task_run_ids == {}
