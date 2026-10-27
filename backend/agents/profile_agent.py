"""画像抽取智能体：从自然语言对话中抽取 / 更新画像维度。

它不是「表单校验」，而是要做三件事：
1. 识别这句话里有哪些画像线索；
2. 只更新有证据的维度，避免瞎猜；
3. 主动追问信息最少的维度，把对话继续下去。
"""
from __future__ import annotations

import re
import time
from typing import Any

from agents.base import AgentContext
from llm import llm_service
from store import DEFAULT_VALUES, DIMENSIONS, VALID_DIMENSIONS

PROFILE_SCHEMA = {
    "type": "object",
    "properties": {
        "reply": {"type": "string", "description": "给学生的自然语言回复，2-4 句"},
        "dimensions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "dimension": {"type": "string", "enum": [name for name, _ in DIMENSIONS]},
                    "value": {"type": "string"},
                    "confidence": {"type": "number"},
                },
                "required": ["dimension", "value", "confidence"],
                "additionalProperties": False,
            },
        },
        "follow_up": {"type": "string", "description": "一个能继续补全画像的问题"},
    },
    "required": ["reply", "dimensions", "follow_up"],
    "additionalProperties": False,
}

DIMENSION_KEYWORDS = {
    "知识基础": ["学过", "基础", "入门", "熟悉", "掌握", "课程", "python", "java", "数据库", "算法", "前端", "后端"],
    "认知风格": ["视频", "图", "框架", "例子", "文档", "动手", "听讲", "先看", "细节", "整体"],
    "学习目标": ["目标", "实习", "考试", "考研", "项目", "比赛", "找工作", "完成", "想做"],
    "易错点偏好": ["容易错", "易错", "粗心", "混淆", "记不住", "搞混", "难点", "不会"],
    "学习节奏": ["每天", "每周", "小时", "分钟", "晚上", "周末", "节奏", "时间", "专注"],
    "兴趣方向": ["ai", "人工智能", "大模型", "前端", "后端", "可视化", "机器学习"],
    "实践偏好": ["代码", "例子", "实战", "项目", "文档", "视频", "图解", "动手"],
}

QUESTION_BANK = {
    "知识基础": "你之前学过哪些相关课程或技术？哪些地方学得比较扎实？",
    "认知风格": "遇到一个新概念时，你更希望先看整体框架、看一个例子，还是先读完整文档？",
    "学习目标": "这学期你最想完成的一个具体成果是什么？",
    "易错点偏好": "有哪些概念你总觉得「好像懂了，但一做题就错」？",
    "学习节奏": "你每周大概能投入多少小时？更习惯短时间多次，还是一次学很久？",
    "兴趣方向": "除了课程要求，你最近主动了解过哪些技术或方向？",
    "实践偏好": "如果只能选一种材料，你更想要可运行的代码、图解，还是系统讲解文档？",
}


def _snippet(message: str, limit: int = 90) -> str:
    clean = " ".join(message.strip().split())
    return clean[:limit] + ("…" if len(clean) > limit else "")


def _infer_updates(message: str, ctx: AgentContext) -> list[dict]:
    lower = message.lower()
    # 把长句拆成短句，只取和该维度最相关的那一小句，避免把整段话塞进每个维度
    clauses = [c.strip() for c in re.split(r"[。！？；，,\n]", message) if c.strip()]
    updates: list[dict] = []
    for dimension, keywords in DIMENSION_KEYWORDS.items():
        hits = [word for word in keywords if word in lower]
        if not hits:
            continue
        relevant = max(
            clauses,
            key=lambda clause: sum(1 for word in keywords if word in clause.lower()),
            default=message,
        )
        snippet = _snippet(relevant)
        if not snippet:
            continue
        current = ctx.profile.get(dimension, DEFAULT_VALUES[dimension])
        if current.startswith("待补充") or not current:
            value = snippet
        elif snippet in current:
            value = current
        else:
            value = f"{current}；补充：{snippet}"
        updates.append(
            {
                "dimension": dimension,
                "value": value[:1000],
                # 关键词命中只是弱证据，置信度给保守值
                "confidence": round(min(0.9, 0.45 + 0.12 * len(hits)), 2),
            }
        )
        if len(updates) >= 4:
            break

    # 首轮对话补全：保证画像至少 6 个维度有可展示的值
    filled = sum(
        1
        for value in ctx.profile.values()
        if value and not value.startswith("待补充")
    )
    if filled + len(updates) < 6:
        inferred = {
            "知识基础": f"{ctx.major}专业本科阶段，具备课程基础（待对话细化）",
            "认知风格": "倾向「先框架、再示例」，具体偏好待观察",
            "学习目标": ctx.goal or "完成当前课程项目",
            "易错点偏好": "待观察：将通过练习与测评记录持续修正",
            "学习节奏": "每周约 6-8 小时（待确认）",
            "兴趣方向": f"{ctx.major}相关方向（待细化）",
            "实践偏好": "偏好可运行示例与图解",
        }
        existing_dims = {item["dimension"] for item in updates}
        for dimension, value in inferred.items():
            if len(updates) + sum(1 for v in ctx.profile.values() if v and not v.startswith("待补充")) >= 7:
                break
            if dimension in existing_dims:
                continue
            if ctx.profile.get(dimension, "").startswith("待补充"):
                updates.append(
                    {"dimension": dimension, "value": value, "confidence": 0.4}
                )
    return updates


class ProfileAgent:
    name = "profile_extractor"
    role = "画像抽取智能体"
    system_prompt = (
        "你是一个学习画像抽取智能体。你的任务是从学生的自然语言中识别稳定的学习特征，"
        "更新 7 个维度：知识基础、认知风格、学习目标、易错点偏好、学习节奏、兴趣方向、实践偏好。\n"
        "规则：\n"
        "1. 只根据学生提供的信息更新，不要编造具体事实；证据不足时 confidence 给 0.3-0.5。\n"
        "2. 每条 value 要具体、可行动，不要只写「较好」「一般」。\n"
        "3. reply 先复述你更新了什么，再给一句自然的反馈；follow_up 只问一个最需要补全的问题。\n"
        "4. 不要收集身份证号、住址等敏感个人信息。\n"
        "5. 只输出 JSON。"
    )

    def run(
        self,
        ctx: AgentContext,
        message: str,
        history: list[dict],
    ) -> dict:
        started = time.perf_counter()
        prompt = self._build_prompt(ctx, message, history)
        result = llm_service.complete_json(
            system=self.system_prompt,
            prompt=prompt,
            schema=PROFILE_SCHEMA,
            mock_factory=lambda: self._mock(ctx, message),
            agent=self.name,
        )
        data: dict[str, Any] = result.data
        # 过滤未知维度，避免脏数据
        data["dimensions"] = [
            item for item in data.get("dimensions", [])
            if item.get("dimension") in VALID_DIMENSIONS
        ]
        data["provider"] = result.provider
        data["model"] = result.model
        data["duration_ms"] = int((time.perf_counter() - started) * 1000)
        data["note"] = result.note
        return data

    def _build_prompt(self, ctx: AgentContext, message: str, history: list[dict]) -> str:
        history_text = "\n".join(
            f"{item['role']}：{item['content']}" for item in history[-8:]
        ) or "（暂无历史对话）"
        return (
            f"学生：{ctx.student_name}，专业：{ctx.major}，目标：{ctx.goal}\n"
            f"当前画像：\n{ctx.profile_text()}\n\n"
            f"最近对话：\n{history_text}\n\n"
            f"学生这次说：{message}\n\n"
            "请抽取可更新的维度，并给出回复与一个追问。"
        )

    def _mock(self, ctx: AgentContext, message: str) -> dict:
        updates = _infer_updates(message, ctx)
        if updates:
            names = "、".join(f"「{item['dimension']}」" for item in updates)
            reply = (
                f"收到。我从这句话里更新了 {names}。"
                "这些信息会作为后续资源生成和路径规划的依据。"
            )
        else:
            reply = "这句话里暂时没有新的画像线索，我先把当前画像保持住，不做过拟合。"

        # 追问置信度最低、或仍是「待补充」的维度
        def rough_confidence(value: str) -> float:
            if not value or value.startswith("待补充"):
                return 0.1
            if "待" in value:
                return 0.4
            return 0.7

        candidates = [
            (name, rough_confidence(ctx.profile.get(name, "")))
            for name, _ in DIMENSIONS
        ]
        pending = [
            name for name, _ in DIMENSIONS
            if ctx.profile.get(name, "").startswith("待补充")
        ]
        if pending:
            follow_up = QUESTION_BANK[pending[0]]
        else:
            # 取置信度最低的维度；同分时按消息长度轮换，避免每次都问同一题
            lowest = min(conf for _, conf in candidates) if candidates else 0
            choices = [name for name, conf in candidates if conf == lowest]
            follow_up = QUESTION_BANK[choices[len(message) % len(choices)]]

        return {"reply": reply, "dimensions": updates, "follow_up": follow_up}
