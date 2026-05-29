from __future__ import annotations

from typing import Any, Dict, List, Optional, Union

from taskpps.schemas.pipeline import (
    GitSpec,
    NexusSpec,
    OptionsYAML,
    PipelineConfig,
    PipelineYAML,
    SubPipeline,
    TaskYAML,
    TaskStep,
)


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
        commands: Optional[List[str]] = None,
        invoke_task: Optional[str] = None,
        invoke_args: Optional[List[Any]] = None,
        invoke_kwargs: Optional[Dict[str, Any]] = None,
        steps: Optional[List[ResolvedStep]] = None,
        git: Optional[Dict[str, Any]] = None,
        nexus: Optional[Dict[str, Any]] = None,
        cwd: Optional[str] = None,
        host: Optional[str] = None,
        credential: Optional[str] = None,
        env: Optional[Dict[str, str]] = None,
        timeout: Optional[int] = None,
        retry: int = 0,
        on_failure: Optional[str] = None,
        depends_on: Optional[List[str]] = None,
        when: Optional[str] = None,
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

    @classmethod
    def from_yaml(cls, task_yaml: TaskYAML, config: Union[PipelineConfig, OptionsYAML, None] = None, options: Optional[OptionsYAML] = None) -> ResolvedTask:
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
            cwd=task_yaml.cwd,
            host=task_yaml.host or config.host,
            credential=task_yaml.credential or config.credential,
            env={**config.env, **task_yaml.env},
            timeout=task_yaml.timeout or config.timeout,
            retry=task_yaml.retry if task_yaml.retry > 0 else config.retry,
            on_failure=task_yaml.on_failure or config.on_failure,
            depends_on=task_yaml.depends_on,
            when=task_yaml.when,
        )


class ResolvedSubPipeline:
    def __init__(
        self,
        name: str,
        tasks: List[ResolvedTask],
        config: PipelineConfig,
        depends_on: Optional[List[str]] = None,
    ):
        self.name = name
        self.tasks = tasks
        self.config = config
        self.depends_on = depends_on or []

    @classmethod
    def from_yaml(cls, sub: SubPipeline, top_config: PipelineConfig) -> ResolvedSubPipeline:
        merged_config = _merge_config(top_config, sub.config)
        tasks = [ResolvedTask.from_yaml(t, merged_config) for t in sub.tasks]
        return cls(name=sub.name, tasks=tasks, config=merged_config, depends_on=sub.depends_on)

    def get_task_by_name(self, name: str) -> Optional[ResolvedTask]:
        for t in self.tasks:
            if t.name == name:
                return t
        return None


class ResolvedPipeline:
    def __init__(
        self,
        name: str,
        tasks: Optional[List[ResolvedTask]] = None,
        options: Optional[Union[PipelineConfig, OptionsYAML]] = None,
        subpipelines: Optional[List[ResolvedSubPipeline]] = None,
        top_config: Optional[PipelineConfig] = None,
        pipeline_file: str = "",
    ):
        self.name = name
        self.pipeline_file = pipeline_file

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
        subs: List[ResolvedSubPipeline] = []
        if spec.pipelines:
            for sub in spec.pipelines:
                subs.append(ResolvedSubPipeline.from_yaml(sub, top_config))
        return cls(name=spec.name, subpipelines=subs, top_config=top_config, pipeline_file=pipeline_file)

    def get_subpipeline_by_name(self, name: str) -> Optional[ResolvedSubPipeline]:
        for s in self.subpipelines:
            if s.name == name:
                return s
        return None

    def get_task_by_name(self, name: str) -> Optional[ResolvedTask]:
        for t in self.tasks:
            if t.name == name:
                return t
        return None

    @property
    def tasks(self) -> List[ResolvedTask]:
        result = []
        for s in self.subpipelines:
            result.extend(s.tasks)
        return result

    @property
    def options(self) -> PipelineConfig:
        return self.top_config


def _merge_config(top: PipelineConfig, override: Optional[PipelineConfig]) -> PipelineConfig:
    if override is None:
        return top
    return PipelineConfig(
        host=override.host if override.host is not None else top.host,
        credential=override.credential if override.credential is not None else top.credential,
        env={**top.env, **override.env},
        timeout=override.timeout if override.timeout is not None else top.timeout,
        retry=override.retry if override.retry > 0 else top.retry,
        on_failure=override.on_failure if override.on_failure != "fail" or top.on_failure == "fail" else top.on_failure,
        execution_strategy=override.execution_strategy if override.execution_strategy != "sequential" or top.execution_strategy == "sequential" else top.execution_strategy,
    )