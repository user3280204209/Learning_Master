"""智能辅导智能体：即时答疑，并给出可执行的下一步。"""
from __future__ import annotations

import time

from agents.base import AgentContext
from llm import llm_service

TUTOR_SCHEMA = {
    "type": "object",
    "properties": {
        "answer": {"type": "string", "description": "Markdown 形式的详细回答"},
        "key_points": {"type": "array", "items": {"type": "string"}},
        "analogy": {"type": "string"},
        "diagram": {"type": "string", "description": "可选：Mermaid 图，没有就空字符串"},
        "next_actions": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["answer", "key_points", "analogy", "diagram", "next_actions"],
    "additionalProperties": False,
}


class TutorAgent:
    name = "tutor"
    role = "智能辅导智能体"
    system_prompt = (
        "你是学生的即时辅导老师。回答要准确、分层：先用一句话回答，再解释原因，"
        "再给一个贴近学生专业的类比，最后给可执行的下一步。"
        "不确定的内容要明确说「需要查证」，不要编造。只输出 JSON。"
    )

    def run(self, ctx: AgentContext, question: str, resource: dict | None = None) -> dict:
        started = time.perf_counter()
        resource_text = (
            f"关联资源：{resource['title']}（{resource['type']}）\n"
            f"资源摘要：{resource.get('summary', '')}\n"
            if resource
            else ""
        )
        prompt = (
            f"学生：{ctx.student_name}，专业：{ctx.major}\n"
            f"画像：\n{ctx.profile_text()}\n\n"
            f"{resource_text}"
            f"学生的问题：{question}\n\n"
            "请用中文回答。先给结论，再拆解，再类比，最后给 2-3 个下一步动作。"
        )
        result = llm_service.complete_json(
            system=self.system_prompt,
            prompt=prompt,
            schema=TUTOR_SCHEMA,
            mock_factory=lambda: self._mock(ctx, question),
            agent=self.name,
        )
        data = result.data
        data["provider"] = result.provider
        data["model"] = result.model
        data["duration_ms"] = int((time.perf_counter() - started) * 1000)
        return data

    def _mock(self, ctx: AgentContext, question: str) -> dict:
        weak = ctx.profile.get("易错点偏好", "概念边界")
        style = ctx.profile.get("认知风格", "先框架后细节")
        if "区别" in question or "不同" in question:
            core = "这类问题通常卡在「边界」而不是「定义」：先分别写出两者的输入、输出和适用场景，再找交集。"
            analogy = "像区分两种工具箱：不要背工具名字，先看它们各自能拧什么螺丝。"
        elif "为什么" in question:
            core = "先找「不这样做会怎样」的反例，再从反例倒推机制；只背结论很容易在换场景后失效。"
            analogy = "像理解刹车：不是记住踏板位置，而是知道它为什么能让车慢下来。"
        elif "怎么" in question or "如何" in question:
            core = "把任务拆成「最小可运行版本 → 再加一个变量 → 再处理边界」三步，先跑通再加复杂度。"
            analogy = "像学做菜：先炒熟一个鸡蛋，再考虑摆盘和调味。"
        else:
            core = "先确认问题属于「概念不清、步骤不会、还是环境报错」，三类问题的解法完全不同。"
            analogy = "像看病先分诊：头痛和脚痛不该用同一张处方。"

        answer = f"""### 一句话回答

{core}

### 拆开看

1. **先定位问题类型**：你是在问「它是什么」「为什么这样」还是「我该怎么做」？
2. **把已知和未知分开写**：左边写确定的事实，右边写你的猜测。
3. **用一个小例子验证**：不要一次改很多变量。

### 结合你的画像

你提到的易错点是 **{weak}**，认知风格偏 **{style}**。建议你这次不要直接看完整答案，
先用 2 分钟写下自己的解释，再对照下面的要点修正。

### 类比

{analogy}

### 需要警惕

如果问题涉及具体版本、API 参数或公司内部实现，仅凭记忆回答可能过时；
这类内容应以官方文档或实际运行结果为准。
"""
        diagram = (
            "flowchart LR\n"
            "  A[问题] --> B{属于哪类?}\n"
            "  B -->|概念| C[对比+反例]\n"
            "  B -->|步骤| D[拆最小步骤]\n"
            "  B -->|报错| E[读错误信息]\n"
            "  C --> F[用自己的话复述]\n"
            "  D --> F\n"
            "  E --> F\n"
        )
        return {
            "answer": answer,
            "key_points": [
                "先分类问题，再选解法",
                "用反例和对比建立概念边界",
                "最小示例 + 单变量修改",
                f"重点检查你的易错点：{weak[:50]}",
            ],
            "analogy": analogy,
            "diagram": diagram,
            "next_actions": [
                "用 3 句话写出你现在的理解",
                "找同批次资源里的一个最小示例跑一遍",
                "把仍然模糊的点发回来，我帮你拆解",
            ],
        }
