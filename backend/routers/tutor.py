"""智能辅导接口。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

import store
from models import ApiResponse, TutorRequest
from orchestrator import tutor_orchestrator

router = APIRouter(prefix="/tutor", tags=["智能辅导"])


@router.get("/history/{student_id}")
def history(
    student_id: int,
    limit: int = Query(default=30, ge=1, le=100),
) -> ApiResponse:
    if store.get_student(student_id, use_master=True) is None:
        raise HTTPException(status_code=404, detail="学生不存在")
    return ApiResponse(
        data={
            "dialogues": store.list_dialogues(
                student_id,
                limit=limit,
                use_master=True,
                session_id=f"tutor-{student_id}",
            )
        }
    )


@router.post("/ask")
def ask(req: TutorRequest) -> ApiResponse:
    try:
        data = tutor_orchestrator.ask(
            student_id=req.student_id,
            question=req.question.strip(),
            resource_id=req.resource_id,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return ApiResponse(data=data)
