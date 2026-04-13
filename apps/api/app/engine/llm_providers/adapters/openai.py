"""OpenAI / OpenAI 兼容 Provider"""

from typing import Generator, Optional

from openai import OpenAI

from app.engine.llm_providers.base import LLMProvider
from app.engine.llm_providers.types import LLMRequest, LLMResponse, LLMStreamChunk


class OpenAIProvider(LLMProvider):
    """OpenAI / OpenAI 兼容适配器"""

    def __init__(self, api_key: str, base_url: Optional[str] = None):
        client_kwargs = {"api_key": api_key}
        if base_url:
            client_kwargs["base_url"] = base_url
        self.client = OpenAI(**client_kwargs)

    def complete(self, request: LLMRequest) -> LLMResponse:
        extra_params = request.extra_params or {}
        extra_body = extra_params.get("extra_body") or {"enable_thinking": False}
        extra_headers = extra_params.get("extra_headers")

        params = {
            "model": request.model_id,
            "messages": request.messages,
            "temperature": request.temperature,
            "extra_body": extra_body,
        }
        if request.max_tokens is not None:
            params["max_tokens"] = request.max_tokens
        if request.response_format:
            params["response_format"] = request.response_format
        if extra_headers:
            params["extra_headers"] = extra_headers
        if request.tools:
            params["tools"] = request.tools

        response = self.client.chat.completions.create(**params)
        message = response.choices[0].message
        content = message.content or ""

        # 检查是否发生了工具调用
        raw_tool_calls = getattr(message, "tool_calls", None) or []
        tool_calls = []
        for tc in raw_tool_calls:
            # tc 是 ChatCompletionMessageToolCall 类型
            func = getattr(tc, "function", None)
            if func:
                tool_calls.append({
                    "name": func.name or "",
                    "args": func.arguments or "{}",
                    "id": tc.id or "",
                })

        return LLMResponse(
            content=content.strip(),
            raw=response,
            usage=getattr(response, "usage", None),
            tool_calls=tool_calls if tool_calls else None,
        )

    def stream(self, request: LLMRequest) -> Generator[LLMStreamChunk, None, None]:
        extra_params = request.extra_params or {}
        extra_body = extra_params.get("extra_body") or {"enable_thinking": False}
        extra_headers = extra_params.get("extra_headers")

        params = {
            "model": request.model_id,
            "messages": request.messages,
            "temperature": request.temperature,
            "stream": True,
            "extra_body": extra_body,
        }
        if request.max_tokens is not None:
            params["max_tokens"] = request.max_tokens
        if request.response_format:
            params["response_format"] = request.response_format
        if extra_headers:
            params["extra_headers"] = extra_headers

        response = self.client.chat.completions.create(**params)

        full_content = ""
        for chunk in response:
            if chunk.choices and chunk.choices[0].delta.content:
                delta = chunk.choices[0].delta.content
                full_content += delta
                yield LLMStreamChunk(delta=delta, full_content=full_content, raw=chunk)
