"""学习效果评估智能体：把行为数据变成可解释的评估，并回写画像。

这是需求 5 的闭环落点：
学习行为 → 评估 → 更新画像 → 下一轮路径/资源调整。
"""
from __future__ import annotations

import time

from agents.base import AgentContext
from llm import llm_service

ASSESS_SCHEMA = {
    "type": "object",
    "properties": {
        "overall_score": {"type": "number"},
        "dimensions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "dimension": {"type": "string"},
                    "score": {"type": "number"},
                    "comment": {"type": "string"},
                },
                "required": ["dimension", "score", "comment"],
                "additionalProperties": False,
            },
        },
        "strengths": {"type": "array", "items": {"type": "string"}},
        "weaknesses": {"type": "array", "items": {"type": "string"}},
        "suggestions": {"type": "array", "items": {"type": "string"}},
        "summary": {"type": "string"},
        "profile_updates": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "dimension": {"type": "string"},
                    "value": {"type": "string"},
                    "confidence": {"type": "number"},
                },
                "required": ["dimension", "value", "confidence"],
                "additionalProperties": False,
            },
        },
    },
    "required": [
        "overall_score", "dimensions", "strengths", "weaknesses",
        "suggestions", "summary", "profile_updates",
    ],
    "additionalProperties": False,
}


def _clamp(value: float, low: float = 40, high: float = 95) -> float:
    return round(max(low, min(high, value)), 1)


class AssessorAgent:
    name = "assessor"
    role = "学习评估智能体"
    system_prompt = (
        "你是学习效果评估智能体。根据学生的学习行为记录（浏览、答题、用时、得分）"
        "给出 7 个维度的 0-100 分评估，说明优势、薄弱点与具体建议。"
        "评估必须基于数据，不要编造。只能输出 JSON。"
    )

    def run(self, ctx: AgentContext) -> dict:
        started = time.perf_counter()
        records_text = "\n".join(
            f"- {r.get('action')} | resource={r.get('resource_title') or '-'} | "
            f"score={r.get('score')} | {r.get('duration_sec', 0)}s | {r.get('created_at')}"
            for r in ctx.records[:50]
        ) or "（暂无学习行为记录）"
        prompt = (
            f"学生：{ctx.student_name}，专业：{ctx.major}\n"
            f"画像：\n{ctx.profile_text()}\n\n"
            f"学习行为记录：\n{records_text}\n\n"
            "请输出评估结果，并给出 2-3 条可以直接执行的建议。"
            "profile_updates 用来把评估结论写回画像，值要具体。"
        )
        result = llm_service.complete_json(
            system=self.system_prompt,
            prompt=prompt,
            schema=ASSESS_SCHEMA,
            mock_factory=lambda: self._mock(ctx),
            agent=self.name,
        )
        data = result.data
        data["provider"] = result.provider
        data["model"] = result.model
        data["duration_ms"] = int((time.perf_counter() - started) * 1000)
        return data

    def _mock(self, ctx: AgentContext) -> dict:
        records = ctx.records
        actions = len(records)
        answers = [r for r in records if r.get("action") == "answer" and r.get("score") is not None]
        views = [r for r in records if r.get("action") == "view"]
        total_seconds = sum(int(r.get("duration_sec") or 0) for r in records)
        minutes = total_seconds / 60
        avg_score = (
            sum(float(r["score"]) for r in answers) / len(answers) if answers else 0.0
        )
        distinct_types = len({r.get("resource_type") for r in records if r.get("resource_type")})
        practice_count = sum(
            1 for r in records if r.get("resource_type") in ("code", "exercise")
        )

        scores = {
            "知识基础": _clamp(58 + min(18, actions * 2) + avg_score * 0.12),
            "认知风格": _clamp(66 + min(10, len(views) * 2)),
            "学习目标": _clamp(70 + min(10, actions)),
            "易错点偏好": _clamp(55 + min(22, len(answers) * 6) + avg_score * 0.1),
            "学习节奏": _clamp(60 + min(20, minutes / 5)),
            "兴趣方向": _clamp(68 + min(12, distinct_types * 2)),
            "实践偏好": _clamp(62 + min(18, practice_count * 5)),
        }
        comments = {
            "知识基础": f"已产生 {actions} 次学习行为，答题均分 {avg_score:.0f} 分。",
            "认知风格": "已接触多种资源形态，偏好仍在形成中。",
            "学习目标": "目标较明确，但还需要更多可交付成果来验证。",
            "易错点偏好": f"已积累 {len(answers)} 次答题样本，易错点开始显性化。",
            "学习节奏": f"累计学习约 {minutes:.0f} 分钟，样本仍偏少，节奏稳定性待观察。",
            "兴趣方向": f"已接触 {distinct_types} 类资源，兴趣分布正在形成。",
            "实践偏好": f"实操类行为 {practice_count} 次，动手比例还有提升空间。",
        }
        dimension_list = [
            {"dimension": name, "score": score, "comment": comments[name]}
            for name, score in scores.items()
        ]
        overall = round(sum(scores.values()) / len(scores), 1)

        ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
        strengths = [
            f"{name}（{score:.0f} 分）：{comments[name]}" for name, score in ranked[:2]
        ]
        weaknesses = [
            f"{name}（{score:.0f} 分）：{comments[name]}" for name, score in ranked[-2:]
        ]
        suggestions = [
            f"优先补「{ranked[-1][0]}」：下一次学习至少安排 25 分钟做对应的刻意练习。",
            "每完成一份资源，立刻记录 1 条「我仍然模糊的点」，用于下一轮画像更新。",
            "把「看资源」和「做输出」的比例控制在 1:1，例如看 20 分钟就写 20 分钟笔记或代码。",
        ]
        summary = (
            f"本次评估基于 {actions} 次学习行为、约 {minutes:.0f} 分钟投入"
            f"和 {len(answers)} 次答题（均分 {avg_score:.0f}）。"
            f"整体得分 {overall}，强项是{ranked[0][0]}，优先改进{ranked[-1][0]}。"
        )
        def append(existing: str, addition: str) -> str:
            """评估结论追加到画像，而不是覆盖掉之前的对话信息。"""
            if not existing or existing.startswith("待补充"):
                return addition
            return f"{existing}；{addition}"

        profile_updates = [
            {
                "dimension": "知识基础",
                "value": append(
                    ctx.profile.get("知识基础", ""),
                    f"近期评估掌握度约 {scores['知识基础']:.0f} 分，"
                    f"答题均分 {avg_score:.0f}，累计 {actions} 次学习行为",
                ),
                "confidence": 0.7,
            },
            {
                "dimension": "易错点偏好",
                "value": append(
                    ctx.profile.get("易错点偏好", ""),
                    f"近期练习样本 {len(answers)} 条、均分 {avg_score:.0f}，"
                    "下一轮重点观察低分题对应的概念边界",
                ),
                "confidence": 0.65,
            },
            {
                "dimension": "学习节奏",
                "value": append(
                    ctx.profile.get("学习节奏", ""),
                    f"累计投入约 {minutes:.0f} 分钟，建议保持每次 25-45 分钟的可完成单元",
                ),
                "confidence": 0.6,
            },
        ]
        return {
            "overall_score": overall,
            "dimensions": dimension_list,
            "strengths": strengths,
            "weaknesses": weaknesses,
            "suggestions": suggestions,
            "summary": summary,
            "profile_updates": profile_updates,
        }
