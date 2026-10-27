"""学习行为记录与学习效果评估接口。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

import store
from models import ApiResponse, EvaluateRequest, RecordRequest
from orchestrator import assessment_orchestrator

router = APIRouter(prefix="/assessment", tags=["学习评估"])


@router.post("/records")
def add_record(req: RecordRequest) -> ApiResponse:
    if store.get_student(req.student_id, use_master=True) is None:
        raise HTTPException(status_code=404, detail="学生不存在")
    if req.resource_id is not None and store.get_resource(req.resource_id, use_master=True) is None:
        raise HTTPException(status_code=404, detail="资源不存在")
    record_id = store.add_record(
        student_id=req.student_id,
        resource_id=req.resource_id,
        action=req.action,
        score=req.score,
        duration_sec=req.duration_sec,
        detail=req.detail,
    )
    return ApiResponse(
        data={"id": record_id, "stats": store.record_stats(req.student_id)}
    )


@router.get("/records/{student_id}")
def list_records(
    student_id: int,
    limit: int = Query(default=50, ge=1, le=200),
) -> ApiResponse:
    if store.get_student(student_id, use_master=True) is None:
        raise HTTPException(status_code=404, detail="学生不存在")
    return ApiResponse(
        data={
            "records": store.list_records(student_id, limit=limit),
            "stats": store.record_stats(student_id),
        }
    )


@router.post("/evaluate")
def evaluate(req: EvaluateRequest) -> ApiResponse:
    try:
        data = assessment_orchestrator.evaluate(req.student_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return ApiResponse(data=data)


@router.get("/latest/{student_id}")
def latest(student_id: int) -> ApiResponse:
    report = store.latest_report(student_id, use_master=True)
    if report is None:
        raise HTTPException(status_code=404, detail="还没有评估报告")
    return ApiResponse(data=report)


@router.get("/reports/{student_id}")
def reports(student_id: int) -> ApiResponse:
    return ApiResponse(data={"reports": store.list_reports(student_id)})
