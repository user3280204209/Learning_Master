"""学习路径接口：生成、查询、步骤完成度更新。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

import store
from models import ApiResponse, PathGenerateRequest, PathStepUpdate
from orchestrator import decorate_path, path_orchestrator

router = APIRouter(prefix="/paths", tags=["学习路径"])


@router.post("/generate")
def generate(req: PathGenerateRequest) -> ApiResponse:
    try:
        path = path_orchestrator.generate(req.student_id, req.goal)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ApiResponse(data=path)


@router.get("/{student_id}")
def latest(student_id: int) -> ApiResponse:
    if store.get_student(student_id, use_master=True) is None:
        raise HTTPException(status_code=404, detail="学生不存在")
    path = store.latest_path(student_id, use_master=True)
    if path is None:
        raise HTTPException(status_code=404, detail="还没有学习路径，请先生成资源并规划")
    return ApiResponse(data=decorate_path(path))


@router.patch("/{path_id}/steps/{step_no}")
def update_step(path_id: int, step_no: int, req: PathStepUpdate) -> ApiResponse:
    path = store.get_path(path_id, use_master=True)
    if path is None:
        raise HTTPException(status_code=404, detail="学习路径不存在")
    steps = path.get("steps") or []
    target = next((step for step in steps if int(step.get("no", 0)) == step_no), None)
    if target is None:
        raise HTTPException(status_code=404, detail=f"步骤 {step_no} 不存在")
    target["completed"] = req.completed
    store.update_path_steps(path_id, steps)
    return ApiResponse(
        data=decorate_path(store.get_path(path_id, use_master=True) or {})
    )
