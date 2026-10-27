"""数据库初始化 / 增量迁移 / 演示数据。

用法（在 backend/ 下）：
    python init_db.py

它是幂等的：重复执行不会重复插入演示数据，也不会删掉已有表。
"""
from __future__ import annotations

import logging
import sys

import pymysql

from config import DB_HOST, DB_NAME, DB_PASSWORD, DB_USER, WRITE_DB_PORT
from logging_conf import setup_logging

logger = logging.getLogger("init_db")

# 旧库 → 新结构需要的列。ADD COLUMN 在 MySQL 8 没有 IF NOT EXISTS，
# 所以先查 information_schema，再决定是否 ALTER。
COLUMN_MIGRATIONS = {
    "student": {
        "email": "VARCHAR(120) NULL AFTER goal",
        "updated_at": "DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP",
    },
    "profile_dimension": {
        "confidence": "FLOAT DEFAULT 0.5 AFTER value",
        "source": "VARCHAR(20) DEFAULT 'dialogue' AFTER confidence",
    },
    "dialogue": {
        "session_id": "VARCHAR(64) NULL AFTER student_id",
        "meta": "JSON NULL AFTER content",
    },
    "resource": {
        "task_id": "VARCHAR(64) NULL AFTER student_id",
        "summary": "TEXT NULL AFTER title",
        "meta": "JSON NULL AFTER file_path",
        "agent": "VARCHAR(50) NULL AFTER meta",
        "status": "VARCHAR(20) DEFAULT 'ready' AFTER agent",
        "quality_score": "FLOAT DEFAULT 0 AFTER status",
    },
    "learning_path": {
        "rationale": "TEXT NULL AFTER title",
        "status": "VARCHAR(20) DEFAULT 'active' AFTER steps",
        "updated_at": "DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP",
    },
    "learning_record": {
        "duration_sec": "INT DEFAULT 0 AFTER score",
        "detail": "TEXT NULL AFTER duration_sec",
    },
}

DEMO_PROFILE = [
    ("知识基础", "Python 基础较扎实，能独立写脚本；数据结构与算法处于入门阶段", 0.82),
    ("认知风格", "偏好先看整体框架，再通过动手例子理解细节（视觉型 + 实践型）", 0.76),
    ("学习目标", "本学期完成一个可演示的 AI 应用，并为后端开发实习做准备", 0.9),
    ("易错点偏好", "容易混淆概念的边界，例如索引与约束、同步与异步", 0.68),
    ("学习节奏", "每周可投入 8-10 小时，偏好 25 分钟一个专注块", 0.72),
    ("兴趣方向", "AI 应用开发、后端工程、数据可视化", 0.8),
    ("实践偏好", "喜欢可运行的最小示例，其次是图解，最后是长文档", 0.78),
]


def admin_connection(database: str | None = None):
    return pymysql.connect(
        host=DB_HOST,
        port=WRITE_DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        database=database,
        charset="utf8mb4",
        autocommit=True,
        cursorclass=pymysql.cursors.DictCursor,
    )


def split_sql(script: str) -> list[str]:
    """去掉注释后按分号切分。脚本里没有存储过程，够用。"""
    lines = []
    for line in script.splitlines():
        stripped = line.strip()
        if stripped.startswith("--") or not stripped:
            continue
        lines.append(line)
    return [stmt.strip() for stmt in "\n".join(lines).split(";") if stmt.strip()]


def table_exists(cur, table: str) -> bool:
    cur.execute(
        "SELECT 1 FROM information_schema.tables "
        "WHERE table_schema = %s AND table_name = %s",
        (DB_NAME, table),
    )
    return cur.fetchone() is not None


def column_exists(cur, table: str, column: str) -> bool:
    cur.execute(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_schema = %s AND table_name = %s AND column_name = %s",
        (DB_NAME, table, column),
    )
    return cur.fetchone() is not None


def migrate(conn) -> None:
    with conn.cursor() as cur:
        for table, columns in COLUMN_MIGRATIONS.items():
            if not table_exists(cur, table):
                continue
            for column, ddl in columns.items():
                if not column_exists(cur, table, column):
                    logger.info("迁移：%s 增加列 %s", table, column)
                    cur.execute(f"ALTER TABLE `{table}` ADD COLUMN `{column}` {ddl}")

        # 旧表没有这些索引，补上（重复创建会报错，所以先查）
        index_defs = [
            ("resource", "idx_resource_student_type", "KEY idx_resource_student_type (student_id, type)"),
            ("dialogue", "idx_dialogue_student", "KEY idx_dialogue_student (student_id, created_at)"),
        ]
        for table, index, ddl in index_defs:
            if not table_exists(cur, table):
                continue
            cur.execute(
                "SELECT 1 FROM information_schema.statistics "
                "WHERE table_schema = %s AND table_name = %s AND index_name = %s",
                (DB_NAME, table, index),
            )
            if not cur.fetchone():
                cur.execute(f"ALTER TABLE `{table}` ADD {ddl}")


def seed(conn) -> None:
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM student WHERE name = %s LIMIT 1", ("林小满",))
        row = cur.fetchone()
        if row:
            logger.info("演示学生已存在，跳过种子数据")
            return

        cur.execute(
            "INSERT INTO student(name, major, age, goal, email) VALUES(%s,%s,%s,%s,%s)",
            (
                "林小满",
                "计算机科学与技术",
                20,
                "掌握 Python 后端与 AI 应用开发，完成一个可演示的多智能体学习系统",
                "xiaoman@example.edu",
            ),
        )
        student_id = cur.lastrowid

        cur.executemany(
            "INSERT INTO profile_dimension(student_id, dimension, value, confidence, source) "
            "VALUES(%s,%s,%s,%s,%s)",
            [(student_id, dim, value, conf, "seed") for dim, value, conf in DEMO_PROFILE],
        )

        cur.execute(
            "INSERT INTO dialogue(student_id, session_id, role, content) VALUES(%s,%s,%s,%s)",
            (
                student_id,
                f"profile-{student_id}",
                "assistant",
                "你好，我是画像构建助手。我们已经根据你的专业与目标建立了初始画像，"
                "接下来可以通过对话继续补充你的学习习惯与薄弱点。",
            ),
        )
        logger.info("已创建演示学生：林小满（id=%s），并写入 7 个画像维度", student_id)


def main() -> int:
    setup_logging()
    script = (__file__.replace("init_db.py", "schema.sql"))
    with open(script, encoding="utf-8") as f:
        sql = f.read()

    root = admin_connection()
    try:
        with root.cursor() as cur:
            cur.execute(
                f"CREATE DATABASE IF NOT EXISTS `{DB_NAME}` "
                "DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci"
            )
        root.select_db(DB_NAME)
        for statement in split_sql(sql):
            with root.cursor() as cur:
                cur.execute(statement)
        migrate(root)
        seed(root)
    finally:
        root.close()

    logger.info("数据库初始化完成：%s:%s/%s", DB_HOST, WRITE_DB_PORT, DB_NAME)
    return 0


if __name__ == "__main__":
    sys.exit(main())
