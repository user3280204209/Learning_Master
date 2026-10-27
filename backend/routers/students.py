"""学生与学习总览接口。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

import store
from models import ApiResponse, StudentCreate

router = APIRouter(prefix="/students", tags=["学生"])


@router.get("")
def list_students(
    limit: int = Query(default=50, ge=1, le=200),
) -> ApiResponse:
    return ApiResponse(data={"students": store.list_students(limit=limit)})


@router.post("")
def create_student(req: StudentCreate) -> ApiResponse:
    student_id = store.create_student(
        name=req.name.strip(),
        major=req.major.strip(),
        age=req.age,
        goal=req.goal.strip(),
        email=req.email.strip(),
    )
    store.ensure_dimensions(student_id)
    return ApiResponse(data=store.profile_payload(student_id, use_master=True))


@router.get("/{student_id}")
def get_student(student_id: int) -> ApiResponse:
    payload = store.profile_payload(student_id)
    if payload is None:
        raise HTTPException(status_code=404, detail="学生不存在")
    return ApiResponse(data=payload)


@router.get("/{student_id}/dashboard")
def dashboard(student_id: int) -> ApiResponse:
    data = store.dashboard(student_id)
    if not data:
        raise HTTPException(status_code=404, detail="学生不存在")
    return ApiResponse(data=data)
