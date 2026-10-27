"""集中配置：环境变量 / .env / 默认值。

原则：代码里不出现密码和模型名，所有可变项从一个地方读。
"""
from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent


def _load_dotenv(path: Path) -> None:
    """极简 .env 解析，避免为一个小功能引入额外依赖。"""
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        # 已经存在的环境变量优先，方便命令行临时覆盖
        os.environ.setdefault(key, value)


_load_dotenv(BASE_DIR / ".env")


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


# ---------- 数据库 ----------
DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "root123456")
DB_NAME = os.getenv("DB_NAME", "learning")
DB_CHARSET = os.getenv("DB_CHARSET", "utf8mb4")

WRITE_DB_PORT = _int_env("WRITE_DB_PORT", 3306)
READ_DB_PORT = _int_env("READ_DB_PORT", 3307)
DB_POOL_SIZE = _int_env("DB_POOL_SIZE", 8)
DB_CONNECT_TIMEOUT = _int_env("DB_CONNECT_TIMEOUT", 3)

# ---------- 大模型 ----------
# mock：不调用外部 API，用确定性模板生成，保证离线可演示
# claude：调用 Anthropic API（需要 ANTHROPIC_API_KEY）
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "mock").lower()
LLM_MODEL = os.getenv("LLM_MODEL", "claude-opus-4-8")
LLM_MAX_TOKENS = _int_env("LLM_MAX_TOKENS", 8192)
LLM_TIMEOUT_SECONDS = _int_env("LLM_TIMEOUT_SECONDS", 60)
LLM_MAX_ATTEMPTS = _int_env("LLM_MAX_ATTEMPTS", 3)

# ---------- 应用 ----------
API_PREFIX = "/api"
UPLOAD_DIR = BASE_DIR / "uploads"
GENERATED_DIR = UPLOAD_DIR / "generated"
LOG_DIR = BASE_DIR.parent / "logs"
FRONTEND_DIST = BASE_DIR.parent / "frontend" / "dist"

for directory in (UPLOAD_DIR, GENERATED_DIR, LOG_DIR):
    directory.mkdir(parents=True, exist_ok=True)
