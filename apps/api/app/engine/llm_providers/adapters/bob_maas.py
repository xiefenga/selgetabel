"""北京银行 (BOB) MaaS Provider（OpenAI 兼容格式）"""

import json
import logging
from typing import Generator, Optional

import httpx

from app.engine.llm_providers.base import LLMProvider
from app.engine.llm_providers.types import LLMRequest, LLMResponse, LLMStreamChunk

logger = logging.getLogger(__name__)


class BobMaasProvider(LLMProvider):
    """
    北京银行 (Bank of Beijing) MaaS 平台适配器。

    接口为 OpenAI 兼容格式，通过 ``?body_format=openai`` 指定。

    URL 结构: {base_url}/{endpoint_suffix}?body_format=openai
    - base_url: 例如 http://maasapp.aip.bj.bob.test:8080/apis/ais
    - endpoint_suffix: 从 LLMModel.defaults.endpoint_suffix 读取，fallback 到 model_id

    配置示例（在 LLMModel.defaults 中）:
        {
            "endpoint_suffix": "qwen3-30b-a",
            "temperature": 0.7
        }
    """

    def __init__(self, api_key: str, base_url: str):
        if not base_url:
            raise ValueError("BobMaasProvider 需要配置 base_url")
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")

    def _build_url(self, request: LLMRequest) -> str:
        """
        构建请求 URL。

        endpoint_suffix 优先从 request.extra_params 读取，
        如果未配置则 fallback 到 request.model_id。
        """
        endpoint_suffix = request.extra_params.get("endpoint_suffix") if request.extra_params else None
        if not endpoint_suffix:
            endpoint_suffix = request.model_id
        return f"{self.base_url}/{endpoint_suffix}?body_format=openai"

    def _build_headers(self) -> dict:
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

    def _build_body(self, request: LLMRequest, *, stream: bool = False) -> dict:
        body: dict = {
            "model": request.model_id,
            "messages": request.messages,
        }
        if request.temperature is not None:
            body["temperature"] = request.temperature
        if request.max_tokens is not None:
            body["max_tokens"] = request.max_tokens
        if request.tools:
            body["tools"] = request.tools
        if stream:
            body["stream"] = True
        return body

    @staticmethod
    def _strip_think(text: str) -> str:
        """去除 qwen3 模型返回的 <think>...</think> 推理块。"""
        import re
        return re.sub(r"<think>[\s\S]*?</think>\s*", "", text).strip()

    # ── 非流式 ───────────────────────────────────────────

    def complete(self, request: LLMRequest) -> LLMResponse:
        url = self._build_url(request)
        headers = self._build_headers()
        body = self._build_body(request)

        logger.info("[BOB-MaaS] complete 请求: url=%s model=%s messages=%d", url, request.model_id, len(request.messages))
        logger.debug("[BOB-MaaS] complete body: %s", json.dumps(body, ensure_ascii=False))

        try:
            with httpx.Client(timeout=120) as client:
                resp = client.post(url, headers=headers, json=body)
                logger.info("[BOB-MaaS] complete 响应: status=%d", resp.status_code)
                if resp.status_code != 200:
                    logger.error("[BOB-MaaS] complete 异常响应: status=%d body=%s", resp.status_code, resp.text)
                resp.raise_for_status()
        except httpx.ConnectError as e:
            logger.error("[BOB-MaaS] complete 连接失败: %s", e)
            raise
        except httpx.TimeoutException as e:
            logger.error("[BOB-MaaS] complete 超时: %s", e)
            raise

        data = resp.json()
        content = data["choices"][0]["message"]["content"] or ""
        content = self._strip_think(content)
        usage = data.get("usage")

        logger.info("[BOB-MaaS] complete 完成: content_len=%d usage=%s", len(content), usage)

        return LLMResponse(
            content=content.strip(),
            raw=data,
            usage=usage,
        )

    # ── 流式 ─────────────────────────────────────────────

    def stream(self, request: LLMRequest) -> Generator[LLMStreamChunk, None, None]:
        url = self._build_url(request)
        headers = self._build_headers()
        body = self._build_body(request, stream=True)

        logger.info("[BOB-MaaS] stream 请求: url=%s model=%s messages=%d", url, request.model_id, len(request.messages))
        logger.debug("[BOB-MaaS] stream body: %s", json.dumps(body, ensure_ascii=False))

        full_content = ""
        chunk_count = 0
        try:
            with httpx.Client(timeout=120) as client:
                with client.stream("POST", url, headers=headers, json=body) as resp:
                    logger.info("[BOB-MaaS] stream 连接建立: status=%d", resp.status_code)
                    if resp.status_code != 200:
                        error_body = resp.read().decode()
                        logger.error("[BOB-MaaS] stream 异常响应: status=%d body=%s", resp.status_code, error_body)
                    resp.raise_for_status()
                    for line in resp.iter_lines():
                        if not line or not line.startswith("data: "):
                            continue
                        payload = line[len("data: "):]
                        if payload.strip() == "[DONE]":
                            logger.info("[BOB-MaaS] stream 完成: chunks=%d content_len=%d", chunk_count, len(full_content))
                            break
                        try:
                            chunk = json.loads(payload)
                        except json.JSONDecodeError:
                            logger.warning("[BOB-MaaS] stream JSON 解析失败: %s", payload[:200])
                            continue
                        choices = chunk.get("choices", [])
                        if not choices:
                            continue
                        delta_content = choices[0].get("delta", {}).get("content")
                        if delta_content:
                            full_content += delta_content
                            chunk_count += 1
                            yield LLMStreamChunk(
                                delta=delta_content,
                                full_content=full_content,
                                raw=chunk,
                            )
        except httpx.ConnectError as e:
            logger.error("[BOB-MaaS] stream 连接失败: %s", e)
            raise
        except httpx.TimeoutException as e:
            logger.error("[BOB-MaaS] stream 超时 (已接收 %d chunks): %s", chunk_count, e)
            raise
