from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, model_validator


class InvokeSpec(BaseModel):
    task: str
    args: list[Any] = Field(default_factory=list)
    kwargs: dict[str, Any] = Field(default_factory=dict)


class TaskStep(BaseModel):
    run: str
    cd: str | None = None
    env: dict[str, str] = Field(default_factory=dict)


class ArtifactDeclaration(BaseModel):
    path: str


class TaskYAML(BaseModel):
    name: str
    command: str | None = None
    commands: list[str] | None = None
    invoke: InvokeSpec | None = None
    steps: list[TaskStep] | None = None
    plugin: str | None = None
    params: dict[str, Any] | None = None
    cwd: str | None = None
    host: str | None = None
    credential: str | None = None
    env: dict[str, str] = Field(default_factory=dict)
    timeout: int | None = None
    retry: int = 0
    on_failure: str | None = None
    depends_on: list[str] = Field(default_factory=list)
    when: str | None = None
    artifacts: list[ArtifactDeclaration] = Field(default_factory=list)
    post: PostConfig | None = None

    def get_task_type(self) -> str:
        if self.invoke is not None:
            return "invoke"
        if self.steps is not None:
            return "steps"
        if self.plugin is not None:
            return "plugin"
        return "command"

    def get_effective_command(self) -> str | None:
        if self.command:
            return self.command
        if self.commands:
            return self.commands[0] if len(self.commands) == 1 else None
        return None


class PipelineConfig(BaseModel):
    host: str | None = None
    credential: str | None = None
    env: dict[str, str] = Field(default_factory=dict)
    timeout: int | None = None
    retry: int = 0
    on_failure: str = "fail"
    execution_strategy: str = "sequential"
    max_concurrent_runs: int | None = None
    max_concurrent_tasks: int | None = None
    cwd: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _migrate_max_parallel(cls, values):
        # 向后兼容：max_parallel 映射到 max_concurrent_runs
        if isinstance(values, dict):
            if "max_parallel" in values and "max_concurrent_runs" not in values:
                values["max_concurrent_runs"] = values.pop("max_parallel")
            elif "max_parallel" in values and "max_concurrent_runs" in values:
                values.pop("max_parallel")  # 优先使用新字段
        return values


class OptionsYAML(PipelineConfig):
    pass


class SubPipeline(BaseModel):
    name: str
    config: PipelineConfig | None = None
    depends_on: list[str] = Field(default_factory=list)
    tasks: list[TaskYAML]
    artifacts: list[ArtifactDeclaration] = Field(default_factory=list)
    post: PostConfig | None = None

    @model_validator(mode="after")
    def _validate_unique_task_names(self) -> SubPipeline:
        # v7 (2026-08): DAG 用 {name: task} 建图，重复 task name 会静默覆盖第一个
        # 定义，随后报「循环依赖」或漏跑任务；保存阶段直接拒绝
        seen: set[str] = set()
        for task in self.tasks:
            if task.name in seen:
                raise ValueError(f"duplicate task name in subpipeline '{self.name}': {task.name}")
            seen.add(task.name)
        return self


class PostConfig(BaseModel):
    on_fail: list[TaskYAML] = Field(default_factory=list)
    on_success: list[TaskYAML] = Field(default_factory=list)
    always: list[TaskYAML] = Field(default_factory=list)


class PipelineYAML(BaseModel):
    name: str
    options: OptionsYAML | None = None
    config: PipelineConfig | None = None
    post: PostConfig | None = None
    tasks: list[TaskYAML] | None = None
    pipelines: list[SubPipeline] | None = None
    artifacts: list[ArtifactDeclaration] = Field(default_factory=list)

    @model_validator(mode="after")
    def _normalize(self) -> PipelineYAML:
        if self.tasks is not None and self.pipelines is None:
            sub = SubPipeline(name=self.name, tasks=self.tasks)
            if self.config:
                sub.config = self.config
            elif self.options:
                sub.config = PipelineConfig(**self.options.model_dump())
            object.__setattr__(self, "pipelines", [sub])
            object.__setattr__(self, "tasks", None)
        return self

    @model_validator(mode="after")
    def _validate_no_tasks_with_pipelines(self) -> PipelineYAML:
        # v7 (2026-08): tasks 非空且 pipelines 存在时，ResolvedPipeline 只消费
        # pipelines，顶层 tasks 被静默忽略（保存 200 但运行漏跑任务）。
        # 空数组组合（tasks: [] / pipelines: []）无数据可丢，保持兼容。
        if self.tasks and self.pipelines is not None:
            raise ValueError("'tasks' and 'pipelines' cannot be used together")
        return self

    @model_validator(mode="after")
    def _validate_unique_subpipeline_names(self) -> PipelineYAML:
        # v7 (2026-08): 重复 subpipeline name 时 get_subpipeline_by_name 只命中
        # 第一个，第二个静默不执行；保存阶段直接拒绝
        if self.pipelines:
            seen: set[str] = set()
            for sub in self.pipelines:
                if sub.name in seen:
                    raise ValueError(f"duplicate subpipeline name: {sub.name}")
                seen.add(sub.name)
        return self

    def get_effective_config(self) -> PipelineConfig:
        if self.config:
            return self.config
        if self.options:
            return PipelineConfig(**self.options.model_dump())
        return PipelineConfig()
