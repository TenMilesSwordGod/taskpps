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
    def _normalize(self) -> "PipelineYAML":
        if self.tasks is not None and self.pipelines is None:
            sub = SubPipeline(name=self.name, tasks=self.tasks)
            if self.config:
                sub.config = self.config
            elif self.options:
                sub.config = PipelineConfig(**self.options.model_dump())
            object.__setattr__(self, "pipelines", [sub])
            object.__setattr__(self, "tasks", None)
        return self

    def get_effective_config(self) -> PipelineConfig:
        if self.config:
            return self.config
        if self.options:
            return PipelineConfig(**self.options.model_dump())
        return PipelineConfig()
