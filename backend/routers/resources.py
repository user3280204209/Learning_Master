"""学习资源接口：多智能体生成、列表、详情、删除、浏览埋点。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

import store
from models import ApiResponse, ResourceGenerateRequest
from orchestrator import resource_orchestrator

router = APIRouter(prefix="/resources", tags=["资源"])


@router.post("/generate")
def generate(req: ResourceGenerateRequest) -> ApiResponse:
    try:
        data = resource_orchestrator.generate(
            student_id=req.student_id,
            topic=req.topic.strip(),
            requirements=req.requirements.strip(),
            types=req.types,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return ApiResponse(data=data)


@router.get("")
def list_resources(
    student_id: int = Query(gt=0),
    resource_type: str | None = Query(default=None, alias="type"),
    limit: int = Query(default=100, ge=1, le=200),
) -> ApiResponse:
    if resource_type and resource_type not in store.VALID_RESOURCE_TYPES:
        raise HTTPException(status_code=400, detail=f"未知资源类型：{resource_type}")
    resources = store.list_resources(
        student_id, resource_type=resource_type, limit=limit, use_master=True
    )
    return ApiResponse(
        data={
            "resources": resources,
            "counts": store.resource_counts(student_id),
            "types": store.RESOURCE_TYPES,
        }
    )


@router.get("/{resource_id}")
def get_resource(resource_id: int) -> ApiResponse:
    resource = store.get_resource(resource_id, use_master=True)
    if resource is None:
        raise HTTPException(status_code=404, detail="资源不存在")
    return ApiResponse(data=resource)


@router.delete("/{resource_id}")
def delete_resource(resource_id: int) -> ApiResponse:
    if store.get_resource(resource_id) is None:
        raise HTTPException(status_code=404, detail="资源不存在")
    store.delete_resource(resource_id)
    return ApiResponse(data={"deleted": resource_id})


@router.post("/{resource_id}/view")
def mark_view(resource_id: int, duration_sec: int = Query(default=30, ge=0, le=36000)) -> ApiResponse:
    resource = store.get_resource(resource_id, use_master=True)
    if resource is None:
        raise HTTPException(status_code=404, detail="资源不存在")
    store.add_record(
        student_id=int(resource["student_id"]),
        resource_id=resource_id,
        action="view",
        duration_sec=duration_sec,
        detail=f"浏览资源：{resource['title']}",
    )
    return ApiResponse(
        data={
            "resource_id": resource_id,
            "stats": store.record_stats(int(resource["student_id"])),
        }
    )
