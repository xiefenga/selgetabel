"""Provider Registry → LangChain ChatModel 适配层"""

from typing import Any, Dict, Optional, Sequence, Union, Callable, Annotated
from uuid import UUID

from langchain.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage, AIMessage, HumanMessage, SystemMessage
from langchain_core.outputs import ChatResult, ChatGeneration
from langchain_core.runnables import Runnable
from langchain_core.tools import BaseTool

from app.engine.llm_providers import ProviderRegistry
from app.engine.llm_providers.types import LLMStageConfig, LLMRequest


def _convert_tool_to_openai_schema(t: Union[BaseTool, dict, type, Callable, Any]) -> Dict[str, Any]:
    """将工具转换为 OpenAI function calling 格式"""
    if isinstance(t, dict):
        return t
    if isinstance(t, BaseTool):
        return {
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description,
                "parameters": t.get_input_jsonschema(),
            },
        }
    if callable(t):
        # 简单包装
        return {
            "type": "function",
            "function": {
                "name": getattr(t, "__name__", "unnamed"),
                "description": getattr(t, "__doc__", ""),
                "parameters": {"type": "object", "properties": {}, "required": []},
            },
        }
    # assume it's a TypedDict or Pydantic model
    return t


class RegistryChatModel(BaseChatModel):
    """将 Provider Registry 适配为 LangChain BaseChatModel"""

    stage_config: LLMStageConfig

    # LangChain 1.x 要求类属性声明
    _bound_tools: Optional[list] = None
    _tool_choice: Optional[str] = None

    @property
    def _llm_type(self) -> str:
        return f"registry_{self.stage_config.provider.type}"

    @property
    def _identifying_params(self) -> dict:
        return {"model": self.stage_config.model.model_id}

    def bind_tools(
        self,
        tools: Sequence[Union[dict, type, Callable, BaseTool]],
        *,
        tool_choice: Optional[str] = None,
        **kwargs: Any,
    ) -> Runnable:
        """绑定工具，返回带有工具信息的 Runnable（供 create_agent 使用）"""
        # 深拷贝自己，存储工具
        bound = self.model_copy()
        bound._bound_tools = [_convert_tool_to_openai_schema(t) for t in tools]
        bound._tool_choice = tool_choice
        return bound

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: Optional[list[str]] = None,
        **kwargs,
    ) -> ChatResult:
        registry = ProviderRegistry()
        adapter = registry.get_adapter(self.stage_config.provider)

        llm_messages = []
        for msg in messages:
            if isinstance(msg, HumanMessage):
                llm_messages.append({"role": "user", "content": msg.content})
            elif isinstance(msg, AIMessage):
                llm_messages.append({"role": "assistant", "content": msg.content})
            elif isinstance(msg, SystemMessage):
                llm_messages.append({"role": "system", "content": msg.content})

        request = LLMRequest(
            model_id=self.stage_config.model.model_id,
            messages=llm_messages,
            temperature=self.stage_config.model.defaults.get("temperature", 0),
            max_tokens=self.stage_config.model.defaults.get("max_tokens"),
            extra_params={},
        )

        # 如果绑定了工具，传入 LLMRequest
        if getattr(self, "_bound_tools", None):
            request.tools = self._bound_tools

        response = adapter.complete(request)

        # 构建 AIMessage
        ai_message_kwargs: Dict[str, Any] = {"content": response.content}
        if response.tool_calls:
            # 解析 args (JSON string → dict)
            parsed_tool_calls = []
            for tc in response.tool_calls:
                args = tc.get("args")
                if isinstance(args, str):
                    import json
                    args = json.loads(args)
                parsed_tool_calls.append({
                    "name": tc.get("name", ""),
                    "args": args or {},
                    "id": tc.get("id", ""),
                })
            ai_message_kwargs["tool_calls"] = parsed_tool_calls

        gen = ChatGeneration(message=AIMessage(**ai_message_kwargs))
        return ChatResult(generations=[gen])

    async def _agenerate(
        self,
        messages: list[BaseMessage],
        stop: Optional[list[str]] = None,
        **kwargs,
    ) -> ChatResult:
        import asyncio
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, lambda: self._generate(messages, stop))

    def _create_streaming_adapter(self):
        """
        创建流式适配器（用于 SSE streaming）。
        返回一个同步 generator: (delta: str, full_content: str)
        """
        registry = ProviderRegistry()
        adapter = registry.get_adapter(self.stage_config.provider)

        def gen(messages: list[dict]):
            request = LLMRequest(
                model_id=self.stage_config.model.model_id,
                messages=messages,
                temperature=self.stage_config.model.defaults.get("temperature", 0),
                extra_params={},
            )
            if getattr(self, "_bound_tools", None):
                request.tools = self._bound_tools
            full = ""
            for chunk in adapter.stream(request):
                full = chunk.full_content
                yield chunk.delta, full
        return gen
