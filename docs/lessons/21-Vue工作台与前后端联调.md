# 第 21 课：Vue 工作台与前后端联调

> **日期**：2026-10-27
> **目标**：把后端能力变成一个可演示、可操作、有反馈的工作台，而不是一堆接口。
> **对应代码**：`frontend/src/App.vue`、`frontend/src/api.js`、`frontend/src/components/`

---

## 一、页面与状态怎么分？

工作台有 6 个页面：

| 页面 | 主要数据 | 主要动作 |
|---|---|---|
| 学习总览 | 学生、画像、资源数、路径进度、Agent 轨迹 | 跳转、打开资源 |
| 画像对话 | 对话历史、7 维画像 | 发送一句话、更新画像 |
| 资源工坊 | 资源列表、生成结果、资源详情 | 生成、筛选、做题、看视频 |
| 学习路径 | 路径步骤、资源 | 生成、标记完成 |
| 智能辅导 | 辅导历史、关联资源 | 提问 |
| 学习评估 | 行为记录、评估报告 | 记录行为、生成报告 |

`App.vue` 只负责：

- 当前学生、当前页面；
- 六个页面的公共数据（画像、资源、路径、记录、报告）；
- 全局 toast；
- 调用后的刷新；
- 深链接（hash）。

具体交互放在各组件里。这样 `App.vue` 不会变成一个 2000 行的怪物。

---

## 二、统一请求封装

`src/api.js`：

```js
async function request(path, { method = 'GET', body, params } = {}) {
  const url = new URL(BASE + path, window.location.origin)
  ...
  const payload = await response.json()
  if (!response.ok || payload.code !== 0) {
    throw new Error(payload.message || `请求失败（HTTP ${response.status}）`)
  }
  return payload.data
}
```

好处：

- 组件里只关心 `data`，不用每次判断 `code`；
- 错误统一抛出，组件用 `try/catch` 转成 toast；
- GET 参数、POST body 统一处理；
- 后端返回 `{code, message, data}`，前端不需要猜形状。

---

## 三、加载、错误、空状态

三个状态必须都设计：

1. **加载**：骨架屏 / spinner / “6 个智能体并行工作”；
2. **错误**：toast 显示后端 message，不吞掉；
3. **空状态**：告诉用户下一步做什么，而不是一片空白。

例如资源工坊没有资源时：

```text
资源工坊还是空的
输入一个主题，让 6 个智能体并行产出讲解、导图、练习、阅读、代码和微课。
[开始生成]
```

> **不要伪造进度**。生成接口是同步的，前端无法知道“第 3 个 Agent 已经完成”。所以只显示“并行工作”，不画一个假的 60%。

---

## 四、Hash 深链接

项目没有引入 Vue Router，但需要“刷新后还能回到某个页面”和“截图某个资源”。用 hash：

```js
function syncFromHash() {
  const [key, id] = location.hash.replace('#', '').split('/')
  if (visibleKeys.has(key)) activeTab.value = key
  if (key === 'resources' && id) pendingResourceId.value = Number(id)
}
```

支持：

- `#dashboard`
- `#profile`
- `#resources`
- `#resources/25`（直接打开资源详情）

这个设计也让自动化截图变得容易：Chrome 直接访问 `/#resources/25` 就能截到弹窗。

---

## 五、几个渲染细节

### 1. Markdown

用 `marked` 解析、`DOMPurify` 清洗：

```js
const raw = marked.parse(props.content)
return DOMPurify.sanitize(raw)
```

为什么不能直接 `v-html`？因为资源内容最终可能来自大模型，直接渲染有 XSS 风险。清洗后再渲染是底线。

### 2. 思维导图

后端返回两层树：

```json
[
  { "label": "核心概念", "children": [{ "label": "输入 / 输出" }] }
]
```

前端用递归结构 + CSS 连接线渲染。没有引入图形库，因为两层树用 CSS 足够，依赖越少越稳。

### 3. 练习

单选题用 `v-model` 绑定选项，提交后：

- 正确选项标绿，选错的标红；
- 显示参考答案与解析；
- 把得分提交给后端 `learning_record`。

简答题无法自动判分，只展示参考答案，并在界面明确说明“按单选计分”。

### 4. 微课

后端生成的是独立 HTML 文件，前端用 iframe 加载：

```html
<iframe :src="`/uploads/${detail.file_path}`"></iframe>
```

这样视频/动画的播放逻辑与 Vue 应用解耦，后端也能单独打开这个文件。

---

## 六、开发与生产两套跑法

开发：

```bash
cd frontend
npm run dev
```

Vite 监听 5173，`/api` 和 `/uploads` 代理到 8001：

```js
proxy: {
  '/api': 'http://127.0.0.1:8001',
  '/uploads': 'http://127.0.0.1:8001',
}
```

生产 / 演示：

```bash
npm run build
```

产物在 `frontend/dist`，FastAPI 启动时如果检测到该目录，就挂到 `/`：

```python
if FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIST), html=True))
```

所以最终只需要启动一个 8001，前端、接口、上传文件都能访问。

> 注意路由顺序：API 路由先注册，静态站点最后挂载。否则 `/api/...` 会被静态文件吞掉。

---

## 七、联调时踩过的坑

1. **中文 JSON 在 Windows 终端乱码**：不是数据坏了，是控制台编码。Python 端 `sys.stdout.reconfigure(encoding="utf-8")`，检查时用 `PYTHONIOENCODING=utf-8`。
2. **路径生成返回空对象**：后端主从延迟，前端看到 200 但 `data={}`。修复在后端，不是前端“再请求一次”。
3. **画像页混入辅导对话**：`dialogue` 表用 `session_id` 区分场景，画像页只查 `profile-{id}`，辅导页只查 `tutor-{id}`。
4. **辅导历史刷新后丢失**：把结构化回答写进 `dialogue.meta`，页面加载时恢复要点、类比、下一步。
5. **资源详情太长**：列表接口不返回 `content`，点开后再请求详情，首屏更轻。

---

## 八、验收方式

- `npm run build` 成功；
- 8001 根路径返回工作台；
- 六个页面都能加载真实数据；
- 资源弹窗能渲染文档、导图、练习、代码、微课；
- 提交练习后，评估页出现答题记录；
- 刷新 `#resources/25` 仍能打开对应弹窗。

截图见 `docs/screenshots/`。

---

## 九、练习

1. 为什么 `App.vue` 不直接写所有请求，而要拆组件？
2. 如果资源生成改成后台任务，前端需要增加哪些状态和接口？
3. 为什么 Mindmap 用 CSS 而不是引入图形库？什么情况下应该换库？
4. 设计一个「生成中取消」的交互，后端需要支持什么？

---

## 十、我的理解

- 我最大的收获：
- 我对“加载 / 错误 / 空状态”的新理解：
- 我认为前端最容易忽略的联调细节：
- 还没弄明白的：
