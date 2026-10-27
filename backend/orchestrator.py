"""总控编排器（Orchestrator）。

它不负责「写内容」，只负责：
1. 组装共享上下文（画像黑板）；
2. 决定哪些 Agent 并行、哪些串行；
3. 记录每个 Agent 的状态与耗时；
4. 把产物落库，并在失败时做降级而不是整单失败。
"""
from __future__ import annotations

import logging
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed

from agents.assessor_agent import AssessorAgent
from agents.base import AgentContext, AgentOutput
from agents.path_agent import PathAgent
from agents.planner import PlannerAgent
from agents.profile_agent import ProfileAgent
from agents.resource_agents import AGENT_CLASSES
from agents.reviewer import ReviewerAgent
from agents.tutor_agent import TutorAgent
import store

logger = logging.getLogger(__name__)


def _task_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


def _trace(
    *,
    task_id: str,
    student_id: int,
    agent: str,
    role: str,
    status: str,
    model: str = "template-engine",
    input_summary: str = "",
    output_summary: str = "",
    duration_ms: int = 0,
    error: str = "",
) -> None:
    try:
        store.add_agent_run(
            task_id=task_id,
            student_id=student_id,
            agent=agent,
            role=role,
            status=status,
            model=model,
            input_summary=input_summary,
            output_summary=output_summary,
            duration_ms=duration_ms,
            error=error,
        )
    except Exception:  # 追踪失败不能影响主流程
        logger.exception("写入 Agent 运行记录失败：task=%s agent=%s", task_id, agent)


def _context(
    student_id: int,
    *,
    topic: str = "",
    requirements: str = "",
    task_id: str = "",
    records: list[dict] | None = None,
) -> AgentContext:
    student = store.get_student(student_id, use_master=True)
    if student is None:
        raise LookupError("学生不存在")
    store.ensure_dimensions(student_id)
    return AgentContext(
        student=student,
        profile=store.profile_map(student_id, use_master=True),
        topic=topic,
        requirements=requirements,
        task_id=task_id,
        records=records or [],
    )


def decorate_path(path: dict) -> dict:
    """把 steps 里的 resource_ids 展开成资源摘要，方便前端直接渲染。"""
    if not path:
        return path
    steps = path.get("steps") or []
    ids = sorted({rid for step in steps for rid in step.get("resource_ids", [])})
    resource_map = {row["id"]: row for row in store.resources_by_ids(ids)}
    for step in steps:
        step["resources"] = [
            resource_map[rid] for rid in step.get("resource_ids", []) if rid in resource_map
        ]
        step.setdefault("completed", False)
    path["steps"] = steps
    completed = sum(1 for step in steps if step.get("completed"))
    path["progress"] = round(completed / len(steps) * 100) if steps else 0
    return path


class ResourceOrchestrator:
    def generate(
        self,
        student_id: int,
        topic: str,
        requirements: str = "",
        types: list[str] | None = None,
    ) -> dict:
        requested = types or list(AGENT_CLASSES)
        kinds = [kind for kind in requested if kind in AGENT_CLASSES]
        if not kinds:
            raise ValueError("没有可生成的资源类型")

        task_id = _task_id("res")
        ctx = _context(
            student_id, topic=topic, requirements=requirements, task_id=task_id
        )

        # 1) 规划（串行：它是后续并行的输入）
        planner = PlannerAgent()
        try:
            plan = planner.run(ctx, kinds)
            _trace(
                task_id=task_id, student_id=student_id, agent=planner.name,
                role=planner.role, status="success", model=plan.get("model", ""),
                input_summary=f"主题={topic}; 类型={','.join(kinds)}",
                output_summary=plan.get("focus", "")[:200],
                duration_ms=int(plan.get("duration_ms", 0)),
            )
        except Exception as exc:
            logger.exception("规划失败，使用默认计划")
            plan = planner._mock(ctx, kinds)  # 规划失败不能阻断整条流水线
            _trace(
                task_id=task_id, student_id=student_id, agent=planner.name,
                role=planner.role, status="fallback", model="template-engine",
                input_summary=topic, error=str(exc)[:300],
            )
        ctx.plan = plan
        plan_map = {item["type"]: item for item in plan.get("resource_plan", [])}

        # 2) 并行生成（6 个 Agent 互不依赖）
        outputs: list[AgentOutput] = []
        with ThreadPoolExecutor(max_workers=min(6, len(kinds))) as pool:
            futures = {
                pool.submit(self._run_one, ctx, kind, plan_map.get(kind, {})): kind
                for kind in kinds
            }
            for future in as_completed(futures):
                kind = futures[future]
                try:
                    outputs.append(future.result())
                except Exception as exc:
                    logger.exception("资源智能体 %s 失败", kind)
                    _trace(
                        task_id=task_id, student_id=student_id,
                        agent=f"{kind}_agent", role="资源生成智能体",
                        status="failed", model="error",
                        input_summary=f"主题={topic}; kind={kind}",
                        error=str(exc)[:300],
                    )

        if not outputs:
            raise RuntimeError("所有资源智能体都失败了，请检查模型配置或日志")

        # 3) 审核（规则，不花 token）
        reviewer = ReviewerAgent()
        for output in outputs:
            score, note = reviewer.review(output, ctx)
            output.quality_score = score
            output.review_note = (
                f"{output.review_note}；{note}" if output.review_note else note
            )
        avg_score = round(sum(o.quality_score for o in outputs) / len(outputs), 1)
        _trace(
            task_id=task_id, student_id=student_id, agent=reviewer.name,
            role=reviewer.role, status="success", model="rules",
            input_summary=f"{len(outputs)} 个产物",
            output_summary=f"平均质量分 {avg_score}",
        )

        # 4) 按计划顺序落库
        order = {kind: index for index, kind in enumerate(plan.get("sequence", kinds))}
        outputs.sort(key=lambda o: order.get(o.type or "", 99))
        saved: list[dict] = []
        for output in outputs:
            meta = {
                **output.meta,
                "provider": output.provider,
                "model": output.model,
                "duration_ms": output.duration_ms,
                "review_note": output.review_note,
                "plan_focus": plan_map.get(output.type or "", {}).get("focus", ""),
            }
            resource_id = store.create_resource(
                student_id=student_id,
                task_id=task_id,
                resource_type=output.type or "document",
                title=output.title,
                summary=output.summary,
                content=output.content,
                agent=output.agent,
                meta=meta,
                file_path=output.file_path,
                quality_score=output.quality_score,
            )
            saved.append(
                {
                    "id": resource_id,
                    "type": output.type,
                    "title": output.title,
                    "summary": output.summary,
                    "agent": output.agent,
                    "role": output.role,
                    "quality_score": output.quality_score,
                    "provider": output.provider,
                    "model": output.model,
                    "duration_ms": output.duration_ms,
                    "file_path": output.file_path,
                    "review_note": output.review_note,
                    "meta": output.meta,
                }
            )

        return {
            "task_id": task_id,
            "topic": topic,
            "plan": plan,
            "resources": saved,
            "avg_quality": avg_score,
            "agent_count": len(outputs) + 2,  # 规划 + 6 个生成 + 审核
        }

    def _run_one(self, ctx: AgentContext, kind: str, plan_item: dict) -> AgentOutput:
        agent = AGENT_CLASSES[kind]()
        context = AgentContext(
            student=ctx.student,
            profile=ctx.profile,
            topic=ctx.topic,
            requirements=ctx.requirements,
            task_id=ctx.task_id,
            plan={**ctx.plan, "current": plan_item},
        )
        output = agent.run(context)
        _trace(
            task_id=ctx.task_id, student_id=int(ctx.student["id"]), agent=agent.name,
            role=agent.role, status="success", model=output.model,
            input_summary=f"主题={ctx.topic}; 类型={kind}",
            output_summary=output.trace_output(),
            duration_ms=output.duration_ms,
        )
        return output


class ProfileOrchestrator:
    def chat(
        self,
        student_id: int,
        message: str,
        session_id: str | None = None,
    ) -> dict:
        session_id = session_id or f"profile-{student_id}"
        task_id = _task_id("chat")
        ctx = _context(student_id)
        before = dict(ctx.profile)
        history = store.list_dialogues(
            student_id, limit=12, use_master=True, session_id=session_id
        )

        store.add_dialogue(student_id, "user", message, session_id=session_id)
        agent = ProfileAgent()
        result = agent.run(ctx, message, history)

        applied = store.upsert_dimensions(
            student_id, result.get("dimensions", []), source="dialogue"
        )
        changes = [
            {
                "dimension": item["dimension"],
                "old": before.get(item["dimension"], ""),
                "new": item["value"],
                "confidence": item["confidence"],
            }
            for item in applied
        ]
        reply = str(result.get("reply") or "")
        follow_up = str(result.get("follow_up") or "")
        full_reply = f"{reply}\n\n{follow_up}".strip()
        store.add_dialogue(
            student_id,
            "assistant",
            full_reply,
            session_id=session_id,
            meta={"changes": changes, "provider": result.get("provider")},
        )
        _trace(
            task_id=task_id, student_id=student_id, agent=agent.name, role=agent.role,
            status="success", model=str(result.get("model", "")),
            input_summary=message[:160],
            output_summary=f"更新 {len(changes)} 个维度",
            duration_ms=int(result.get("duration_ms", 0)),
        )
        return {
            "reply": reply,
            "follow_up": follow_up,
            "changes": changes,
            "profile": store.profile_payload(student_id, use_master=True),
            "provider": result.get("provider"),
            "model": result.get("model"),
            "duration_ms": result.get("duration_ms"),
            "task_id": task_id,
        }


class PathOrchestrator:
    def generate(self, student_id: int, goal: str | None = None) -> dict:
        task_id = _task_id("path")
        ctx = _context(student_id)
        ctx.resources = store.list_resources(student_id, limit=100, use_master=True)
        if not ctx.resources:
            raise ValueError("还没有资源，请先生成一组学习资源")
        # 路径标题需要一个主题：优先用最近资源 meta 里的 topic
        ctx.topic = next(
            (
                str((row.get("meta") or {}).get("topic", ""))
                for row in ctx.resources
                if (row.get("meta") or {}).get("topic")
            ),
            ctx.resources[0]["title"].split("·")[0].strip(),
        )

        agent = PathAgent()
        data = agent.run(ctx, goal)
        steps = data.get("steps") or []
        if not steps:
            data = agent._mock(ctx, goal)
            steps = data["steps"]

        # 过滤不存在的 resource_id，补齐 completed 状态
        valid_ids = {row["id"] for row in ctx.resources}
        for index, step in enumerate(steps, start=1):
            step["no"] = index
            step["resource_ids"] = [
                int(rid) for rid in step.get("resource_ids", []) if int(rid) in valid_ids
            ]
            step["completed"] = False

        path_id = store.create_path(
            student_id,
            data.get("title") or f"{ctx.topic or '个性化'}学习路径",
            data.get("rationale") or "",
            steps,
        )
        _trace(
            task_id=task_id, student_id=student_id, agent=agent.name, role=agent.role,
            status="success", model=str(data.get("model", "")),
            input_summary=f"{len(ctx.resources)} 个资源",
            output_summary=f"{len(steps)} 个步骤",
            duration_ms=int(data.get("duration_ms", 0)),
        )
        # 写后立刻读：必须走主库，否则可能因为主从延迟拿到 None
        path = store.get_path(path_id, use_master=True)
        return decorate_path(path or {})


class TutorOrchestrator:
    def ask(
        self,
        student_id: int,
        question: str,
        resource_id: int | None = None,
    ) -> dict:
        task_id = _task_id("tutor")
        ctx = _context(student_id)
        resource = store.get_resource(resource_id, use_master=True) if resource_id else None
        agent = TutorAgent()
        data = agent.run(ctx, question, resource)

        store.add_dialogue(
            student_id, "user", question, session_id=f"tutor-{student_id}",
            meta={"resource_id": resource_id},
        )
        store.add_dialogue(
            student_id, "assistant", data["answer"],
            session_id=f"tutor-{student_id}",
            meta={
                **data,
                "resource_id": resource_id,
                "resource": (
                    {"id": resource["id"], "title": resource["title"], "type": resource["type"]}
                    if resource else None
                ),
            },
        )
        store.add_record(
            student_id=student_id,
            action="tutor",
            resource_id=resource_id,
            duration_sec=0,
            detail=question[:1000],
        )
        _trace(
            task_id=task_id, student_id=student_id, agent=agent.name, role=agent.role,
            status="success", model=str(data.get("model", "")),
            input_summary=question[:160],
            output_summary=data.get("key_points", [""])[0][:160],
            duration_ms=int(data.get("duration_ms", 0)),
        )
        return {
            **data,
            "question": question,
            "resource": (
                {"id": resource["id"], "title": resource["title"], "type": resource["type"]}
                if resource else None
            ),
            "task_id": task_id,
        }


class AssessmentOrchestrator:
    def evaluate(self, student_id: int) -> dict:
        task_id = _task_id("eval")
        records = store.list_records(student_id, limit=100, use_master=True)
        ctx = _context(student_id, records=records)
        agent = AssessorAgent()
        data = agent.run(ctx)

        report_id = store.save_report(
            student_id=student_id,
            overall_score=float(data.get("overall_score") or 0),
            dimensions={
                item["dimension"]: item["score"] for item in data.get("dimensions", [])
            },
            strengths=data.get("strengths", []),
            weaknesses=data.get("weaknesses", []),
            suggestions=data.get("suggestions", []),
            summary=data.get("summary", ""),
            source=str(data.get("provider", "agent")),
        )
        applied = store.upsert_dimensions(
            student_id, data.get("profile_updates", []), source="assessment"
        )
        _trace(
            task_id=task_id, student_id=student_id, agent=agent.name, role=agent.role,
            status="success", model=str(data.get("model", "")),
            input_summary=f"{len(records)} 条学习行为",
            output_summary=f"总分 {data.get('overall_score')}，回写 {len(applied)} 个维度",
            duration_ms=int(data.get("duration_ms", 0)),
        )
        report = store.latest_report(student_id, use_master=True) or {}
        report["id"] = report_id
        return {
            "report": report,
            "profile": store.profile_payload(student_id, use_master=True),
            "record_count": len(records),
            "provider": data.get("provider"),
            "model": data.get("model"),
            "task_id": task_id,
        }


resource_orchestrator = ResourceOrchestrator()
profile_orchestrator = ProfileOrchestrator()
path_orchestrator = PathOrchestrator()
tutor_orchestrator = TutorOrchestrator()
assessment_orchestrator = AssessmentOrchestrator()
