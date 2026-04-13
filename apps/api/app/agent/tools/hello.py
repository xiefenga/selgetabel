"""HelloTool — 打招呼"""

from app.agent.tools.base import ExcelBaseTool, ToolResult


class HelloTool(ExcelBaseTool):
    """打招呼工具"""

    name: str = "hello"
    description: str = (
        "打招呼用。当用户只是闲聊、问候或说「你好」时调用此工具。 "
        "参数 greeting: str = '你好'。返回问候语。"
    )

    async def _arun(self, greeting: str = "你好") -> ToolResult:
        return ToolResult(
            success=True,
            observation=f"{greeting}！我是 Excel 智能助手，可以帮你处理数据分析、排序、筛选等操作。有什么我可以帮你的吗？"
        )
