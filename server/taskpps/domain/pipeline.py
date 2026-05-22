from __future__ import annotations

from typing import Any, Dict, List, Optional

from taskpps.schemas.pipeline import PipelineYAML, TaskYAML, OptionsYAML, TaskStep


class ResolvedStep:
    def __init__(self, run: str, cd: Optional[str] = None, env: Optional[Dict[str, str]] = None):
        self.run = run
        self.cd = cd
        self.env = env or {}

    @classmethod
    def from_yaml(cls, step: TaskStep) -> ResolvedStep:
        return cls(run=step.run, cd=step.cd, env=step.env)


class ResolvedTask:
    def __init__(
        self,
        name: str,
        task_type: str,
        command: Optional[str] = None,
        invoke_task: Optional[str] = None,
        invoke_args: Optional[List[Any]] = None,
        invoke_kwargs: Optional[Dict[str, Any]] = None,
        steps: Optional[List[ResolvedStep]] = None,
        cwd: Optional[str] = None,
        host: Optional[str] = None,
        credential: Optional[str] = None,
        env: Optional[Dict[str, str]] = None,
        timeout: Optional[int] = None,
        on_failure: Optional[str] = None,
        depends_on: Optional[List[str]] = None,
    ):
        self.name = name
        self.task_type = task_type
        self.command = command
        self.invoke_task = invoke_task
        self.invoke_args = invoke_args or []
        self.invoke_kwargs = invoke_kwargs or {}
        self.steps = steps
        self.cwd = cwd
        self.host = host
        self.credential = credential
        self.env = env or {}
        self.timeout = timeout
        self.on_failure = on_failure
        self.depends_on = depends_on or []

    @classmethod
    def from_yaml(cls, task_yaml: TaskYAML, options: OptionsYAML) -> ResolvedTask:
        resolved_steps = None
        if task_yaml.steps:
            resolved_steps = [ResolvedStep.from_yaml(s) for s in task_yaml.steps]

        return cls(
            name=task_yaml.name,
            task_type=task_yaml.get_task_type(),
            command=task_yaml.command,
            invoke_task=task_yaml.invoke.task if task_yaml.invoke else None,
            invoke_args=task_yaml.invoke.args if task_yaml.invoke else [],
            invoke_kwargs=task_yaml.invoke.kwargs if task_yaml.invoke else {},
            steps=resolved_steps,
            cwd=task_yaml.cwd,
            host=task_yaml.host or options.host,
            credential=task_yaml.credential or options.credential,
            env={**options.env, **task_yaml.env},
            timeout=task_yaml.timeout or options.timeout,
            on_failure=task_yaml.on_failure or options.on_failure,
            depends_on=task_yaml.depends_on,
        )


class ResolvedPipeline:
    def __init__(self, name: str, tasks: List[ResolvedTask], options: OptionsYAML, pipeline_file: str = ""):
        self.name = name
        self.tasks = tasks
        self.options = options
        self.pipeline_file = pipeline_file

    @classmethod
    def from_yaml(cls, spec: PipelineYAML, pipeline_file: str = "") -> ResolvedPipeline:
        tasks = [ResolvedTask.from_yaml(t, spec.options) for t in spec.tasks]
        return cls(name=spec.name, tasks=tasks, options=spec.options, pipeline_file=pipeline_file)

    def get_task_by_name(self, name: str) -> Optional[ResolvedTask]:
        for t in self.tasks:
            if t.name == name:
                return t
        return None
