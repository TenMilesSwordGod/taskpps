from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class DescribeRequest(BaseModel):
    jsonrpc: str = "2.0"
    method: str = "describe"
    id: int = 1


class DescribeResponse(BaseModel):
    name: str
    type: str
    version: str = "0.0.0"
    help_msg: str = ""
    hooks: list[str] | None = Field(default_factory=list)
    params_schema: dict[str, Any] | None = Field(default_factory=dict)
    config_schema: dict[str, Any] | None = Field(default_factory=dict)


class DescribeRPCResponse(BaseModel):
    jsonrpc: str = "2.0"
    result: DescribeResponse
    id: int = 1


class HookEventRequest(BaseModel):
    jsonrpc: str = "2.0"
    method: str
    params: dict[str, Any] = Field(default_factory=dict)
    id: int = 1


class ExecuteRequest(BaseModel):
    jsonrpc: str = "2.0"
    method: str = "execute"
    params: dict[str, Any] = Field(default_factory=dict)
    id: int = 1


class ExecuteResult(BaseModel):
    success: bool
    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0


class ExecuteRPCResponse(BaseModel):
    jsonrpc: str = "2.0"
    result: ExecuteResult
    id: int = 1


class ShutdownRequest(BaseModel):
    jsonrpc: str = "2.0"
    method: str = "on_shutdown"
    id: int = 1
