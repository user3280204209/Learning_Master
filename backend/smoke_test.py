"""只读冒烟测试：验证后端关键接口与演示数据是否齐全。

用法（先启动 8001）：
    python smoke_test.py
"""
from __future__ import annotations

import os
import sys

import httpx

BASE = os.getenv("API_BASE", "http://127.0.0.1:8001/api")


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)
    print(f"[OK] {message}")


def main() -> int:
    with httpx.Client(timeout=20) as client:
        health = client.get(f"{BASE}/health").json()
        check(health["code"] == 0, "健康检查通过")
        check(health["data"]["database"]["master"]["ok"], "主库 3306 可用")
        replica_ok = health["data"]["database"]["replica"]["ok"]
        if replica_ok:
            print("[OK] 从库 3307 可用")
        else:
            print("[INFO] 从库不可用，读请求会降级主库（符合设计）")

        route = client.get(f"{BASE}/debug/db-route").json()["data"]
        check(route["write_port"] == 3306, f"写连接走主库（{route['write_port']}）")
        if replica_ok:
            check(route["read_port"] == 3307, f"读连接走从库（{route['read_port']}）")
        else:
            check(route["read_port"] == 3306, "从库不可用时读连接降级主库（3306）")

        meta = client.get(f"{BASE}/meta").json()["data"]
        check(len(meta["dimensions"]) >= 6, f"画像维度 {len(meta['dimensions'])} 个（≥6）")
        check(len(meta["resource_types"]) >= 5, f"资源类型 {len(meta['resource_types'])} 种（≥5）")

        students = client.get(f"{BASE}/students").json()["data"]["students"]
        check(bool(students), "学生列表非空")
        student_id = students[0]["id"]

        profile = client.get(f"{BASE}/profile/{student_id}").json()["data"]
        check(len(profile["dimensions"]) >= 6, "画像接口返回 ≥6 个维度")

        resources = client.get(
            f"{BASE}/resources", params={"student_id": student_id}
        ).json()["data"]["resources"]
        print(f"[INFO] 当前学生 {students[0]['name']} 有 {len(resources)} 份资源")

        path = client.get(f"{BASE}/paths/{student_id}")
        if path.status_code == 200:
            steps = path.json()["data"].get("steps", [])
            check(bool(steps), f"学习路径 {len(steps)} 个步骤")
        else:
            print("[INFO] 还没有学习路径（可先做资源生成）")

        report = client.get(f"{BASE}/assessment/latest/{student_id}")
        if report.status_code == 200:
            check(report.json()["data"]["overall_score"] > 0, "评估报告可读取")
        else:
            print("[INFO] 还没有评估报告")

    print("\n冒烟测试通过。打开 http://127.0.0.1:8001/ 查看工作台。")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"[FAIL] {exc}")
        sys.exit(1)
