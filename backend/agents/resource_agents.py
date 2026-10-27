"""6 个资源生成智能体：文档 / 导图 / 练习 / 阅读 / 代码 / 微课。

它们共享同一个上下文（画像 + 主题 + 规划），但各自有独立的角色提示词和输出结构。
这是「多智能体」最直观的体现：不是一个大 prompt 写六件事，而是六个角色各自负责。
"""
from __future__ import annotations

import html
import json
from pathlib import Path

from agents.base import AgentContext, AgentOutput, BaseAgent
from config import GENERATED_DIR


def _profile(ctx: AgentContext, key: str, default: str = "未填写") -> str:
    return ctx.profile.get(key) or default


def _header(ctx: AgentContext, kind: str) -> str:
    return (
        f"> 为 **{ctx.student_name}**（{ctx.major}）定制 · {kind}\n"
        f"> 学习目标：{ctx.goal}\n"
        f"> 适配画像：知识基础「{_profile(ctx, '知识基础')}」；"
        f"认知风格「{_profile(ctx, '认知风格')}」\n"
    )


class ResourceAgent(BaseAgent):
    """所有资源 Agent 的公共输出转换。"""

    def extra_meta(self, data: dict, ctx: AgentContext) -> dict:
        return {}

    def to_output(self, data: dict, ctx: AgentContext, result) -> AgentOutput:
        return AgentOutput(
            agent=self.name,
            role=self.role,
            type=self.resource_type,
            title=str(data.get("title") or ctx.topic),
            summary=str(data.get("summary") or ""),
            content=str(data.get("content") or ""),
            meta={
                "topic": ctx.topic,
                "estimated_minutes": int(data.get("estimated_minutes") or 15),
                **self.extra_meta(data, ctx),
            },
        )


# ---------------------------------------------------------------- 讲解文档
class DocumentAgent(ResourceAgent):
    name = "document_agent"
    role = "讲解文档智能体"
    resource_type = "document"
    system_prompt = (
        "你是专业课程讲解文档智能体。写一份给学生本人看的中文讲解，"
        "必须结合学生的知识基础、认知风格与易错点，先框架后细节，"
        "包含类比、步骤、检查清单。用 Markdown，标题层级清晰。只输出 JSON。"
    )
    schema = {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "summary": {"type": "string"},
            "content": {"type": "string", "description": "Markdown 正文"},
            "keywords": {"type": "array", "items": {"type": "string"}},
            "estimated_minutes": {"type": "integer"},
        },
        "required": ["title", "summary", "content", "keywords", "estimated_minutes"],
        "additionalProperties": False,
    }

    def extra_meta(self, data: dict, ctx: AgentContext) -> dict:
        return {"keywords": data.get("keywords", [])}

    def mock(self, ctx: AgentContext) -> dict:
        weak = _profile(ctx, "易错点偏好", "概念边界容易混淆")
        style = _profile(ctx, "认知风格", "先框架后细节")
        content = f"""# {ctx.topic}：从直觉到系统理解

{_header(ctx, '专业讲解文档')}
## 0. 先定位：你现在在哪

你的知识基础是：**{_profile(ctx, '知识基础')}**。所以这份材料不会从定义堆砌开始，
而是先用一个你能在脑中跑起来的场景建立直觉，再回到概念和结构。

## 1. 用一个问题建立框架

学习 **{ctx.topic}** 之前，先回答三个问题：

1. 它解决的是什么问题？如果没有它，会遇到什么麻烦？
2. 它的输入、输出分别是什么？中间发生了什么？
3. 它在整个知识体系里，站在哪一层？

> 记忆技巧：不要先背定义，先找到「它为什么存在」。

## 2. 核心概念的三层理解

| 层次 | 你要能回答 | 自检方式 |
|---|---|---|
| 直觉层 | 用一句话向非专业同学解释 | 不看资料讲 30 秒 |
| 结构层 | 画出概念之间的关系 | 独立画出导图 |
| 应用层 | 在一个小任务里用出来 | 完成文末练习 |

## 3. 结合你的易错点

你提到容易出问题的地方是：**{weak}**。针对这一点，建议用「对比表 + 反例」学习：

- 每学一个概念，写一行：它**不是**什么。
- 每做一道题，标出自己是在哪一步犹豫的。
- 每隔两天，把易错点用空白纸复述一次，而不是重读笔记。

## 4. 适配你的学习方式

你的认知风格是「{style}」。建议按下面的节奏使用本材料：

1. 先看目录和加粗句，建立地图（3 分钟）；
2. 读第 1、2 节，合上材料用自己的话复述（8 分钟）；
3. 读第 3 节，把易错点写进自己的错题本（5 分钟）；
4. 做文末自检，不会的再回到对应小节（10 分钟）。

## 5. 最小行动

今天只做一件事：**用 5 句话写下「{ctx.topic} 是什么、为什么、怎么用」**。
写不出来不是失败，而是暴露了下一步该补哪里。

## 6. 自检清单

- [ ] 我能不看资料解释「{ctx.topic}」存在的理由
- [ ] 我能说出它和相邻概念的区别
- [ ] 我完成了一个最小示例
- [ ] 我记录了一个仍然模糊的点

---

**下一步**：打开同批次的思维导图，把本节内容压缩成 4 个分支；再去做分层练习。
"""
        return {
            "title": f"{ctx.topic} · 从直觉到系统理解",
            "summary": f"按「先框架、后细节」组织，结合你的知识基础与易错点，配有自检清单。",
            "content": content,
            "keywords": [ctx.topic, "知识框架", "易错点", "自检"],
            "estimated_minutes": 25,
        }


# ---------------------------------------------------------------- 思维导图
class MindmapAgent(ResourceAgent):
    name = "mindmap_agent"
    role = "思维导图智能体"
    resource_type = "mindmap"
    system_prompt = (
        "你是知识点思维导图智能体。输出一棵两层结构树（根节点在 title 里），"
        "一级分支 4-5 个，每个分支 2-4 个子节点；同时给出 Mermaid mindmap 文本。只输出 JSON。"
    )
    schema = {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "summary": {"type": "string"},
            "content": {"type": "string", "description": "Markdown 阅读说明"},
            "nodes": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "label": {"type": "string"},
                        "description": {"type": "string"},
                        "children": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "label": {"type": "string"},
                                    "description": {"type": "string"},
                                },
                                "required": ["label", "description"],
                                "additionalProperties": False,
                            },
                        },
                    },
                    "required": ["label", "description", "children"],
                    "additionalProperties": False,
                },
            },
            "markdown": {"type": "string"},
            "estimated_minutes": {"type": "integer"},
        },
        "required": ["title", "summary", "content", "nodes", "markdown", "estimated_minutes"],
        "additionalProperties": False,
    }

    def extra_meta(self, data: dict, ctx: AgentContext) -> dict:
        return {"nodes": data.get("nodes", []), "markdown": data.get("markdown", "")}

    def mock(self, ctx: AgentContext) -> dict:
        nodes = [
            {
                "label": "为什么学",
                "description": "问题场景与价值",
                "children": [
                    {"label": "它解决什么问题", "description": "先找痛点，再看方案"},
                    {"label": "不用它会怎样", "description": "用反例建立动机"},
                ],
            },
            {
                "label": "核心概念",
                "description": "三到五个必须能复述的概念",
                "children": [
                    {"label": "输入 / 输出", "description": "明确边界"},
                    {"label": "关键机制", "description": "中间发生了什么"},
                    {"label": "与相邻概念的区别", "description": f"重点针对：{_profile(ctx, '易错点偏好')}"},
                ],
            },
            {
                "label": "怎么用",
                "description": "从最小示例到完整任务",
                "children": [
                    {"label": "最小可运行示例", "description": "先跑通，再理解"},
                    {"label": "常见任务模板", "description": "形成可复用套路"},
                    {"label": "调试与验证", "description": "如何知道自己做对了"},
                ],
            },
            {
                "label": "怎么练",
                "description": "练习与反馈闭环",
                "children": [
                    {"label": "概念辨析", "description": "用对比表区分近邻概念"},
                    {"label": "迁移应用", "description": "换一个场景再用一次"},
                    {"label": "错题复盘", "description": "记录犹豫点，而非只记答案"},
                ],
            },
            {
                "label": "学到什么程度",
                "description": "可检查的掌握标准",
                "children": [
                    {"label": "能讲", "description": "30 秒向同学解释"},
                    {"label": "能画", "description": "独立画出结构图"},
                    {"label": "能做", "description": "完成一个真实小任务"},
                ],
            },
        ]
        markdown = (
            "```mermaid\nmindmap\n"
            f"  root(({ctx.topic}))\n"
            + "".join(
                f"    {node['label']}\n"
                + "".join(f"      {child['label']}\n" for child in node["children"])
                for node in nodes
            )
            + "```"
        )
        content = f"""# {ctx.topic} · 知识结构图

{_header(ctx, '思维导图')}
## 怎么用这张图

1. **先看一级分支**：`{', '.join(n['label'] for n in nodes)}`。
2. 合上页面，尝试自己复述这 5 个分支。
3. 对每个二级节点，问自己：能不能举一个例子？
4. 把说不出来的节点标记出来，回到讲解文档对应小节。

> 导图的价值不是「好看」，而是帮你发现「哪些连接还没建立」。
"""
        return {
            "title": f"{ctx.topic} · 一张图看懂知识结构",
            "summary": "5 个一级分支 + 可交互树状结构，适合先建立全局地图。",
            "content": content,
            "nodes": nodes,
            "markdown": markdown,
            "estimated_minutes": 12,
        }


# ---------------------------------------------------------------- 练习题
class ExerciseAgent(ResourceAgent):
    name = "exercise_agent"
    role = "出题智能体"
    resource_type = "exercise"
    system_prompt = (
        "你是分层练习智能体。出 5 道中文题：3 道单选、2 道简答，"
        "难度从概念辨析到迁移应用，必须针对学生的易错点。"
        "每题给答案与解析。只输出 JSON。"
    )
    schema = {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "summary": {"type": "string"},
            "content": {"type": "string"},
            "questions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "integer"},
                        "type": {"type": "string", "enum": ["single", "short"]},
                        "question": {"type": "string"},
                        "options": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "key": {"type": "string"},
                                    "text": {"type": "string"},
                                },
                                "required": ["key", "text"],
                                "additionalProperties": False,
                            },
                        },
                        "answer": {"type": "string"},
                        "explanation": {"type": "string"},
                        "difficulty": {"type": "string", "enum": ["基础", "进阶", "挑战"]},
                    },
                    "required": [
                        "id", "type", "question", "options", "answer", "explanation", "difficulty",
                    ],
                    "additionalProperties": False,
                },
            },
            "estimated_minutes": {"type": "integer"},
        },
        "required": ["title", "summary", "content", "questions", "estimated_minutes"],
        "additionalProperties": False,
    }

    def extra_meta(self, data: dict, ctx: AgentContext) -> dict:
        return {"questions": data.get("questions", [])}

    def mock(self, ctx: AgentContext) -> dict:
        # 题目里只放最核心的一段，避免把整条画像直接塞进题干
        raw_weak = _profile(ctx, "易错点偏好", "概念边界")
        weak = raw_weak.split("，例如")[0].split("；")[0][:30] or "概念边界"
        questions = [
            {
                "id": 1,
                "type": "single",
                "question": f"学习「{ctx.topic}」时，下面哪种顺序最符合「先框架后细节」？",
                "options": [
                    {"key": "A", "text": "先把所有定义背下来，再做题"},
                    {"key": "B", "text": "先弄清它解决什么问题，再展开概念与例子"},
                    {"key": "C", "text": "直接复制一个复杂项目，遇到问题再查"},
                    {"key": "D", "text": "只看视频，不做任何练习"},
                ],
                "answer": "B",
                "explanation": "先建立问题动机与整体结构，再进入细节，能降低认知负荷，也更容易迁移。",
                "difficulty": "基础",
            },
            {
                "id": 2,
                "type": "single",
                "question": f"关于「{weak}」，下面哪种复习方式更有效？",
                "options": [
                    {"key": "A", "text": "反复重读同一段笔记"},
                    {"key": "B", "text": "只看正确答案，不看解析"},
                    {"key": "C", "text": "用对比表和反例主动区分概念"},
                    {"key": "D", "text": "跳过错题，继续做新题"},
                ],
                "answer": "C",
                "explanation": "易错点往往来自概念边界不清。对比表、反例和主动回忆比被动重读更有效。",
                "difficulty": "基础",
            },
            {
                "id": 3,
                "type": "single",
                "question": "你完成了一个最小示例后，下一步最合理的是？",
                "options": [
                    {"key": "A", "text": "立刻换一个更复杂的框架"},
                    {"key": "B", "text": "改一个参数或输入，观察结果如何变化"},
                    {"key": "C", "text": "把代码删掉重新抄一遍"},
                    {"key": "D", "text": "认为已经掌握，不再复习"},
                ],
                "answer": "B",
                "explanation": "在最小示例上做变量控制，是建立因果理解最便宜的方式。",
                "difficulty": "进阶",
            },
            {
                "id": 4,
                "type": "short",
                "question": f"请用 3 句话解释「{ctx.topic}」是什么，并说明它为什么存在。",
                "options": [],
                "answer": "参考要点：①它解决的具体问题；②核心输入与输出；③不用它时的代价。",
                "explanation": "能用自己的话讲清「为什么存在」，说明已经跨过机械记忆阶段。",
                "difficulty": "进阶",
            },
            {
                "id": 5,
                "type": "short",
                "question": f"结合你的易错点「{weak}」，设计一个 10 分钟内可完成的复习动作。",
                "options": [],
                "answer": "参考要点：动作要具体、可检查，例如「画出 A 与 B 的对比表并用一个反例解释区别」。",
                "explanation": "复习动作越具体，越容易真正执行；「再复习一遍」不是可执行动作。",
                "difficulty": "挑战",
            },
        ]
        content = f"""# {ctx.topic} · 分层练习

{_header(ctx, '练习与自检')}
共 5 题：3 道单选 + 2 道简答。建议先独立完成，再看解析。

- 单选：关注「为什么这个选项对」，而不只是答案字母。
- 简答：先写关键词，再补成完整句子。
- 做完后把犹豫的题目标记出来，那才是你真正的复习入口。
"""
        return {
            "title": f"{ctx.topic} · 分层练习与自检",
            "summary": "3 道单选 + 2 道简答，覆盖概念辨析、迁移应用与易错点复盘。",
            "content": content,
            "questions": questions,
            "estimated_minutes": 20,
        }


# ---------------------------------------------------------------- 拓展阅读
class ReadingAgent(ResourceAgent):
    name = "reading_agent"
    role = "拓展阅读智能体"
    resource_type = "reading"
    system_prompt = (
        "你是拓展阅读智能体。为学生设计 4 条阅读路线：入门、进阶、项目、视野，"
        "每条说明为什么值得读、读的时候关注什么。不要编造具体 URL。只输出 JSON。"
    )
    schema = {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "summary": {"type": "string"},
            "content": {"type": "string"},
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "reason": {"type": "string"},
                        "keywords": {"type": "array", "items": {"type": "string"}},
                        "search_hint": {"type": "string"},
                    },
                    "required": ["title", "reason", "keywords", "search_hint"],
                    "additionalProperties": False,
                },
            },
            "estimated_minutes": {"type": "integer"},
        },
        "required": ["title", "summary", "content", "items", "estimated_minutes"],
        "additionalProperties": False,
    }

    def extra_meta(self, data: dict, ctx: AgentContext) -> dict:
        return {"items": data.get("items", [])}

    def mock(self, ctx: AgentContext) -> dict:
        items = [
            {
                "title": "入门：一份官方入门指南",
                "reason": "先把术语和最小工作流对齐，避免在二手资料里迷路。",
                "keywords": [ctx.topic, "官方文档", "快速开始"],
                "search_hint": f"{ctx.topic} official getting started 官方文档 快速开始",
            },
            {
                "title": "进阶：一篇讲原理的长文",
                "reason": f"针对你的知识基础「{_profile(ctx, '知识基础')}」，补上机制层，而不只是 API 用法。",
                "keywords": [ctx.topic, "原理", "架构"],
                "search_hint": f"{ctx.topic} 原理 深入 架构 设计",
            },
            {
                "title": "项目：一个可读的中等规模示例",
                "reason": "看真实项目如何组织目录、处理错误、写测试，这是从教程到工程的桥。",
                "keywords": [ctx.topic, "项目", "工程化"],
                "search_hint": f"{ctx.topic} github example project 中等规模",
            },
            {
                "title": "视野：一条与相邻领域的连接线",
                "reason": "把当前主题放到更大的技术地图里，形成可迁移的理解。",
                "keywords": [ctx.topic, "相邻领域", "技术地图"],
                "search_hint": f"{ctx.topic} 与 相关技术 对比 应用场景",
            },
        ]
        content = f"""# {ctx.topic} · 拓展阅读地图

{_header(ctx, '拓展阅读材料')}
## 阅读策略

不要从长文开始。按「入门 → 原理 → 项目 → 视野」的顺序，每次只读一条路线，
读完后用 3 句话写下：**它回答了什么、我原来错在哪、下一步查什么**。

## 四条路线

| 路线 | 适合什么时候读 | 阅读产出 |
|---|---|---|
| 入门 | 刚开始接触 | 一张术语表 |
| 原理 | 能跑通示例后 | 一张机制图 |
| 项目 | 要动手做东西前 | 一份目录/模块笔记 |
| 视野 | 阶段复盘时 | 一段与相邻技术的对比 |

> 阅读不是收集链接。没有产出的阅读，很容易变成「看过但不会」。
"""
        return {
            "title": f"{ctx.topic} · 拓展阅读与资料地图",
            "summary": "入门 / 原理 / 项目 / 视野四条路线，每条都给出阅读产出要求。",
            "content": content,
            "items": items,
            "estimated_minutes": 18,
        }


# ---------------------------------------------------------------- 代码实操
class CodeAgent(ResourceAgent):
    name = "code_agent"
    role = "代码实操智能体"
    resource_type = "code"
    system_prompt = (
        "你是代码实操智能体。给出一个可直接运行的 Python 最小示例，"
        "代码要有注释、可修改，并配套 3 个递进任务。只输出 JSON。"
    )
    schema = {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "summary": {"type": "string"},
            "content": {"type": "string"},
            "language": {"type": "string"},
            "code": {"type": "string"},
            "tasks": {"type": "array", "items": {"type": "string"}},
            "estimated_minutes": {"type": "integer"},
        },
        "required": ["title", "summary", "content", "language", "code", "tasks", "estimated_minutes"],
        "additionalProperties": False,
    }

    def extra_meta(self, data: dict, ctx: AgentContext) -> dict:
        return {
            "language": data.get("language", "python"),
            "code": data.get("code", ""),
            "tasks": data.get("tasks", []),
        }

    def mock(self, ctx: AgentContext) -> dict:
        code = '''from dataclasses import dataclass, field


@dataclass
class TopicChecklist:
    """一个可运行的学习闭环：概念 -> 示例 -> 自检。"""

    topic: str
    concepts: list[str] = field(default_factory=list)
    practiced: set[str] = field(default_factory=set)

    def add_concept(self, name: str) -> None:
        if name not in self.concepts:
            self.concepts.append(name)

    def practice(self, name: str) -> None:
        if name not in self.concepts:
            raise ValueError(f"先加入概念，再练习：{name}")
        self.practiced.add(name)

    def missing(self) -> list[str]:
        return [name for name in self.concepts if name not in self.practiced]

    def report(self) -> str:
        total = len(self.concepts)
        done = len(self.practiced)
        ratio = done / total if total else 0
        return f"{self.topic}: {done}/{total} 已练习（{ratio:.0%}）"


if __name__ == "__main__":
    checklist = TopicChecklist("__TOPIC__")
    for concept in ["问题动机", "核心概念", "最小示例", "常见误区"]:
        checklist.add_concept(concept)

    checklist.practice("问题动机")
    checklist.practice("核心概念")

    print(checklist.report())
    print("还没练习：", checklist.missing())
'''
        code = code.replace("__TOPIC__", ctx.topic)
        tasks = [
            "把 concepts 换成你实际学到的 4 个概念，运行并观察完成率。",
            "新增一个 `review()` 方法：随机抽一个未练习概念，生成一个自测问题。",
            "把数据保存成 JSON 文件，下次启动时自动恢复进度。",
        ]
        content = f"""# {ctx.topic} · 可运行的最小实操

{_header(ctx, '代码实操案例')}
## 这段代码在做什么

它把「学习闭环」变成一个可执行对象：概念必须先登记，才能被标记为练习过；
`missing()` 会持续暴露你还没动手的部分。它不是业务代码，而是一个可修改的学习脚手架。

## 运行方式

```bash
python checklist.py
```

## 三个递进任务

1. 换掉示例概念，变成你自己的知识清单；
2. 增加随机自测，让程序主动提问；
3. 接入 JSON 持久化，形成跨天可用的学习记录。

> 重点不是这段代码本身，而是「把学习过程建模成数据结构」的思路。
"""
        return {
            "title": f"{ctx.topic} · 可运行的最小实操",
            "summary": "一个零依赖的 Python 学习闭环脚手架，附 3 个递进改造任务。",
            "content": content,
            "language": "python",
            "code": code,
            "tasks": tasks,
            "estimated_minutes": 30,
        }


# ---------------------------------------------------------------- 微课视频
VIDEO_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>__TITLE__</title>
<style>
  :root { --bg:#0f172a; --panel:#172033; --accent:#f59e0b; --text:#e8eefc; --muted:#93a4c3; }
  * { box-sizing:border-box; }
  body { margin:0; min-height:100vh; display:grid; place-items:center; background:
    radial-gradient(circle at 20% 20%, #1e3a5f 0, transparent 40%),
    radial-gradient(circle at 80% 80%, #3b2a12 0, transparent 40%), var(--bg);
    color:var(--text); font-family:"Microsoft YaHei", "PingFang SC", sans-serif; }
  .player { width:min(960px, 94vw); aspect-ratio:16/9; background:var(--panel);
    border:1px solid rgba(255,255,255,.08); border-radius:20px; overflow:hidden;
    box-shadow:0 30px 80px rgba(0,0,0,.45); display:flex; flex-direction:column; position:relative; }
  .top { display:flex; justify-content:space-between; padding:16px 22px; font-size:13px; color:var(--muted); }
  .stage { flex:1; padding:28px 52px; display:flex; flex-direction:column; justify-content:center; gap:18px; }
  .scene-no { color:var(--accent); font-size:13px; letter-spacing:2px; }
  .scene-title { font-size:clamp(24px, 4vw, 42px); font-weight:800; line-height:1.25; }
  .scene-visual { font-size:clamp(14px, 1.8vw, 18px); color:var(--muted); border-left:3px solid var(--accent); padding-left:14px; }
  .narration { font-size:clamp(14px, 1.7vw, 17px); line-height:1.9; color:#cdd9ee; max-width:760px; }
  .bar { height:5px; background:rgba(255,255,255,.08); }
  .bar > i { display:block; height:100%; width:0; background:linear-gradient(90deg,#f59e0b,#fbbf24); transition:width .2s linear; }
  .controls { display:flex; gap:10px; align-items:center; padding:12px 18px; color:var(--muted); font-size:13px; }
  button { background:#24314a; color:var(--text); border:1px solid rgba(255,255,255,.1);
    border-radius:10px; padding:8px 14px; cursor:pointer; }
  button:hover { border-color:var(--accent); color:var(--accent); }
  .dots { display:flex; gap:6px; margin-left:auto; }
  .dot { width:8px; height:8px; border-radius:50%; background:#3a4763; }
  .dot.on { background:var(--accent); }
</style>
</head>
<body>
<div class="player">
  <div class="top"><span>AI 微课 · 个性化资源</span><span id="timer">00:00</span></div>
  <div class="stage">
    <div class="scene-no" id="no">SCENE 01</div>
    <div class="scene-title" id="title"></div>
    <div class="scene-visual" id="visual"></div>
    <div class="narration" id="narration"></div>
  </div>
  <div class="bar"><i id="progress"></i></div>
  <div class="controls">
    <button id="prev">上一幕</button>
    <button id="play">暂停</button>
    <button id="next">下一幕</button>
    <div class="dots" id="dots"></div>
  </div>
</div>
<script>
const scenes = __SCENES__;
let index = 0, playing = true, elapsed = 0, tick = null;
const noEl = document.getElementById('no');
const titleEl = document.getElementById('title');
const visualEl = document.getElementById('visual');
const narrationEl = document.getElementById('narration');
const progress = document.getElementById('progress');
const dots = document.getElementById('dots');
const timer = document.getElementById('timer');
scenes.forEach(() => { const d = document.createElement('span'); d.className='dot'; dots.appendChild(d); });
function fmt(s){ const m=String(Math.floor(s/60)).padStart(2,'0'); const x=String(Math.floor(s%60)).padStart(2,'0'); return m+':'+x; }
function render(){
  const s = scenes[index];
  noEl.textContent = 'SCENE ' + String(index+1).padStart(2,'0') + ' / ' + String(scenes.length).padStart(2,'0');
  titleEl.textContent = s.title;
  visualEl.textContent = s.visual;
  narrationEl.textContent = s.narration;
  [...dots.children].forEach((d,i)=>d.classList.toggle('on', i===index));
  elapsed = 0;
  progress.style.width = '0%';
}
function advance(){
  if (index < scenes.length - 1) { index += 1; render(); }
  else { playing = false; document.getElementById('play').textContent = '重播'; }
}
function loop(){
  clearInterval(tick);
  tick = setInterval(() => {
    if (!playing) return;
    const total = scenes[index].duration;
    elapsed += 0.1;
    progress.style.width = Math.min(100, elapsed/total*100) + '%';
    timer.textContent = fmt(elapsed) + ' / ' + fmt(total);
    if (elapsed >= total) advance();
  }, 100);
}
document.getElementById('prev').onclick = () => { index = Math.max(0, index-1); render(); };
document.getElementById('next').onclick = () => advance();
document.getElementById('play').onclick = (e) => {
  if (!playing && index === scenes.length - 1 && progress.style.width === '100%') { index = 0; render(); }
  playing = !playing; e.target.textContent = playing ? '暂停' : '继续';
};
render(); loop();
</script>
</body>
</html>
"""


class VideoAgent(ResourceAgent):
    name = "video_agent"
    role = "微课视频智能体"
    resource_type = "video"
    system_prompt = (
        "你是微课视频智能体。为一个 1-2 分钟的微课设计 5 个镜头，"
        "每个镜头包含标题、画面描述、旁白、时长（秒）。旁白要口语化、准确。只输出 JSON。"
    )
    schema = {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "summary": {"type": "string"},
            "content": {"type": "string"},
            "scenes": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "no": {"type": "integer"},
                        "title": {"type": "string"},
                        "visual": {"type": "string"},
                        "narration": {"type": "string"},
                        "duration": {"type": "integer"},
                    },
                    "required": ["no", "title", "visual", "narration", "duration"],
                    "additionalProperties": False,
                },
            },
            "estimated_minutes": {"type": "integer"},
        },
        "required": ["title", "summary", "content", "scenes", "estimated_minutes"],
        "additionalProperties": False,
    }

    def extra_meta(self, data: dict, ctx: AgentContext) -> dict:
        return {"scenes": data.get("scenes", [])}

    def to_output(self, data: dict, ctx: AgentContext, result) -> AgentOutput:
        output = super().to_output(data, ctx, result)
        scenes = data.get("scenes", [])
        filename = f"{ctx.task_id or 'demo'}-video.html"
        path = Path(GENERATED_DIR) / filename
        # JSON 里的 < 也转义掉，避免分镜文本意外闭合 <script>
        scenes_json = json.dumps(scenes, ensure_ascii=False).replace("<", "\\u003c")
        path.write_text(
            VIDEO_TEMPLATE.replace("__TITLE__", html.escape(output.title)).replace(
                "__SCENES__", scenes_json
            ),
            encoding="utf-8",
        )
        output.file_path = f"generated/{filename}"
        return output

    def mock(self, ctx: AgentContext) -> dict:
        scenes = [
            {
                "no": 1,
                "title": f"为什么今天要学 {ctx.topic}？",
                "visual": "标题淡入，背景出现三个问题卡片：它解决什么？怎么用？容易错在哪？",
                "narration": f"先别急着记定义。今天我们用几分钟，把 {ctx.topic} 放进一个能理解、能动手、能自检的框架里。",
                "duration": 14,
            },
            {
                "no": 2,
                "title": "先建立一张地图",
                "visual": "四个分支依次展开：动机、概念、用法、练习。",
                "narration": "学习新主题，第一步不是钻细节，而是先知道地图上有哪几块。动机、概念、用法、练习，四块缺一不可。",
                "duration": 16,
            },
            {
                "no": 3,
                "title": "抓住一个核心区别",
                "visual": f"对比卡片：左边「看起来像」，右边「实际是」；关键词高亮：{_profile(ctx, '易错点偏好')}。",
                "narration": "你最容易卡住的地方，通常不是不会，而是两个概念边界不清。先写出「它不是什么」，往往比背定义更快。",
                "duration": 18,
            },
            {
                "no": 4,
                "title": "跑一个最小示例",
                "visual": "终端窗口逐行输出；旁边出现三个可修改的参数。",
                "narration": "理解之后，立刻跑一个最小示例。然后只改一个变量，看结果怎么变。这一步能把「知道」变成「会」。",
                "duration": 17,
            },
            {
                "no": 5,
                "title": "用一道题收尾",
                "visual": "自检清单出现：能讲、能画、能做；最后停在「下一步：分层练习」。",
                "narration": "最后用一道题自检：能不能用三句话讲清楚？能不能画出结构？能不能完成一个小任务？如果都能，就可以进入下一阶段了。",
                "duration": 15,
            },
        ]
        content = f"""# {ctx.topic} · 5 分钟微课脚本

{_header(ctx, '微课视频脚本')}
## 分镜表

| 镜头 | 标题 | 时长 | 画面重点 |
|---|---|---|---|
""" + "\n".join(
            f"| {s['no']} | {s['title']} | {s['duration']}s | {s['visual']} |"
            for s in scenes
        ) + """

## 使用建议

先完整看一遍，不要暂停；第二遍再在「最小示例」处停下，跟着动手。
看完后立刻做同批次的分层练习，趁记忆还热。
"""
        return {
            "title": f"{ctx.topic} · 5 分钟微课",
            "summary": "5 个镜头、约 80 秒的动画微课，自动播放并支持逐幕控制。",
            "content": content,
            "scenes": scenes,
            "estimated_minutes": 5,
        }


AGENT_CLASSES = {
    "document": DocumentAgent,
    "mindmap": MindmapAgent,
    "exercise": ExerciseAgent,
    "reading": ReadingAgent,
    "code": CodeAgent,
    "video": VideoAgent,
}
