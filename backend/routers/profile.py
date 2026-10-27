"""画像接口：查询、对话式构建、对话历史。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

import store
from models import ApiResponse, ChatRequest
from orchestrator import profile_orchestrator

router = APIRouter(prefix="/profile", tags=["画像"])


@router.get("/{student_id}")
def get_profile(student_id: int) -> ApiResponse:
    payload = store.profile_payload(student_id, use_master=True)
    if payload is None:
        raise HTTPException(status_code=404, detail="学生不存在")
    return ApiResponse(data=payload)


@router.get("/{student_id}/dialogues")
def list_dialogues(
    student_id: int,
    limit: int = Query(default=50, ge=1, le=200),
) -> ApiResponse:
    if store.get_student(student_id, use_master=True) is None:
        raise HTTPException(status_code=404, detail="学生不存在")
    return ApiResponse(
        data={
            "dialogues": store.list_dialogues(
                student_id,
                limit=limit,
                use_master=True,
                session_id=f"profile-{student_id}",
            )
        }
    )


@router.post("/{student_id}/chat")
def chat(student_id: int, req: ChatRequest) -> ApiResponse:
    try:
        data = profile_orchestrator.chat(
            student_id=student_id,
            message=req.message.strip(),
            session_id=req.session_id,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return ApiResponse(data=data)
