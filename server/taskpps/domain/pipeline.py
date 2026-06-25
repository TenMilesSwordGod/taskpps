from __future__ import annotations

from typing import Any

from taskpps.schemas.pipeline import (
    OptionsYAML,
    PipelineConfig,
    PipelineYAML,
    SubPipeline,
    TaskStep,
    TaskYAML,
)


class ResolvedStep:
    def __init__(self, run: str, cd: str | None = None, env: dict[str, str] | None = None):
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
        command: str | None = None,
        commands: list[str] | None = None,
        invoke_task: str | None = None,
        invoke_args: list[Any] | None = None,
        invoke_kwargs: dict[str, Any] | None = None,
        steps: list[ResolvedStep] | None = None,
        git: dict[str, Any] | None = None,
        nexus: dict[str, Any] | None = None,
        cwd: str | None = None,
        host: str | None = None,
        credential: str | None = None,
        env: dict[str, str] | None = None,
        timeout: int | None = None,
        retry: int = 0,
        on_failure: str | None = None,
        depends_on: list[str] | None = None,
        when: str | None = None,
        artifacts: list[dict[str, str]] | None = None,
    ):
        self.name = name
        self.task_type = task_type
        self.command = command
        self.commands = commands or []
        self.invoke_task = invoke_task
        self.invoke_args = invoke_args or []
        self.invoke_kwargs = invoke_kwargs or {}
        self.steps = steps
        self.git = git or {}
        self.nexus = nexus or {}
        self.cwd = cwd
        self.host = host
        self.credential = credential
        self.env = env or {}
        self.timeout = timeout
        self.retry = retry
        self.on_failure = on_failure
        self.depends_on = depends_on or []
        self.when = when
        self.artifacts = artifacts or []

    @classmethod
    def from_yaml(
        cls, task_yaml: TaskYAML, config: PipelineConfig | OptionsYAML | None = None, options: OptionsYAML | None = None
    ) -> ResolvedTask:
        if config is None:
            config = options or PipelineConfig()
        if isinstance(config, OptionsYAML):
            config = PipelineConfig(**config.model_dump())
        resolved_steps = None
        if task_yaml.steps:
            resolved_steps = [ResolvedStep.from_yaml(s) for s in task_yaml.steps]

        resolved_git = None
        if task_yaml.git:
            resolved_git = task_yaml.git.model_dump()

        resolved_nexus = None
        if task_yaml.nexus:
            resolved_nexus = task_yaml.nexus.model_dump()

        return cls(
            name=task_yaml.name,
            task_type=task_yaml.get_task_type(),
            command=task_yaml.command,
            commands=task_yaml.commands,
            invoke_task=task_yaml.invoke.task if task_yaml.invoke else None,
            invoke_args=task_yaml.invoke.args if task_yaml.invoke else [],
            invoke_kwargs=task_yaml.invoke.kwargs if task_yaml.invoke else {},
            steps=resolved_steps,
            git=resolved_git,
            nexus=resolved_nexus,
            cwd=task_yaml.cwd or config.cwd,
            host=task_yaml.host or config.host,
            credential=task_yaml.credential or config.credential,
            env={**config.env, **task_yaml.env},
            timeout=task_yaml.timeout or config.timeout,
            retry=task_yaml.retry if task_yaml.retry > 0 else config.retry,
            on_failure=task_yaml.on_failure or config.on_failure,
            depends_on=task_yaml.depends_on,
            when=task_yaml.when,
            artifacts=[{"path": a.path} for a in task_yaml.artifacts],
        )


class ResolvedSubPipeline:
    def __init__(
        self,
        name: str,
        tasks: list[ResolvedTask],
        config: PipelineConfig,
        depends_on: list[str] | None = None,
        artifacts: list[dict[str, str]] | None = None,
    ):
        self.name = name
        self.tasks = tasks
        self.config = config
        self.depends_on = depends_on or []
        self.artifacts = artifacts or []

    @classmethod
    def from_yaml(cls, sub: SubPipeline, top_config: PipelineConfig) -> ResolvedSubPipeline:
        merged_config = _merge_config(top_config, sub.config)
        tasks = [ResolvedTask.from_yaml(t, merged_config) for t in sub.tasks]
        return cls(
            name=sub.name,
            tasks=tasks,
            config=merged_config,
            depends_on=sub.depends_on,
            artifacts=[{"path": a.path} for a in sub.artifacts],
        )

    def get_task_by_name(self, name: str) -> ResolvedTask | None:
        for t in self.tasks:
            if t.name == name:
                return t
        return None


class ResolvedPipeline:
    def __init__(
        self,
        name: str,
        tasks: list[ResolvedTask] | None = None,
        options: PipelineConfig | OptionsYAML | None = None,
        subpipelines: list[ResolvedSubPipeline] | None = None,
        top_config: PipelineConfig | None = None,
        pipeline_file: str = "",
        artifacts: list[dict[str, str]] | None = None,
    ):
        self.name = name
        self.pipeline_file = pipeline_file
        self.artifacts = artifacts or []

        if subpipelines is not None:
            self.subpipelines = subpipelines
            self.top_config = top_config or PipelineConfig()
        elif tasks is not None:
            config = options
            if isinstance(config, OptionsYAML):
                config = PipelineConfig(**config.model_dump())
            if config is None:
                config = PipelineConfig()
            self.subpipelines = [ResolvedSubPipeline(name=name, tasks=tasks, config=config)]
            self.top_config = config
        else:
            self.subpipelines = []
            self.top_config = top_config or PipelineConfig()

    @classmethod
    def from_yaml(cls, spec: PipelineYAML, pipeline_file: str = "") -> ResolvedPipeline:
        top_config = spec.get_effective_config()
        subs: list[ResolvedSubPipeline] = []
        if spec.pipelines:
            for sub in spec.pipelines:
                subs.append(ResolvedSubPipeline.from_yaml(sub, top_config))
        return cls(
            name=spec.name,
            subpipelines=subs,
            top_config=top_config,
            pipeline_file=pipeline_file,
            artifacts=[{"path": a.path} for a in spec.artifacts],
        )

    def get_subpipeline_by_name(self, name: str) -> ResolvedSubPipeline | None:
        for s in self.subpipelines:
            if s.name == name:
                return s
        return None

    def get_task_by_name(self, name: str) -> ResolvedTask | None:
        for t in self.tasks:
            if t.name == name:
                return t
        return None

    @property
    def tasks(self) -> list[ResolvedTask]:
        result = []
        for s in self.subpipelines:
            result.extend(s.tasks)
        return result

    @property
    def options(self) -> PipelineConfig:
        return self.top_config


def _merge_config(top: PipelineConfig, override: PipelineConfig | None) -> PipelineConfig:
    if override is None:
        return top
    return PipelineConfig(
        host=override.host if override.host is not None else top.host,
        credential=override.credential if override.credential is not None else top.credential,
        env={**top.env, **override.env},
        timeout=override.timeout if override.timeout is not None else top.timeout,
        retry=override.retry if override.retry > 0 else top.retry,
        on_failure=override.on_failure if override.on_failure != "fail" or top.on_failure == "fail" else top.on_failure,
        execution_strategy=override.execution_strategy
        if override.execution_strategy != "sequential" or top.execution_strategy == "sequential"
        else top.execution_strategy,
        max_concurrent_runs=override.max_concurrent_runs
        if override.max_concurrent_runs is not None
        else top.max_concurrent_runs,
        max_concurrent_tasks=override.max_concurrent_tasks
        if override.max_concurrent_tasks is not None
        else top.max_concurrent_tasks,
        cwd=override.cwd if override.cwd is not None else top.cwd,
    )
