"""系统级接口：健康检查、元数据、Agent 追踪、学习总览。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

import db
import store
from llm import llm_service
from models import ApiResponse

router = APIRouter(tags=["系统"])


@router.get("/health")
def health() -> ApiResponse:
    database = db.health()
    llm = llm_service.info()
    ok = database["master"]["ok"]
    return ApiResponse(
        code=0 if ok else 1,
        message="ok" if ok else "database unavailable",
        data={
            "status": "healthy" if ok else "degraded",
            "database": database,
            "llm": llm,
            "services": {
                "api": True,
                "replica_fallback": not database["replica"]["ok"],
            },
        },
    )


@router.get("/meta")
def meta() -> ApiResponse:
    return ApiResponse(
        data={
            "dimensions": [
                {"name": name, "description": description}
                for name, description in store.DIMENSIONS
            ],
            "resource_types": store.RESOURCE_TYPES,
            "llm": llm_service.info(),
        }
    )


@router.get("/agent-runs/{student_id}")
def agent_runs(
    student_id: int,
    limit: int = Query(default=60, ge=1, le=200),
    task_id: str | None = Query(default=None),
) -> ApiResponse:
    if store.get_student(student_id, use_master=True) is None:
        raise HTTPException(status_code=404, detail="学生不存在")
    runs = store.list_agent_runs(student_id, limit=limit)
    if task_id:
        runs = [row for row in runs if row.get("task_id") == task_id]
    return ApiResponse(data={"runs": runs})


@router.get("/dashboard/{student_id}")
def dashboard(student_id: int) -> ApiResponse:
    data = store.dashboard(student_id)
    if not data:
        raise HTTPException(status_code=404, detail="学生不存在")
    return ApiResponse(data=data)


@router.get("/debug/db-route")
def db_route() -> ApiResponse:
    """教学用：直接证明读/写连接确实落在不同端口。"""

    def port(connection_context) -> int:
        with connection_context as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT @@port AS port")
                row = cur.fetchone()
                return int(row["port"])

    return ApiResponse(
        data={
            "write_port": port(db.write_conn()),
            "read_port": port(db.read_conn()),
            "expected": {"write": 3306, "read": 3307},
        }
    )
