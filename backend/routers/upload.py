"""文件上传接口：大文件分片上传 + 小文件批量读写。

分片上传思路（对应云 OSS 的 multipart upload）：
前端把大文件切成 N 片，逐片调 /upload/chunk；全部传完后调 /upload/complete，
后端按序号把分片拼回完整文件。
"""
from __future__ import annotations

import mimetypes
import os
import re
import shutil
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, Response, StreamingResponse

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


@router.get("/status/{file_id}")
def upload_status(
    file_id: str,
    total_chunks: int = Query(default=0, ge=0, le=100000),
) -> ApiResponse:
    """断点续传的核心：告诉前端「服务端已经收到了哪些分片」。

    前端暂停/刷新后，只需要重新上传 missing 里的分片，而不是整文件重传。
    """
    safe_id = _safe_name(file_id, "upload")
    chunk_dir = UPLOAD_ROOT / safe_id
    uploaded: list[int] = []
    if chunk_dir.is_dir():
        uploaded = sorted(
            int(path.name)
            for path in chunk_dir.iterdir()
            if path.is_file() and path.name.isdigit()
        )
    uploaded_set = set(uploaded)
    missing = (
        [index for index in range(total_chunks) if index not in uploaded_set]
        if total_chunks
        else []
    )
    return ApiResponse(data={
        "file_id": safe_id,
        "uploaded": uploaded,
        "missing": missing,
        "uploaded_count": len(uploaded),
    })


def _content_disposition(filename: str) -> str:
    ascii_name = filename.encode("ascii", "ignore").decode() or "download.bin"
    return f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(filename)}"


@router.get("/download/{filename}")
def download(filename: str, request: Request):
    """支持 Range 的下载端点：206 Partial Content 是下载断点续传的基础。"""
    safe_filename = _safe_name(filename, "download.bin")
    path = UPLOAD_ROOT / safe_filename
    if not path.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")

    total = path.stat().st_size
    media_type = mimetypes.guess_type(safe_filename)[0] or "application/octet-stream"
    disposition = _content_disposition(safe_filename)
    range_header = request.headers.get("range")

    if range_header:
        match = re.fullmatch(r"bytes=(\d*)-(\d*)", range_header.strip())
        if match:
            start_raw, end_raw = match.groups()
            start = int(start_raw) if start_raw else 0
            end = int(end_raw) if end_raw else total - 1
            end = min(end, total - 1)
            if start >= total or end < start:
                return Response(
                    status_code=416,
                    headers={"Content-Range": f"bytes */{total}"},
                )
            length = end - start + 1

            def iter_range():
                with path.open("rb") as source:
                    source.seek(start)
                    remaining = length
                    while remaining > 0:
                        block = source.read(min(64 * 1024, remaining))
                        if not block:
                            break
                        remaining -= len(block)
                        yield block

            return StreamingResponse(
                iter_range(),
                status_code=206,
                media_type=media_type,
                headers={
                    "Content-Range": f"bytes {start}-{end}/{total}",
                    "Content-Length": str(length),
                    "Accept-Ranges": "bytes",
                    "Content-Disposition": disposition,
                },
            )

    return FileResponse(
        path,
        media_type=media_type,
        filename=safe_filename,
        headers={"Accept-Ranges": "bytes", "Content-Disposition": disposition},
    )


@router.post("/batch")
async def upload_batch(files: list[UploadFile] = File(...)) -> ApiResponse:
    """小文件批量上传：一次请求接收多个小文件，逐个落盘。"""
    if len(files) > 100:
        raise HTTPException(status_code=400, detail="一次最多上传 100 个文件")
    saved = []
    total_size = 0
    for f in files:
        safe_filename = _safe_name(f.filename or "", "unnamed.bin")
        path = UPLOAD_ROOT / safe_filename
        with path.open("wb") as out:
            shutil.copyfileobj(f.file, out)
        size = path.stat().st_size
        total_size += size
        saved.append({
            "filename": safe_filename,
            "size": size,
            "url": f"/uploads/{safe_filename}",
        })

    return ApiResponse(data={
        "count": len(saved),
        "total_size": total_size,
        "files": saved,
    })
