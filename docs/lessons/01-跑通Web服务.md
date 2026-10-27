# 第 1 课：跑通一个最小的 Web 服务

> **日期**：2026-10-12（补记于 10-15）
> **前置**：无
> **目标**：让浏览器访问一个地址，看到自己写的代码返回的内容

---

## 一、为什么先做这个

不是为了学 FastAPI，而是为了**有一个"能跑的东西"当载体**。

后面学数据库、学 LLM 调用、学前端联调，全都是往这个东西上加东西。没有载体，学的知识就是散的、记不住的。

---

## 二、核心概念：虚拟环境（venv）

**问题**：Python 的第三方库默认装在**全局**。如果项目 A 要 `fastapi 0.1`、项目 B 要 `fastapi 0.2`，全局只能留一个，另一个必然崩。

**虚拟环境**：给项目一个**独立的包目录**。就像每个项目一个专属工具箱，互不干扰。

**这不是可选项，是所有 Python 项目的标准做法。**

```bash
python -m venv .venv        # 创建
source .venv/Scripts/activate    # 激活（Git Bash）
```

**激活成功的标志**：命令行提示符前面出现 `(.venv)`。

> **为什么装在 venv 里而不是全局**——三个理由：
> 1. **版本冲突**：不同项目要同一个库的不同版本，全局只能留一个
> 2. 不污染系统 Python
> 3. 组员靠 `requirements.txt` 能重建出一模一样的环境

---

## 三、动手的完整步骤

```bash
# ① 进入项目目录
cd "C:/Users/qingq/Desktop/Learning"

# ② 建后端目录
mkdir backend && cd backend

# ③ 创建虚拟环境
python -m venv .venv

# ④ 激活（Git Bash）
source .venv/Scripts/activate

# ⑤ 装两个包
pip install fastapi uvicorn

# ⑥ 写 main.py（见下）

# ⑦ 启动
uvicorn main:app --reload --port 8001

# ⑧ 浏览器验证
#    http://127.0.0.1:8001        → 返回 JSON
#    http://127.0.0.1:8001/docs   → 自动生成的接口文档
```

**`main.py` 的内容**：

```python
from fastapi import FastAPI

app = FastAPI()

@app.get("/")
def read_root():
    return {"message": "我的第一个服务跑起来了"}
```

### 两个包的分工（别搞混）

| 包 | 作用 | 比喻 |
|---|---|---|
| **FastAPI** | Web 框架——定义"什么地址返回什么内容" | 剧本 |
| **uvicorn** | 服务器——真正监听端口、接收网络请求 | 舞台和演员 |

### 启动命令怎么读

```bash
uvicorn main:app --reload --port 8001
```

- `main:app` = **文件名:变量名** → "main.py 里的 app 这个对象"
- `--reload` = 改代码后自动重启（开发时必加）
- `--port 8001` = 用 8001 端口

---

## 四、踩到的坑

### 坑 1：`Could not import module "main"`（第一次）

**原因**：`main.py` 是**空文件**——**改了没保存**。

**教训**：VS Code 标签页上有小圆点 ● = 有改动没保存。或者开 `auto save`。

### 坑 2：`Could not import module "main"`（第二次，同一个报错）

**原因**：在 `Learning/` 下运行了命令，但 `main.py` 在 `backend/` 下。

**核心概念——当前工作目录（cwd）**：

`uvicorn main:app` 里的 `main` 是**模块名**，uvicorn 会去**当前工作目录**里找 `main.py`：

| 你在哪运行 | cwd | 结果 |
|---|---|---|
| `Learning/` | `Learning/` | ❌ 这里没有 main.py |
| `Learning/backend/` | `Learning/backend/` | ✅ 找到了 |

> **同一个报错，两个完全不同的原因。**
> **报错告诉你"哪里失败了"，但不会告诉你"为什么"。**
> 排查时要结合另一半信息：**我刚才改了什么？**

### 坑 3：端口 8000 被占用

启动时报 `address already in use`。查下来是 **`CLodopPrint32.exe`**（C-Lodop 打印服务）占了 `0.0.0.0:8000`。

**解决**：改用 **8001**。（不要去关 C-Lodop，那是别的软件在用的。）

**怎么查谁占了端口**：
```bash
netstat -ano | grep LISTENING | grep 8000    # 最后一列是 PID
tasklist //FI "PID eq <PID>"                  # 查这个 PID 是什么程序
```

**养成习惯**：启动后**读一下 uvicorn 打印的那行** `Uvicorn running on http://127.0.0.1:8001`，照着这个地址开浏览器。

---

## 五、两个值得记住的点

### 5.1 `/docs` 是自动生成的

**一行 HTML、一行 JS 都没写，FastAPI 自动生成了一份可交互的接口文档。**

它能读你代码里的信息，自动推断出接口长什么样。**点 "Try it out" 就是真的在发请求。**

项目里要求"冻结接口契约"，靠的就是它——不用写 Word 文档，把页面给前端同学，点着就能测。

### 5.2 相对路径是相对于「当前工作目录」解析的

这是第 1 课埋下的种子，第 2 课（`git add`）又遇到一次。

**以后但凡出现"文件明明在那里却说找不到"，第一反应就查当前目录。**

---

## 六、我的理解（这一节由你自己填）

- 这节课我最大的收获是：
- 我还没完全弄明白的地方是：
- 我踩到的坑 / 犯的错：

---

## 七、备忘

- 启动命令：`uvicorn main:app --reload --port 8001`
- 服务地址 `http://127.0.0.1:8001`，接口文档 `http://127.0.0.1:8001/docs`
- **本机 8000 端口被 C-Lodop 打印服务占用，固定用 8001**
- 虚拟环境：`.venv`，激活 `source .venv/Scripts/activate`
