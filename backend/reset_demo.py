"""把演示学生恢复成干净状态（只影响该学生，不动其他数据）。

用途：答辩 / 截图前清掉测试过程中产生的资源、路径、行为与脏画像。

用法（在 backend/ 下）：
    python reset_demo.py
    python reset_demo.py --name 林小满
"""
from __future__ import annotations

import argparse
import logging

from config import GENERATED_DIR
from db import write_conn
from init_db import DEMO_PROFILE
from logging_conf import setup_logging
import store

logger = logging.getLogger("reset_demo")

SEED_MESSAGE = (
    "你好，我是画像构建助手。我们已经根据你的专业与目标建立了初始画像，"
    "接下来可以通过对话继续补充你的学习习惯与薄弱点。"
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", default="林小满")
    args = parser.parse_args()
    setup_logging()

    students = store.list_students(limit=200)
    student = next((row for row in students if row["name"] == args.name), None)
    if student is None:
        logger.error("没有找到学生「%s」，请先运行 python init_db.py", args.name)
        return 1

    student_id = int(student["id"])
    with write_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM learning_record WHERE student_id = %s", (student_id,))
            cur.execute("DELETE FROM resource WHERE student_id = %s", (student_id,))
            cur.execute("DELETE FROM learning_path WHERE student_id = %s", (student_id,))
            cur.execute("DELETE FROM assessment_report WHERE student_id = %s", (student_id,))
            cur.execute("DELETE FROM agent_run WHERE student_id = %s", (student_id,))
            cur.execute("DELETE FROM dialogue WHERE student_id = %s", (student_id,))
            cur.execute("DELETE FROM profile_dimension WHERE student_id = %s", (student_id,))
            cur.executemany(
                "INSERT INTO profile_dimension(student_id, dimension, value, confidence, source) "
                "VALUES(%s,%s,%s,%s,'seed')",
                [(student_id, dim, value, conf) for dim, value, conf in DEMO_PROFILE],
            )
            cur.execute(
                "INSERT INTO dialogue(student_id, session_id, role, content) "
                "VALUES(%s,%s,'assistant',%s)",
                (student_id, f"profile-{student_id}", SEED_MESSAGE),
            )

    removed = 0
    for path in GENERATED_DIR.glob("*.html"):
        path.unlink(missing_ok=True)
        removed += 1

    logger.info(
        "已重置演示学生 %s（id=%s）：画像 7 维、资源/路径/行为/评估/追踪清空，删除 %s 个生成文件",
        args.name, student_id, removed,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
