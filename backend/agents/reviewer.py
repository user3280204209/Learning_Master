"""质量审核智能体。

不是所有 Agent 都要调用大模型：能用规则稳定判断的事，就别花 token。
这里按「是否贴合画像、内容是否够用、结构是否完整」给每个产物打分。
"""
from __future__ import annotations

from agents.base import AgentContext, AgentOutput


class ReviewerAgent:
    name = "reviewer"
    role = "质量审核智能体"

    def review(self, output: AgentOutput, ctx: AgentContext) -> tuple[float, str]:
        score = 55.0
        notes: list[str] = []

        if len(output.content) >= 500:
            score += 10
            notes.append("内容长度充足")
        else:
            notes.append("内容偏短")

        if ctx.topic and ctx.topic in output.content:
            score += 10
            notes.append("覆盖主题")
        else:
            notes.append("主题词覆盖不足")

        if ctx.student_name in output.content or "画像" in output.content:
            score += 8
            notes.append("体现学生画像")

        if output.meta:
            score += 5
        if output.type in ("exercise", "code", "video") and output.meta:
            score += 5
            notes.append("包含可交互/可运行结构")

        if output.provider == "claude":
            score += 7
            notes.append("由真实模型生成")
        elif output.provider == "mock-fallback":
            notes.append("真实模型失败后降级模板")

        if output.file_path:
            score += 5
            notes.append("附带生成文件")

        score = min(score, 98.0)
        return round(score, 1), "；".join(notes)
