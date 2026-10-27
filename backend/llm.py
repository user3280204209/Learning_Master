"""大模型适配层。

为什么要多这一层？
- 业务代码只关心「给我一个符合 schema 的 dict」，不关心底层是 Claude 还是模板。
- 没有 API Key 时自动走 Mock，保证项目在任何机器上都能完整演示。
- 真实调用失败时降级 Mock，并留下 `provider=mock-fallback` 和错误说明，不静默吞错。

真实模式（Claude）通过 .env 开启：
    LLM_PROVIDER=claude
    ANTHROPIC_API_KEY=...
"""
from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass
from typing import Any, Callable

import anthropic

from config import (
    LLM_MAX_ATTEMPTS,
    LLM_MAX_TOKENS,
    LLM_MODEL,
    LLM_PROVIDER,
    LLM_TIMEOUT_SECONDS,
)

logger = logging.getLogger(__name__)


@dataclass
class LLMResult:
    data: dict
    provider: str          # claude / mock / mock-fallback
    model: str
    duration_ms: int = 0
    note: str = ""


def _extract_json(text: str) -> str:
    """模型偶尔会包一层 ```json 或寒暄，这里做一次宽容提取。"""
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fence:
        text = fence.group(1).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start : end + 1]
    return text


def _missing_required(data: Any, schema: dict) -> list[str]:
    """只校验顶层 required，足够拦住「模型少给字段」的常见问题。"""
    if not isinstance(data, dict):
        return ["<root>"]
    return [key for key in schema.get("required", []) if key not in data]


class LLMService:
    def __init__(self) -> None:
        self.provider = LLM_PROVIDER
        self.model = LLM_MODEL
        self.enabled = self.provider == "claude"
        self.client: anthropic.Anthropic | None = None
        if self.enabled:
            try:
                self.client = anthropic.Anthropic(
                    max_retries=2,
                    timeout=LLM_TIMEOUT_SECONDS,
                )
                logger.info("LLM 已启用：provider=claude model=%s", self.model)
            except Exception as exc:  # 凭证缺失等
                self.enabled = False
                logger.error("LLM 初始化失败，降级为 mock：%s", exc)
        else:
            logger.info("LLM 使用 mock 模板引擎（无需 API Key，可离线演示）")

    @property
    def mode(self) -> str:
        return "claude" if self.enabled else "mock"

    def info(self) -> dict:
        return {
            "provider": self.mode,
            "model": self.model if self.enabled else "template-engine",
            "structured_output": self.enabled,
        }

    def complete_json(
        self,
        *,
        system: str,
        prompt: str,
        schema: dict,
        mock_factory: Callable[[], dict],
        agent: str = "agent",
    ) -> LLMResult:
        """返回结构化 dict。claude 失败会自动重试，最终降级 mock。"""
        started = time.perf_counter()

        if not self.enabled or self.client is None:
            data = mock_factory()
            return LLMResult(
                data=data,
                provider="mock",
                model="template-engine",
                duration_ms=int((time.perf_counter() - started) * 1000),
            )

        last_error: Exception | None = None
        for attempt in range(1, LLM_MAX_ATTEMPTS + 1):
            try:
                data = self._call_claude(system=system, prompt=prompt, schema=schema)
                missing = _missing_required(data, schema)
                if missing:
                    raise ValueError(f"模型输出缺少字段：{missing}")
                return LLMResult(
                    data=data,
                    provider="claude",
                    model=self.model,
                    duration_ms=int((time.perf_counter() - started) * 1000),
                )
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "Agent %s 调用 Claude 失败（第 %s/%s 次）：%s",
                    agent, attempt, LLM_MAX_ATTEMPTS, exc,
                )
                if attempt < LLM_MAX_ATTEMPTS:
                    time.sleep(0.8 * attempt)

        logger.error("Agent %s 最终降级 mock：%s", agent, last_error)
        return LLMResult(
            data=mock_factory(),
            provider="mock-fallback",
            model="template-engine",
            duration_ms=int((time.perf_counter() - started) * 1000),
            note=str(last_error)[:300] if last_error else "",
        )

    def _call_claude(self, *, system: str, prompt: str, schema: dict) -> dict:
        assert self.client is not None
        params: dict[str, Any] = {
            "model": self.model,
            "max_tokens": LLM_MAX_TOKENS,
            "system": system,
            "messages": [{"role": "user", "content": prompt}],
        }

        # 结构化输出：用 output_config.format 约束 JSON Schema。
        # 当前安装的 SDK 版本尚未暴露该参数，因此通过 extra_body 透传；
        # 如果服务端/模型不支持，会退回到「提示词要求 JSON」的普通调用。
        try:
            response = self.client.messages.create(
                **params,
                extra_body={
                    "output_config": {
                        "format": {"type": "json_schema", "schema": schema}
                    }
                },
            )
        except anthropic.BadRequestError as exc:
            logger.info("结构化输出不可用，退回提示词 JSON：%s", exc)
            fallback_params = {
                **params,
                "system": system
                + "\n\n你只能输出一个合法 JSON 对象，不要 Markdown 代码块，不要寒暄。",
            }
            response = self.client.messages.create(**fallback_params)

        text = "".join(
            block.text for block in response.content if getattr(block, "type", "") == "text"
        )
        return json.loads(_extract_json(text))


llm_service = LLMService()
