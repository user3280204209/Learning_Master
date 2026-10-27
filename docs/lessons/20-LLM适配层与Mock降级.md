# 第 20 课：LLM 适配层与 Mock 降级

> **日期**：2026-10-27
> **目标**：让系统在「有 Key / 没 Key / 调用失败」三种状态下都能跑，并且让失败可见。
> **对应代码**：`backend/llm.py`、`backend/agents/base.py`、`backend/.env.example`

---

## 一、大模型输出的不确定性

传统后端的函数是确定的：`add(1, 2)` 永远返回 3。LLM 不是：

- 可能返回 Markdown 代码块包着的 JSON；
- 可能少一个字段；
- 可能超时、限流、服务过载；
- 可能理解错主题，生成空泛内容。

如果业务代码直接 `json.loads(response.content[0].text)`，系统会非常脆。所以需要一层适配：

```text
业务 Agent
   │  只要「符合 schema 的 dict」
   ▼
LLMService.complete_json()
   ├── Claude：结构化输出 + 重试 + 校验
   └── Mock：确定性模板
```

业务 Agent 不知道底层是 Claude 还是模板，这就是**依赖倒置**：业务依赖抽象，不依赖具体模型。

---

## 二、统一接口

```python
def complete_json(
    self,
    *,
    system: str,
    prompt: str,
    schema: dict,
    mock_factory: Callable[[], dict],
    agent: str = "agent",
) -> LLMResult:
```

四个关键参数：

| 参数 | 作用 |
|---|---|
| `system` | 角色设定（“你是出题智能体……”） |
| `prompt` | 本次任务 + 学生画像 + 资源上下文 |
| `schema` | 输出契约 |
| `mock_factory` | 没有模型 / 模型失败时，如何生成一份结构完整的兜底结果 |

返回 `LLMResult`：

```python
@dataclass
class LLMResult:
    data: dict
    provider: str      # claude / mock / mock-fallback
    model: str
    duration_ms: int
    note: str
```

`provider` 会一路写进资源 `meta` 和 `agent_run`，前端能看到“这是真实模型生成的”还是“模板降级”。

---

## 三、结构化输出与 SDK 版本差异

理想调用：

```python
client.messages.create(
    model="claude-opus-4-8",
    max_tokens=8192,
    system=system,
    messages=[{"role": "user", "content": prompt}],
    output_config={
        "format": {"type": "json_schema", "schema": schema}
    },
)
```

但当前安装的 `anthropic==0.75.0` 的 `Messages.create` 签名里没有 `output_config`。代码通过 `extra_body` 透传：

```python
response = self.client.messages.create(
    **params,
    extra_body={
        "output_config": {
            "format": {"type": "json_schema", "schema": schema}
        }
    },
)
```

如果服务端或模型不支持，会捕获 `BadRequestError`，退回普通调用，并在 system 里追加：

```text
你只能输出一个合法 JSON 对象，不要 Markdown 代码块，不要寒暄。
```

然后在客户端提取第一个 `{` 到最后一个 `}`，再 `json.loads`。

> **知识点**：SDK 的类型签名可能落后于 API。先看签名，再看文档；不要因为 IDE 报错就以为 API 不支持。

---

## 四、重试与校验

`complete_json` 最多尝试 `LLM_MAX_ATTEMPTS` 次（默认 3）：

- SDK 层：`max_retries=2`，处理 429 / 5xx / 连接错误；
- 业务层：校验 JSON、校验必填字段，失败重试；
- 最终仍失败：返回 Mock，`provider="mock-fallback"`，`note` 记录最后一次错误。

```python
missing = _missing_required(data, schema)
if missing:
    raise ValueError(f"模型输出缺少字段：{missing}")
```

注意：**只校验顶层 required**，不递归校验嵌套结构。原因是：
- 大多数问题出在顶层缺字段；
- 递归校验代码复杂，且会与不同模型的 schema 支持程度打架；
- 真正的嵌套校验交给各 Agent 的 `to_output()`，缺字段时用 `.get()` 兜底。

---

## 五、Mock 不是“随便编一段”

Mock 的设计目标不是“看起来像”，而是“结构完整、可演示、可降级”：

1. **严格匹配 Schema**：`questions`、`nodes`、`scenes` 一个不少；
2. **读取画像**：内容里会引用知识基础、认知风格、易错点；
3. **确定性**：同样的输入得到同样的结构，便于测试和截图；
4. **不冒充事实**：模板会写“先建立框架”“用对比表区分概念”，而不是编造具体 API 参数；
5. **可替换**：换成真实模型后，前端和下游代码零改动。

这也带来限制：Mock 内容偏“学习方法论”，不是真正的课程知识。**要用于真实学习，应该配置 Claude 或接入课程知识库。**

---

## 六、成本与安全：为什么默认 Mock

- 调用 API 会产生费用，用户没有明确授权时不应该静默消耗；
- 没有网络 / 没有 Key 的机器也要能跑；
- 答辩现场网络不稳定，Mock 保证演示不中断；
- Mock 模式下的 Agent 编排、数据库、前端、评估闭环全部真实执行，只有“内容生成”换成模板。

启用真实模型是显式动作：

```env
LLM_PROVIDER=claude
ANTHROPIC_API_KEY=sk-ant-...
```

如果 Key 缺失或初始化失败，`LLMService` 会降级 Mock 并打日志，不会让应用起不来。

---

## 七、如何判断当前用的是哪种模式？

三个地方：

1. `/api/health`：

```json
"llm": { "provider": "mock", "model": "template-engine", "structured_output": false }
```

2. 资源 `meta`：

```json
{ "provider": "mock", "model": "template-engine" }
```

3. `agent_run` 表 / 前端时间线：每个 Agent 的 `model` 字段。

---

## 八、练习

1. 如果真实模型返回的 JSON 被 ```json 包裹，`_extract_json` 如何工作？自己构造三个样例测试。
2. 为什么要在 `LLMResult` 里保留 `note`？只记录日志够不够？
3. 设计一个“只对失败 Agent 重试一次真实模型”的策略，需要改 `BaseAgent` 还是 `Orchestrator`？
4. 如果真实模型总是把 `questions` 生成成字符串而不是数组，你会改 Schema、改 Prompt，还是加后处理？各自代价是什么？

---

## 九、我的理解

- 我最大的收获：
- 我认为 Mock 最容易被误解的地方：
- 如果接入真实模型，我最担心：
- 还没弄明白的：
