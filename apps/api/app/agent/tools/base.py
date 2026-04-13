"""Excel 工具基类"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, Any

from langchain_core.messages import ToolMessage
from langchain_core.tools import BaseTool


@dataclass
class ToolResult:
    """工具执行结果（统一格式）"""

    success: bool
    observation: str = ""           # human-readable 摘要
    data: Optional[dict] = None    # 结构化数据（供后续工具使用）
    error: Optional[str] = None
    download_url: Optional[str] = None


class ExcelBaseTool(BaseTool, ABC):
    """Excel 工具基类"""

    name: str
    description: str

    def _run(self, **kwargs) -> ToolResult:
        raise NotImplementedError("ExcelBaseTool 只支持异步接口，请使用 _arun")

    @abstractmethod
    async def _arun(self, **kwargs) -> ToolResult:
        """异步执行接口，所有工具必须实现"""
        pass

    async def arun(  # type: ignore[override]
        self,
        tool_input: str | dict,
        **kwargs: Any,
    ) -> ToolMessage:
        """
        LangChain / langgraph 调用的异步入口。

        1. 展开 kwargs 包装
        2. 调用 _arun 获取 ToolResult
        3. 转换为 ToolMessage 返回（langgraph 要求）
        """
        tool_call_id = kwargs.pop("tool_call_id", None)
        if isinstance(tool_input, dict) and "kwargs" in tool_input:
            tool_input = tool_input["kwargs"]
        result = await self._arun(**tool_input)
        return ToolMessage(
            content=result.observation or "",
            name=self.name,
            tool_call_id=tool_call_id or "",
        )

    async def run(self, tool_input: str | dict, **kwargs) -> ToolResult:
        """子类可覆盖的实现（返回 ToolResult）"""
        if isinstance(tool_input, dict):
            return await self._arun(**tool_input)
        return await self._arun(query=tool_input)
