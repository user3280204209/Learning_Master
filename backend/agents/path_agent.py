"""学习路径规划智能体：把已有资源组织成有先后依赖的步骤。"""
from __future__ import annotations

import time

from agents.base import AgentContext
from llm import llm_service

PATH_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "rationale": {"type": "string", "description": "为什么这样排序，结合画像解释"},
        "steps": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "no": {"type": "integer"},
                    "title": {"type": "string"},
                    "objective": {"type": "string"},
                    "resource_ids": {"type": "array", "items": {"type": "integer"}},
                    "estimated_minutes": {"type": "integer"},
                    "checkpoint": {"type": "string", "description": "完成本步的可检查标准"},
                },
                "required": [
                    "no", "title", "objective", "resource_ids", "estimated_minutes", "checkpoint",
                ],
                "additionalProperties": False,
            },
        },
    },
    "required": ["title", "rationale", "steps"],
    "additionalProperties": False,
}


class PathAgent:
    name = "path_planner"
    role = "学习路径规划智能体"
    system_prompt = (
        "你是学习路径规划智能体。根据学生画像与已有资源，设计 4-6 个有依赖关系的步骤。"
        "每一步必须有明确目标、关联资源、预计时长和可检查的完成标准。"
        "资源只能用给定的 resource_id。只输出 JSON。"
    )

    def run(self, ctx: AgentContext, goal: str | None = None) -> dict:
        started = time.perf_counter()
        resources_text = "\n".join(
            f"- id={r['id']} type={r['type']} title={r['title']} summary={r.get('summary', '')}"
            for r in ctx.resources
        )
        prompt = (
            f"学生：{ctx.student_name}，专业：{ctx.major}\n"
            f"总目标：{goal or ctx.goal}\n画像：\n{ctx.profile_text()}\n\n"
            f"当前可用资源：\n{resources_text}\n\n"
            "请规划学习路径。顺序要符合先框架、再理解、再练习、最后评估的认知规律。"
        )
        result = llm_service.complete_json(
            system=self.system_prompt,
            prompt=prompt,
            schema=PATH_SCHEMA,
            mock_factory=lambda: self._mock(ctx, goal),
            agent=self.name,
        )
        data = result.data
        data["provider"] = result.provider
        data["model"] = result.model
        data["duration_ms"] = int((time.perf_counter() - started) * 1000)
        return data

    def _mock(self, ctx: AgentContext, goal: str | None) -> dict:
        by_type: dict[str, list[dict]] = {}
        for resource in ctx.resources:
            by_type.setdefault(resource["type"], []).append(resource)

        def ids(*types: str) -> list[int]:
            return [r["id"] for kind in types for r in by_type.get(kind, [])]

        rhythm = ctx.profile.get("学习节奏", "每周 6-8 小时")
        weak = ctx.profile.get("易错点偏好", "概念边界")
        steps = [
            {
                "no": 1,
                "title": "建立全局地图",
                "objective": f"先弄清「{ctx.topic or '当前主题'}」的知识结构与学习目标，不急着记细节。",
                "resource_ids": ids("mindmap", "document"),
                "estimated_minutes": 30,
                "checkpoint": "能合上资料，用 5 句话复述整体框架。",
            },
            {
                "no": 2,
                "title": "用多模态材料建立直觉",
                "objective": "通过微课与拓展阅读，把抽象概念和具体场景连起来。",
                "resource_ids": ids("video", "reading"),
                "estimated_minutes": 35,
                "checkpoint": "能举出一个与专业背景相关的例子。",
            },
            {
                "no": 3,
                "title": "跑通最小实操",
                "objective": "把理解转成可运行的结果，并做一次变量控制。",
                "resource_ids": ids("code"),
                "estimated_minutes": 45,
                "checkpoint": "代码能运行，且能解释改一个参数后结果为何变化。",
            },
            {
                "no": 4,
                "title": "针对易错点刻意练习",
                "objective": f"用分层练习暴露并修正「{weak}」。",
                "resource_ids": ids("exercise"),
                "estimated_minutes": 30,
                "checkpoint": "完成练习并记录每道题的犹豫点。",
            },
            {
                "no": 5,
                "title": "复盘与下一轮",
                "objective": "根据练习与学习记录更新画像，决定下一步加强什么。",
                "resource_ids": [],
                "estimated_minutes": 15,
                "checkpoint": "产出一份「已掌握 / 仍模糊 / 下一步」三栏清单。",
            },
        ]
        steps = [step for step in steps if step["resource_ids"] or step["no"] == 5]
        for index, step in enumerate(steps, start=1):
            step["no"] = index
        return {
            "title": f"{ctx.topic or '个性化学习'} · 学习路径",
            "rationale": (
                f"你的学习节奏是「{rhythm}」，所以路径按 30-45 分钟一个可完成单元切分；"
                f"你的易错点是「{weak}」，因此把练习放在理解之后、评估之前；"
                "最后一步回到画像，形成「学习—评估—调整」的闭环。"
            ),
            "steps": steps,
        }
