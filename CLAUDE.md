# 项目说明

软件工程课程项目：**个性化资源生成与学习多智能体系统**。
技术栈：Python + FastAPI 后端、Vue 前端、SQLite 起步。

---

## 与 Claude 协作的约定

- **始终用中文回复。**
- **这是一个学习项目，不是交付项目。** 用户是大三学生，目标是提升自身工程能力以便实习，
  不是尽快做完。请以教学方式协作：
  - 讲原理、给方向、做 review，而**不是直接代写实现**
  - 每个模块先让用户写设计草稿，再点评
  - 调试时要求用户先提出自己的假设
  - 样板代码可以直接给，但优先让用户自己写
  - 不要建议"先系统学完再做"——以项目为纲，缺什么补什么
- **每节课的内容写成 `docs/lessons/NN-课程名.md`**，聊天里只回文件名和本次的问题。
  文件名用两位数字前缀保证排序；文件末尾保留一节「我的理解」给用户自己填。

---

## 环境备忘

- 后端代码在 `backend/`，启动命令（在 `backend/` 下）：
  ```
  python init_db.py                         # 首次/表结构变更后
  python -m uvicorn main:app --reload --port 8001
  python smoke_test.py                      # 只读冒烟测试
  ```
- 前端在 `frontend/`：
  ```
  npm install
  npm run build      # 产物由 8001 托管，之后只需开后端
  npm run dev        # 开发模式，5173，代理 /api 和 /uploads 到 8001
  ```
- 默认 `LLM_PROVIDER=mock`（无需 API Key）；`backend/.env` 可切换 Claude。
- **本机 8000 端口被 C-Lodop 打印服务占用**，所以项目固定用 **8001**。
- 服务地址 `http://127.0.0.1:8001`，接口文档 `http://127.0.0.1:8001/docs`
- 演示数据重置：`cd backend && python reset_demo.py`（只影响「林小满」）。

---

## 目录结构

```
Learning/
├── backend/           后端代码
│   ├── main.py        应用入口 / 统一异常 / 静态托管
│   ├── db.py          连接池 + 主从读写分离
│   ├── store.py       SQL 与持久化
│   ├── llm.py         Claude / Mock 适配层
│   ├── orchestrator.py 多智能体总控
│   ├── agents/        8 个智能体角色
│   ├── routers/       REST 接口
│   ├── schema.sql     8 张表
│   └── .venv/         （不进版本控制）
├── frontend/          Vue 3 + Vite 工作台
│   ├── src/components/ 6 个页面 + 资源弹窗
│   └── dist/          build 产物（由后端托管）
├── docs/              项目文档
│   ├── lessons/       课程笔记
│   └── screenshots/   界面截图
├── logs/              运行日志
├── README.md          运行手册 / 架构 / 演示流程
├── .gitignore
└── CLAUDE.md
```
