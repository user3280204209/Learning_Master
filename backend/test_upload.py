# -*- coding: utf-8 -*-
"""
分片上传 · 一次性完整演示脚本（给老师演示用）
每次运行都会生成唯一的 file_id 和合并文件名，可反复演示、互不冲突。

后端已运行: http://127.0.0.1:8001  (接口前缀 /api)
接口:
  POST /api/upload/chunk     收一片分片   (file_id, chunk_index, file)
  POST /api/upload/complete  后台重组     (file_id, total_chunks, filename)
"""
import os, time, hashlib, requests

BASE = "http://127.0.0.1:8001"
CHUNK = 1 * 1024 * 1024                      # 每片 1MB
stamp = time.strftime("%H%M%S")
FILE_ID = f"demo-{stamp}"                    # 本次上传唯一标识
SRC = "uploads/test_3mb.bin"                 # 源文件（不存在时自动生成 3MB）
OUT = f"merged-{stamp}.bin"                  # 重组后的最终文件名（唯一）

# 仓库不提交 uploads/，所以首次运行自动生成一个随机测试文件
if not os.path.exists(SRC):
    os.makedirs(os.path.dirname(SRC), exist_ok=True)
    with open(SRC, "wb") as f:
        f.write(os.urandom(3 * 1024 * 1024))

with open(SRC, "rb") as f:
    data = f.read()
total = (len(data) + CHUNK - 1) // CHUNK
print(f"[1] 源文件: {SRC}, 大小 {len(data)} 字节, 切 {total} 片, file_id={FILE_ID}")

# ① 逐片上传
for i in range(0, len(data), CHUNK):
    idx = i // CHUNK
    resp = requests.post(f"{BASE}/api/upload/chunk",
                         data={"file_id": FILE_ID, "chunk_index": str(idx)},
                         files={"file": (f"part{idx}.bin", data[i:i+CHUNK])})
    print(f"    [2] 上传片{idx}: {resp.json()}")

# ② 后台重组
resp = requests.post(f"{BASE}/api/upload/complete",
                     data={"file_id": FILE_ID, "total_chunks": str(total),
                           "filename": OUT})
result = resp.json()
print(f"[3] 重组结果: {result['data']['filename']}, 大小 {result['data']['size']} 字节")
print(f"    访问地址: {BASE}{result['data']['url']}")

# ③ 字节一致性校验
down = requests.get(f"{BASE}{result['data']['url']}")
ok = hashlib.md5(data).hexdigest() == hashlib.md5(down.content).hexdigest()
print(f"[4] 原始 vs 重组 md5 一致性: {ok}")
print("[5] 分片临时目录已由后端自动清理(可在文件管理器查看)")
