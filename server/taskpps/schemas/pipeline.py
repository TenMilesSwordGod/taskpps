from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class InvokeSpec(BaseModel):
    task: str
    args: List[Any] = Field(default_factory=list)
    kwargs: Dict[str, Any] = Field(default_factory=dict)


class TaskYAML(BaseModel):
    name: str
    command: Optional[str] = None
    invoke: Optional[InvokeSpec] = None
    host: Optional[str] = None
    credential: Optional[str] = None
    env: Dict[str, str] = Field(default_factory=dict)
    timeout: Optional[int] = None
    on_failure: Optional[str] = None
    depends_on: List[str] = Field(default_factory=list)

    def get_task_type(self) -> str:
        if self.invoke is not None:
            return "invoke"
        return "command"


class OptionsYAML(BaseModel):
    host: Optional[str] = None
    credential: Optional[str] = None
    env: Dict[str, str] = Field(default_factory=dict)
    timeout: Optional[int] = None
    on_failure: str = "fail"


class PipelineYAML(BaseModel):
    name: str
    options: OptionsYAML = Field(default_factory=OptionsYAML)
    tasks: List[TaskYAML]
