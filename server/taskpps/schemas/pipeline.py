from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, model_validator


class InvokeSpec(BaseModel):
    task: str
    args: List[Any] = Field(default_factory=list)
    kwargs: Dict[str, Any] = Field(default_factory=dict)


class TaskStep(BaseModel):
    run: str
    cd: Optional[str] = None
    env: Dict[str, str] = Field(default_factory=dict)


class GitSpec(BaseModel):
    repo: str
    ref: Optional[str] = None
    credential: Optional[str] = None
    dest: str = "/workspace/repo"
    depth: int = 1
    submodules: bool = False


class NexusSpec(BaseModel):
    action: str
    url: str
    repository: str
    credential: Optional[str] = None
    group_id: Optional[str] = None
    artifact_id: Optional[str] = None
    version: Optional[str] = None
    packaging: str = "jar"
    classifier: Optional[str] = None
    files: Optional[List[str]] = None
    dest: Optional[str] = None
    query: Optional[str] = None
    source_repo: Optional[str] = None
    target_repo: Optional[str] = None


class TaskYAML(BaseModel):
    name: str
    command: Optional[str] = None
    commands: Optional[List[str]] = None
    invoke: Optional[InvokeSpec] = None
    steps: Optional[List[TaskStep]] = None
    git: Optional[GitSpec] = None
    nexus: Optional[NexusSpec] = None
    cwd: Optional[str] = None
    host: Optional[str] = None
    credential: Optional[str] = None
    env: Dict[str, str] = Field(default_factory=dict)
    timeout: Optional[int] = None
    retry: int = 0
    on_failure: Optional[str] = None
    depends_on: List[str] = Field(default_factory=list)
    when: Optional[str] = None

    def get_task_type(self) -> str:
        if self.invoke is not None:
            return "invoke"
        if self.steps is not None:
            return "steps"
        if self.git is not None:
            return "git"
        if self.nexus is not None:
            return "nexus"
        return "command"

    def get_effective_command(self) -> Optional[str]:
        if self.command:
            return self.command
        if self.commands:
            return self.commands[0] if len(self.commands) == 1 else None
        return None


class PipelineConfig(BaseModel):
    host: Optional[str] = None
    credential: Optional[str] = None
    env: Dict[str, str] = Field(default_factory=dict)
    timeout: Optional[int] = None
    retry: int = 0
    on_failure: str = "fail"
    execution_strategy: str = "sequential"


class OptionsYAML(PipelineConfig):
    pass


class SubPipeline(BaseModel):
    name: str
    config: Optional[PipelineConfig] = None
    depends_on: List[str] = Field(default_factory=list)
    tasks: List[TaskYAML]


class PipelineYAML(BaseModel):
    name: str
    options: Optional[OptionsYAML] = None
    config: Optional[PipelineConfig] = None
    tasks: Optional[List[TaskYAML]] = None
    pipelines: Optional[List[SubPipeline]] = None

    @model_validator(mode="after")
    def _normalize(self) -> "PipelineYAML":
        if self.tasks is not None and self.pipelines is None:
            sub = SubPipeline(name=self.name, tasks=self.tasks)
            if self.config:
                sub.config = self.config
            elif self.options:
                sub.config = PipelineConfig(**self.options.model_dump())
            object.__setattr__(self, "pipelines", [sub])
        return self

    def get_effective_config(self) -> PipelineConfig:
        if self.config:
            return self.config
        if self.options:
            return PipelineConfig(**self.options.model_dump())
        return PipelineConfig()