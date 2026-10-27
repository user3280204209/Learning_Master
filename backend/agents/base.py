"""Agent 基类与共享上下文。

统一约束：
- 每个 Agent 有名字、角色、系统提示词、输出 JSON Schema。
- 生成走 llm_service.complete_json：真实模型失败会降级 mock，不会拖垮整条流水线。
- 输出统一转成 AgentOutput，编排器负责落库和追踪。
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

from llm import LLMResult, llm_service


@dataclass
class AgentContext:
    """共享上下文（黑板）：所有 Agent 从这里读画像，把自己的产物写回结果列表。"""

    student: dict
    profile: dict[str, str]
    topic: str = ""
    requirements: str = ""
    task_id: str = ""
    plan: dict = field(default_factory=dict)
    resources: list[dict] = field(default_factory=list)
    records: list[dict] = field(default_factory=list)

    @property
    def student_name(self) -> str:
        return str(self.student.get("name", "同学"))

    @property
    def major(self) -> str:
        return str(self.student.get("major", "未填写专业"))

    @property
    def goal(self) -> str:
        return str(self.student.get("goal", "未填写目标"))

    def profile_text(self) -> str:
        return "\n".join(f"- {name}：{value}" for name, value in self.profile.items())


@dataclass
class AgentOutput:
    agent: str
    role: str
    type: str | None
    title: str
    summary: str
    content: str
    meta: dict = field(default_factory=dict)
    file_path: str | None = None
    provider: str = "mock"
    model: str = "template-engine"
    duration_ms: int = 0
    quality_score: float = 0
    review_note: str = ""

    def trace_input(self) -> str:
        return f"topic={self.meta.get('topic', '')}"

    def trace_output(self) -> str:
        return f"{self.title}｜{self.summary[:80]}"


class BaseAgent:
    name = "base"
    role = "基础智能体"
    resource_type: str | None = None
    system_prompt = "你是一个学习资源生成智能体。"
    schema: dict = {
        "type": "object",
        "properties": {},
        "required": [],
        "additionalProperties": False,
    }

    @property
    def display_name(self) -> str:
        return f"{self.role}（{self.name}）"

    def build_prompt(self, ctx: AgentContext) -> str:
        return (
            f"学生：{ctx.student_name}，专业：{ctx.major}，学习目标：{ctx.goal}\n"
            f"学生画像：\n{ctx.profile_text()}\n\n"
            f"本次主题：{ctx.topic}\n"
            f"额外要求：{ctx.requirements or '无'}\n\n"
            "请严格按 JSON Schema 输出，内容使用中文，必须贴合该学生的画像，"
            "不要写空泛的套话。"
        )

    def mock(self, ctx: AgentContext) -> dict:
        raise NotImplementedError

    def to_output(self, data: dict, ctx: AgentContext, result: LLMResult) -> AgentOutput:
        raise NotImplementedError

    def validate(self, data: dict) -> None:
        if not isinstance(data, dict):
            raise ValueError("Agent 输出不是 JSON 对象")
        missing = [key for key in self.schema.get("required", []) if key not in data]
        if missing:
            raise ValueError(f"Agent 输出缺少字段：{missing}")

    def run(self, ctx: AgentContext) -> AgentOutput:
        started = time.perf_counter()
        result = llm_service.complete_json(
            system=self.system_prompt,
            prompt=self.build_prompt(ctx),
            schema=self.schema,
            mock_factory=lambda: self.mock(ctx),
            agent=self.name,
        )
        self.validate(result.data)
        output = self.to_output(result.data, ctx, result)
        output.agent = self.name
        output.role = self.role
        output.type = self.resource_type
        output.provider = result.provider
        output.model = result.model
        output.duration_ms = int((time.perf_counter() - started) * 1000)
        if result.note:
            output.review_note = f"LLM 降级：{result.note}"
        return output
