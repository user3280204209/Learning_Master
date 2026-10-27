"""Pydantic 模型：请求体、统一响应。

约定：所有接口返回 {code, message, data}。
code=0 成功；HTTP 状态码仍用于表达协议级错误（404/422/500）。
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ApiResponse(BaseModel):
    code: int = 0
    message: str = "ok"
    data: Any = None


class StudentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=50)
    major: str = Field(default="", max_length=100)
    age: int = Field(default=0, ge=0, le=120)
    goal: str = Field(default="", max_length=300)
    email: str = Field(default="", max_length=120)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    session_id: str | None = Field(default=None, max_length=64)


class ResourceGenerateRequest(BaseModel):
    student_id: int = Field(gt=0)
    topic: str = Field(min_length=1, max_length=100)
    requirements: str = Field(default="", max_length=2000)
    # 不传 = 生成全部 6 类；传了就只生成指定类型
    types: list[str] | None = None


class PathGenerateRequest(BaseModel):
    student_id: int = Field(gt=0)
    goal: str | None = Field(default=None, max_length=300)


class PathStepUpdate(BaseModel):
    completed: bool


class TutorRequest(BaseModel):
    student_id: int = Field(gt=0)
    question: str = Field(min_length=1, max_length=2000)
    resource_id: int | None = None


class RecordRequest(BaseModel):
    student_id: int = Field(gt=0)
    resource_id: int | None = None
    action: str = Field(default="view", max_length=20)
    score: float | None = None
    duration_sec: int = Field(default=0, ge=0)
    detail: str = Field(default="", max_length=2000)


class EvaluateRequest(BaseModel):
    student_id: int = Field(gt=0)
