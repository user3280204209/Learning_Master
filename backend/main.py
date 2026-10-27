"""应用入口：创建 app、注册路由、统一异常、托管前端与上传文件。

启动（在 backend/ 下）：
    python -m uvicorn main:app --reload --port 8001
文档：
    http://127.0.0.1:8001/docs
"""
from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager

import pymysql
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

import db
from config import API_PREFIX, FRONTEND_DIST, UPLOAD_DIR
from llm import llm_service
from logging_conf import setup_logging
from routers import assessment, paths, profile, resources, students, system, tutor, upload

setup_logging()
logger = logging.getLogger("learning")


@asynccontextmanager
async def lifespan(app: FastAPI):
    health = db.health()
    logger.info("启动完成｜LLM=%s｜DB主库=%s｜DB从库=%s",
                llm_service.mode, health["master"]["ok"], health["replica"]["ok"])
    if not health["replica"]["ok"]:
        logger.warning("从库不可用，读请求将降级到主库")
    yield
    db.close_pools()
    logger.info("应用已停止，连接池已关闭")


app = FastAPI(
    title="个性化资源生成与学习多智能体系统",
    description=(
        "6 个专职智能体 + 1 个编排器：画像抽取、讲解文档、思维导图、分层练习、"
        "拓展阅读、代码实操、微课、路径规划、智能辅导、学习评估。"
    ),
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

for router in (
    system.router,
    students.router,
    profile.router,
    resources.router,
    paths.router,
    tutor.router,
    assessment.router,
    upload.router,
):
    app.include_router(router, prefix=API_PREFIX)


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"code": exc.status_code, "message": str(exc.detail), "data": None},
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    errors = []
    for item in exc.errors():
        location = ".".join(str(part) for part in item.get("loc", []) if part != "body")
        errors.append({"field": location, "message": item.get("msg", "参数不合法")})
    return JSONResponse(
        status_code=422,
        content={
            "code": 422,
            "message": "请求参数不合法",
            "data": {"errors": errors},
        },
    )


@app.exception_handler(pymysql.MySQLError)
async def mysql_exception_handler(request: Request, exc: pymysql.MySQLError) -> JSONResponse:
    logger.exception("数据库错误：%s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=503,
        content={"code": 503, "message": "数据库暂时不可用，请稍后重试", "data": None},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("未处理异常：%s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"code": 500, "message": "服务器内部错误，请查看日志", "data": None},
    )


@app.middleware("http")
async def log_requests(request: Request, call_next):
    started = time.perf_counter()
    response = await call_next(request)
    duration = (time.perf_counter() - started) * 1000
    if request.url.path.startswith(API_PREFIX):
        logger.info("%s %s -> %s (%.0fms)",
                    request.method, request.url.path, response.status_code, duration)
    return response


# 生成的文件（微课 HTML 等）直接静态访问
app.mount("/uploads", StaticFiles(directory=str(UPLOAD_DIR)), name="uploads")

# 构建后的 Vue 前端由后端一起托管；开发时用 Vite 5173
if FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIST), html=True), name="frontend")
else:
    @app.get("/")
    def root():
        return {
            "message": "学习多智能体系统 API 已启动",
            "docs": "/docs",
            "health": f"{API_PREFIX}/health",
            "hint": "前端未构建：进入 frontend/ 执行 npm install && npm run build",
        }
