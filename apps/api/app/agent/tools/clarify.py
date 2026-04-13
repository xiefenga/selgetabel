"""ClarifyTool — 需求澄清"""

from typing import Optional

from app.agent.tools.base import ExcelBaseTool, ToolResult


class ClarifyTool(ExcelBaseTool):
    """需求澄清工具"""

    name: str = "clarify"
    description: str = (
        "当用户需求缺少关键信息（如列名、操作类型）时调用此工具，"
        "向用户提出明确问题并列出可用选项。 "
        "参数 question: str（要问的问题）, options: list[str]（可选的答案选项）。"
        "返回给用户的反问内容。"
    )

    async def _arun(
        self,
        question: str,
        options: Optional[list[str]] = None,
    ) -> ToolResult:
        prompt = question
        if options:
            prompt += "\n可选：" + "、".join(options)
        return ToolResult(
            success=True,
            observation=prompt,
            data={"requires_clarification": True, "options": options or []}
        )
