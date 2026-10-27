"""教学规划智能体：先定「学什么、按什么顺序学」，再让 6 个生成 Agent 并行干活。

这是多智能体系统的第一层分工：Planner 做全局决策，Generator 做局部产出。
"""
from __future__ import annotations

import time

from agents.base import AgentContext
from llm import llm_service
from store import RESOURCE_TYPES

PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "level": {"type": "string", "description": "对当前水平的判断"},
        "focus": {"type": "string", "description": "本次资源包的核心聚焦点"},
        "resource_plan": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "type": {"type": "string", "enum": list(RESOURCE_TYPES)},
                    "title": {"type": "string"},
                    "focus": {"type": "string"},
                },
                "required": ["type", "title", "focus"],
                "additionalProperties": False,
            },
        },
        "sequence": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["level", "focus", "resource_plan", "sequence"],
    "additionalProperties": False,
}


class PlannerAgent:
    name = "planner"
    role = "教学规划智能体"
    system_prompt = (
        "你是一个教学规划智能体，负责为一个学生设计一组互补的学习资源。"
        "你需要根据学生画像与主题，决定每类资源的具体切入点和标题。"
        "资源类型只能是：document（讲解文档）、mindmap（思维导图）、exercise（练习）、"
        "reading（拓展阅读）、code（代码实操）、video（微课脚本）。只输出 JSON。"
    )

    def run(self, ctx: AgentContext, types: list[str]) -> dict:
        started = time.perf_counter()
        prompt = (
            f"学生：{ctx.student_name}，专业：{ctx.major}，目标：{ctx.goal}\n"
            f"画像：\n{ctx.profile_text()}\n\n"
            f"学习主题：{ctx.topic}\n额外要求：{ctx.requirements or '无'}\n"
            f"本次需要生成的资源类型：{', '.join(types)}\n\n"
            "请为每种类型给出一个具体标题与聚焦点，并给出推荐学习顺序。"
        )
        result = llm_service.complete_json(
            system=self.system_prompt,
            prompt=prompt,
            schema=PLAN_SCHEMA,
            mock_factory=lambda: self._mock(ctx, types),
            agent=self.name,
        )
        data = result.data
        # 只保留本次请求的类型，并补齐缺失项，保证数量
        generated = {
            item["type"]: item
            for item in data.get("resource_plan", [])
            if item.get("type") in types
        }
        fallback = self._mock(ctx, types)["resource_plan"]
        data["resource_plan"] = [
            generated.get(item["type"], item) for item in fallback if item["type"] in types
        ]
        data["sequence"] = [
            item["type"] for item in data["resource_plan"]
        ]
        data["provider"] = result.provider
        data["model"] = result.model
        data["duration_ms"] = int((time.perf_counter() - started) * 1000)
        return data

    def _mock(self, ctx: AgentContext, types: list[str]) -> dict:
        knowledge = ctx.profile.get("知识基础", "")
        if any(word in knowledge for word in ("入门", "零", "刚", "初学")):
            level = "入门阶段：需要先建立直觉与最小可运行经验"
        elif any(word in knowledge for word in ("扎实", "熟悉", "掌握")):
            level = "进阶阶段：可以压缩概念讲解，增加综合任务"
        else:
            level = "过渡阶段：概念与动手需要交替推进"

        style = ctx.profile.get("认知风格", "先框架后细节")
        focus = f"围绕「{ctx.topic}」建立可迁移的理解框架，并照顾学生的{style}偏好"
        titles = {
            "document": f"{ctx.topic} · 从直觉到系统理解",
            "mindmap": f"{ctx.topic} · 一张图看懂知识结构",
            "exercise": f"{ctx.topic} · 分层练习与自检",
            "reading": f"{ctx.topic} · 拓展阅读与资料地图",
            "code": f"{ctx.topic} · 可运行的最小实操",
            "video": f"{ctx.topic} · 5 分钟微课",
        }
        focuses = {
            "document": "先给整体框架，再用一个贴近专业背景的例子贯穿",
            "mindmap": "提炼 4 个一级分支，标出概念之间的依赖关系",
            "exercise": "从概念辨析到迁移应用，覆盖学生的易错点",
            "reading": "区分入门、进阶、项目三类材料，控制阅读负担",
            "code": "给出一段可直接运行、可修改的代码，并配套任务",
            "video": "用 5 个镜头讲清一个核心问题，控制单镜时长",
        }
        plan = [
            {"type": kind, "title": titles[kind], "focus": focuses[kind]}
            for kind in types
        ]
        sequence = [kind for kind in ("mindmap", "document", "video", "code", "exercise", "reading") if kind in types]
        return {"level": level, "focus": focus, "resource_plan": plan, "sequence": sequence}
