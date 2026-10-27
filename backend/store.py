"""持久化层：所有 SQL 集中在这里。

- 读默认走从库，写默认走主库。
- 需要「写后立刻读」的地方显式传 use_master=True。
- JSON 字段统一在这里序列化/反序列化，上层拿到的就是 dict/list。
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from db import execute, execute_many, fetch_all, fetch_one

# 画像的 7 个维度（需求要求不少于 6 个）
DIMENSIONS = [
    ("知识基础", "已掌握的知识与技能水平"),
    ("认知风格", "更偏好的信息组织与理解方式"),
    ("学习目标", "当前最想达成的学习结果"),
    ("易错点偏好", "容易反复出错或混淆的地方"),
    ("学习节奏", "可投入时间与专注方式"),
    ("兴趣方向", "愿意主动投入的主题"),
    ("实践偏好", "更喜欢的学习材料形态"),
]

DEFAULT_VALUES = {
    "知识基础": "待补充：你学过哪些相关课程或技术？",
    "认知风格": "待补充：你更喜欢先看框架、看例子，还是先读文档？",
    "学习目标": "待补充：这学期最想完成什么？",
    "易错点偏好": "待补充：哪些概念你总容易混淆？",
    "学习节奏": "待补充：你每周能投入多少时间？",
    "兴趣方向": "待补充：哪些方向你会主动去了解？",
    "实践偏好": "待补充：你更喜欢图解、代码示例还是长文档？",
}

RESOURCE_TYPES = {
    "document": "专业讲解文档",
    "mindmap": "知识点思维导图",
    "exercise": "分层练习题目",
    "reading": "拓展阅读材料",
    "code": "代码实操案例",
    "video": "微课视频脚本",
}

VALID_DIMENSIONS = {name for name, _ in DIMENSIONS}
VALID_RESOURCE_TYPES = set(RESOURCE_TYPES)


def _loads(value: Any, default: Any) -> Any:
    if value is None:
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def _serialize_row(row: dict | None) -> dict | None:
    if row is None:
        return None
    result = dict(row)
    for key in ("created_at", "updated_at"):
        if isinstance(result.get(key), datetime):
            result[key] = result[key].strftime("%Y-%m-%d %H:%M:%S")
    for key in ("meta", "steps", "dimensions"):
        if key in result:
            result[key] = _loads(result[key], None)
    return result


# ---------------- 学生 ----------------
def list_students(limit: int = 50) -> list[dict]:
    """默认只取最近 50 个，避免历史压测数据把下拉框撑爆。"""
    rows = fetch_all(
        "SELECT id, name, major, age, goal, email, created_at "
        "FROM student ORDER BY id DESC LIMIT %s",
        (limit,),
    )
    return [_serialize_row(r) for r in rows]  # type: ignore[misc]


def get_student(student_id: int, *, use_master: bool = False) -> dict | None:
    row = fetch_one(
        "SELECT id, name, major, age, goal, email, created_at, updated_at "
        "FROM student WHERE id = %s",
        (student_id,),
        use_master=use_master,
    )
    return _serialize_row(row)


def create_student(name: str, major: str, age: int, goal: str, email: str) -> int:
    return execute(
        "INSERT INTO student(name, major, age, goal, email) VALUES(%s,%s,%s,%s,%s)",
        (name, major, age, goal, email),
    )


# ---------------- 画像 ----------------
def get_dimensions(student_id: int, *, use_master: bool = False) -> list[dict]:
    rows = fetch_all(
        "SELECT dimension, value, confidence, source, updated_at "
        "FROM profile_dimension WHERE student_id = %s ORDER BY id",
        (student_id,),
        use_master=use_master,
    )
    return [_serialize_row(r) for r in rows]  # type: ignore[misc]


def profile_map(student_id: int, *, use_master: bool = False) -> dict[str, str]:
    return {
        row["dimension"]: (row["value"] or "")
        for row in get_dimensions(student_id, use_master=use_master)
    }


def ensure_dimensions(student_id: int) -> None:
    existing = {row["dimension"] for row in get_dimensions(student_id, use_master=True)}
    missing = [(name, DEFAULT_VALUES[name]) for name, _ in DIMENSIONS if name not in existing]
    if not missing:
        return
    execute_many(
        "INSERT INTO profile_dimension(student_id, dimension, value, confidence, source) "
        "VALUES(%s,%s,%s,%s,%s)",
        [(student_id, name, value, 0.3, "system") for name, value in missing],
    )


def upsert_dimensions(
    student_id: int,
    updates: list[dict],
    *,
    source: str = "dialogue",
) -> list[dict]:
    """updates: [{dimension, value, confidence}]，只接受已知维度。"""
    rows = []
    applied = []
    for item in updates:
        dimension = str(item.get("dimension", "")).strip()
        value = str(item.get("value", "")).strip()
        if dimension not in VALID_DIMENSIONS or not value:
            continue
        try:
            confidence = max(0.0, min(1.0, float(item.get("confidence", 0.7))))
        except (TypeError, ValueError):
            confidence = 0.7
        rows.append((student_id, dimension, value[:2000], confidence, source))
        applied.append(
            {"dimension": dimension, "value": value[:2000], "confidence": confidence}
        )
    if rows:
        execute_many(
            "INSERT INTO profile_dimension(student_id, dimension, value, confidence, source) "
            "VALUES(%s,%s,%s,%s,%s) "
            "ON DUPLICATE KEY UPDATE value=VALUES(value), confidence=VALUES(confidence), "
            "source=VALUES(source)",
            rows,
        )
    return applied


def profile_payload(student_id: int, *, use_master: bool = False) -> dict | None:
    student = get_student(student_id, use_master=use_master)
    if student is None:
        return None
    dimensions = get_dimensions(student_id, use_master=use_master)
    by_name = {row["dimension"]: row for row in dimensions}
    ordered = []
    filled = 0
    for name, description in DIMENSIONS:
        row = by_name.get(name)
        value = row["value"] if row else DEFAULT_VALUES[name]
        confidence = float(row["confidence"]) if row else 0.0
        if row and not value.startswith("待补充") and confidence > 0.3:
            filled += 1
        ordered.append(
            {
                "dimension": name,
                "description": description,
                "value": value,
                "confidence": round(confidence, 2),
                "source": row["source"] if row else "system",
                "updated_at": row["updated_at"] if row else None,
            }
        )
    return {
        "student": student,
        "dimensions": ordered,
        "completeness": round(filled / len(DIMENSIONS) * 100),
        "dimension_count": len(ordered),
    }


# ---------------- 对话 ----------------
def add_dialogue(
    student_id: int,
    role: str,
    content: str,
    *,
    session_id: str | None = None,
    meta: dict | None = None,
) -> int:
    return execute(
        "INSERT INTO dialogue(student_id, session_id, role, content, meta) "
        "VALUES(%s,%s,%s,%s,%s)",
        (student_id, session_id, role, content, _json(meta) if meta else None),
    )


def list_dialogues(
    student_id: int,
    limit: int = 50,
    *,
    use_master: bool = False,
    session_id: str | None = None,
) -> list[dict]:
    where = "student_id = %s"
    params: list = [student_id]
    if session_id:
        where += " AND session_id = %s"
        params.append(session_id)
    params.append(limit)
    rows = fetch_all(
        "SELECT * FROM ("
        "  SELECT id, student_id, session_id, role, content, meta, created_at "
        f"  FROM dialogue WHERE {where} ORDER BY id DESC LIMIT %s"
        ") t ORDER BY id ASC",
        tuple(params),
        use_master=use_master,
    )
    return [_serialize_row(r) for r in rows]  # type: ignore[misc]


# ---------------- 资源 ----------------
def create_resource(
    *,
    student_id: int,
    task_id: str,
    resource_type: str,
    title: str,
    summary: str,
    content: str,
    agent: str,
    meta: dict | None = None,
    file_path: str | None = None,
    quality_score: float = 0,
) -> int:
    return execute(
        "INSERT INTO resource(student_id, task_id, type, title, summary, content, "
        "file_path, meta, agent, status, quality_score) "
        "VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        (
            student_id,
            task_id,
            resource_type,
            title[:200],
            summary,
            content,
            file_path,
            _json(meta or {}),
            agent,
            "ready",
            quality_score,
        ),
    )


def list_resources(
    student_id: int,
    *,
    resource_type: str | None = None,
    limit: int = 100,
    use_master: bool = False,
) -> list[dict]:
    if resource_type:
        rows = fetch_all(
            "SELECT id, student_id, task_id, type, title, summary, file_path, meta, "
            "agent, status, quality_score, created_at "
            "FROM resource WHERE student_id = %s AND type = %s "
            "ORDER BY id DESC LIMIT %s",
            (student_id, resource_type, limit),
            use_master=use_master,
        )
    else:
        rows = fetch_all(
            "SELECT id, student_id, task_id, type, title, summary, file_path, meta, "
            "agent, status, quality_score, created_at "
            "FROM resource WHERE student_id = %s ORDER BY id DESC LIMIT %s",
            (student_id, limit),
            use_master=use_master,
        )
    return [_serialize_row(r) for r in rows]  # type: ignore[misc]


def get_resource(resource_id: int, *, use_master: bool = False) -> dict | None:
    row = fetch_one("SELECT * FROM resource WHERE id = %s", (resource_id,), use_master=use_master)
    return _serialize_row(row)


def resources_by_ids(ids: list[int]) -> list[dict]:
    if not ids:
        return []
    placeholders = ",".join(["%s"] * len(ids))
    rows = fetch_all(
        f"SELECT id, type, title, summary FROM resource WHERE id IN ({placeholders})",
        tuple(ids),
        use_master=True,
    )
    return [_serialize_row(r) for r in rows]  # type: ignore[misc]


def delete_resource(resource_id: int) -> int:
    return execute("DELETE FROM resource WHERE id = %s", (resource_id,))


def resource_counts(student_id: int, *, use_master: bool = False) -> dict[str, int]:
    rows = fetch_all(
        "SELECT type, COUNT(*) AS n FROM resource WHERE student_id = %s GROUP BY type",
        (student_id,),
        use_master=use_master,
    )
    return {row["type"]: int(row["n"]) for row in rows}


# ---------------- 学习路径 ----------------
def create_path(
    student_id: int,
    title: str,
    rationale: str,
    steps: list[dict],
) -> int:
    return execute(
        "INSERT INTO learning_path(student_id, title, rationale, steps, status) "
        "VALUES(%s,%s,%s,%s,'active')",
        (student_id, title[:200], rationale, _json(steps)),
    )


def latest_path(student_id: int, *, use_master: bool = False) -> dict | None:
    row = fetch_one(
        "SELECT * FROM learning_path WHERE student_id = %s ORDER BY id DESC LIMIT 1",
        (student_id,),
        use_master=use_master,
    )
    return _serialize_row(row)


def get_path(path_id: int, *, use_master: bool = False) -> dict | None:
    return _serialize_row(
        fetch_one(
            "SELECT * FROM learning_path WHERE id = %s",
            (path_id,),
            use_master=use_master,
        )
    )


def update_path_steps(path_id: int, steps: list[dict]) -> int:
    return execute(
        "UPDATE learning_path SET steps = %s WHERE id = %s",
        (_json(steps), path_id),
    )


# ---------------- 学习行为 ----------------
def add_record(
    *,
    student_id: int,
    action: str,
    resource_id: int | None = None,
    score: float | None = None,
    duration_sec: int = 0,
    detail: str = "",
) -> int:
    return execute(
        "INSERT INTO learning_record(student_id, resource_id, action, score, "
        "duration_sec, detail) VALUES(%s,%s,%s,%s,%s,%s)",
        (student_id, resource_id, action, score, duration_sec, detail),
    )


def list_records(
    student_id: int,
    limit: int = 100,
    *,
    use_master: bool = False,
) -> list[dict]:
    rows = fetch_all(
        "SELECT * FROM ("
        "  SELECT r.id, r.student_id, r.resource_id, r.action, r.score, "
        "         r.duration_sec, r.detail, r.created_at, ro.title AS resource_title, "
        "         ro.type AS resource_type "
        "  FROM learning_record r LEFT JOIN resource ro ON ro.id = r.resource_id "
        "  WHERE r.student_id = %s ORDER BY r.id DESC LIMIT %s"
        ") t ORDER BY id DESC",
        (student_id, limit),
        use_master=use_master,
    )
    return [_serialize_row(r) for r in rows]  # type: ignore[misc]


def record_stats(student_id: int) -> dict:
    row = fetch_one(
        "SELECT COUNT(*) AS actions, "
        "       COALESCE(SUM(duration_sec), 0) AS seconds, "
        "       COALESCE(AVG(score), 0) AS avg_score, "
        "       SUM(CASE WHEN action = 'answer' THEN 1 ELSE 0 END) AS answers "
        "FROM learning_record WHERE student_id = %s",
        (student_id,),
        use_master=True,
    )
    return {
        "actions": int(row["actions"] or 0),
        "minutes": round(int(row["seconds"] or 0) / 60, 1),
        "avg_score": round(float(row["avg_score"] or 0), 1),
        "answers": int(row["answers"] or 0),
    }


# ---------------- 智能体追踪 ----------------
def add_agent_run(
    *,
    task_id: str,
    student_id: int,
    agent: str,
    role: str,
    status: str,
    model: str,
    input_summary: str = "",
    output_summary: str = "",
    error: str = "",
    duration_ms: int = 0,
) -> int:
    return execute(
        "INSERT INTO agent_run(task_id, student_id, agent, role, status, model, "
        "input_summary, output_summary, error, duration_ms) "
        "VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        (
            task_id, student_id, agent, role, status, model,
            input_summary[:2000], output_summary[:2000], error[:2000], duration_ms,
        ),
    )


def list_agent_runs(student_id: int, limit: int = 60) -> list[dict]:
    rows = fetch_all(
        "SELECT * FROM ("
        "  SELECT id, task_id, agent, role, status, model, input_summary, "
        "         output_summary, error, duration_ms, created_at "
        "  FROM agent_run WHERE student_id = %s ORDER BY id DESC LIMIT %s"
        ") t ORDER BY id ASC",
        (student_id, limit),
    )
    return [_serialize_row(r) for r in rows]  # type: ignore[misc]


# ---------------- 评估报告 ----------------
def save_report(
    *,
    student_id: int,
    overall_score: float,
    dimensions: dict,
    strengths: list[str],
    weaknesses: list[str],
    suggestions: list[str],
    summary: str,
    source: str = "agent",
) -> int:
    return execute(
        "INSERT INTO assessment_report(student_id, overall_score, dimensions, "
        "strengths, weaknesses, suggestions, summary, source) "
        "VALUES(%s,%s,%s,%s,%s,%s,%s,%s)",
        (
            student_id,
            overall_score,
            _json(dimensions),
            _json(strengths),
            _json(weaknesses),
            _json(suggestions),
            summary,
            source,
        ),
    )


def latest_report(student_id: int, *, use_master: bool = False) -> dict | None:
    row = fetch_one(
        "SELECT * FROM assessment_report WHERE student_id = %s ORDER BY id DESC LIMIT 1",
        (student_id,),
        use_master=use_master,
    )
    if row is None:
        return None
    result = _serialize_row(row)
    for key in ("strengths", "weaknesses", "suggestions"):
        if result and key in result:
            result[key] = _loads(result[key], [])
    result["dimensions"] = _loads(result.get("dimensions"), {}) if result else {}
    return result


def list_reports(student_id: int, limit: int = 10) -> list[dict]:
    rows = fetch_all(
        "SELECT id, overall_score, summary, created_at FROM assessment_report "
        "WHERE student_id = %s ORDER BY id DESC LIMIT %s",
        (student_id, limit),
    )
    return [_serialize_row(r) for r in rows]  # type: ignore[misc]


# ---------------- 总览 ----------------
def dashboard(student_id: int) -> dict:
    student = get_student(student_id, use_master=True)
    if student is None:
        return {}
    path = latest_path(student_id, use_master=True)
    steps = path["steps"] if path and path.get("steps") else []
    completed = sum(1 for step in steps if step.get("completed"))
    return {
        "student": student,
        "profile": profile_payload(student_id, use_master=True),
        "resource_counts": resource_counts(student_id, use_master=True),
        "resource_total": sum(resource_counts(student_id, use_master=True).values()),
        "path": {
            "id": path["id"] if path else None,
            "title": path["title"] if path else None,
            "steps": len(steps),
            "completed": completed,
        },
        "records": record_stats(student_id),
        "assessment": latest_report(student_id, use_master=True),
    }
