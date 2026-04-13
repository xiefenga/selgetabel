"""TakeTool — 取前/后 N 行"""

from typing import Any, Dict, Optional

from app.agent.tools.base import ExcelBaseTool, ToolResult
from app.engine.executor import ExcelExecutor
from app.engine.models import TakeOperation


class TakeTool(ExcelBaseTool):
    """取前 N 行或后 N 行（Excel 365+ TAKE 函数）"""

    name: str = "take"
    description: str = (
        "从表的开头或末尾提取指定数量的行。 "
        "参数: file_id: str, table: str（sheet名）, "
        "rows: int（正数取前N行，负数取后N行）, "
        "output: dict（输出目标，格式：{'type': 'new_sheet', 'name': '结果'} 或 {'type': 'in_place'}), "
        "file_collection: FileCollection（必须）。"
    )

    async def _arun(
        self,
        file_id: str,
        table: str,
        rows: int,
        output: Optional[Dict[str, Any]] = None,
        file_collection: Any = None,
        **kwargs,
    ) -> ToolResult:
        if file_collection is None:
            return ToolResult(success=False, error="file_collection 不能为空")

        if output is None:
            output = {"type": "in_place"}

        try:
            op = TakeOperation(
                file_id=file_id,
                table=table,
                rows=rows,
                output=output,
            )
        except Exception as e:
            return ToolResult(success=False, error=f"构造 TakeOperation 失败: {e}")

        try:
            executor = ExcelExecutor(file_collection)
            result = executor._execute_take(op)
            if result.error:
                return ToolResult(success=False, error=result.error)
            return ToolResult(
                success=True,
                observation=f"提取 {rows} 行完成",
                data={"row_count": rows, "output": output}
            )
        except Exception as e:
            return ToolResult(success=False, error=f"提取行执行失败: {e}")
