"""文件上传接口：大文件分片上传 + 小文件批量读写。

分片上传思路（对应云 OSS 的 multipart upload）：
前端把大文件切成 N 片，逐片调 /upload/chunk；全部传完后调 /upload/complete，
后端按序号把分片拼回完整文件。
"""
from __future__ import annotations

import os
import re
import shutil
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from config import UPLOAD_DIR
from models import ApiResponse

router = APIRouter(prefix="/upload", tags=["文件上传"])

UPLOAD_ROOT = Path(UPLOAD_DIR)
UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
_SAFE_NAME = re.compile(r"[^0-9A-Za-z._\-一-龥]")


def _safe_name(name: str, fallback: str) -> str:
    """只允许文件名，不允许路径分隔符，防止 ../ 目录穿越。"""
    base = os.path.basename(name or "").strip()
    cleaned = _SAFE_NAME.sub("_", base)
    return cleaned or fallback


@router.post("/chunk")
async def upload_chunk(
    file_id: str = Form(...),       # 本次上传的唯一标识（前端生成，如 UUID）
    chunk_index: int = Form(...),   # 分片序号，从 0 开始
    file: UploadFile = File(...),   # 分片内容
) -> ApiResponse:
    """接收一个分片，落到 uploads/{file_id}/{chunk_index}。"""
    if chunk_index < 0 or chunk_index > 100000:
        raise HTTPException(status_code=400, detail="chunk_index 不合法")
    safe_id = _safe_name(file_id, "upload")
    chunk_dir = UPLOAD_ROOT / safe_id
    chunk_dir.mkdir(parents=True, exist_ok=True)
    chunk_path = chunk_dir / str(chunk_index)

    with chunk_path.open("wb") as f:
        f.write(await file.read())

    return ApiResponse(data={"file_id": safe_id, "chunk": chunk_index})


@router.post("/complete")
async def complete_upload(
    file_id: str = Form(...),
    total_chunks: int = Form(...),
    filename: str = Form(...),
) -> ApiResponse:
    """全部传完后，按序号 0..total_chunks-1 顺序重组为最终文件。"""
    if total_chunks <= 0 or total_chunks > 100000:
        raise HTTPException(status_code=400, detail="total_chunks 不合法")
    safe_id = _safe_name(file_id, "upload")
    safe_filename = _safe_name(filename, "merged.bin")
    chunk_dir = UPLOAD_ROOT / safe_id
    if not chunk_dir.is_dir():
        raise HTTPException(status_code=404, detail="没有找到分片目录")

    final_path = UPLOAD_ROOT / safe_filename
    missing = [i for i in range(total_chunks) if not (chunk_dir / str(i)).exists()]
    if missing:
        raise HTTPException(status_code=400, detail=f"缺少分片：{missing[:10]}")

    with final_path.open("wb") as out:      # ① 打开最终文件（准备写）
        for i in range(total_chunks):        # ② 按 0..N 顺序
            with (chunk_dir / str(i)).open("rb") as f:   # ③ 读第 i 个分片
                shutil.copyfileobj(f, out)  # ④ 写入最终文件

    shutil.rmtree(chunk_dir)     # 清理临时分片
    return ApiResponse(data={
        "filename": safe_filename,
        "size": final_path.stat().st_size,
        "url": f"/uploads/{safe_filename}",
    })


@router.post("/batch")
async def upload_batch(files: list[UploadFile] = File(...)) -> ApiResponse:
    """小文件批量上传：一次请求接收多个小文件，逐个落盘。"""
    if len(files) > 100:
        raise HTTPException(status_code=400, detail="一次最多上传 100 个文件")
    saved = []
    for f in files:
        safe_filename = _safe_name(f.filename or "", "unnamed.bin")
        path = UPLOAD_ROOT / safe_filename
        with path.open("wb") as out:
            shutil.copyfileobj(f.file, out)
        saved.append({"filename": safe_filename, "size": path.stat().st_size})

    return ApiResponse(data={"count": len(saved), "files": saved})
