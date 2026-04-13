"""DropColumnsTool — 删除列"""

from typing import Any, Dict, List, Optional

from app.agent.tools.base import ExcelBaseTool, ToolResult
from app.engine.executor import ExcelExecutor
from app.engine.models import DropColumnsOperation


class DropColumnsTool(ExcelBaseTool):
    """删除指定列（Excel 365+ CHOOSECOLS 函数）"""

    name: str = "drop_columns"
    description: str = (
        "删除指定列，输出剩余列。 "
        "参数: file_id: str, table: str（sheet名）, "
        "columns: list[str]（要删除的列名）, "
        "output: dict（输出目标，格式：{'type': 'new_sheet', 'name': '结果'} 或 {'type': 'in_place'}), "
        "file_collection: FileCollection（必须）。"
    )

    async def _arun(
        self,
        file_id: str,
        table: str,
        columns: List[str],
        output: Optional[Dict[str, Any]] = None,
        file_collection: Any = None,
        **kwargs,
    ) -> ToolResult:
        if file_collection is None:
            return ToolResult(success=False, error="file_collection 不能为空")

        if output is None:
            output = {"type": "in_place"}

        try:
            op = DropColumnsOperation(
                file_id=file_id,
                table=table,
                columns=columns,
                output=output,
            )
        except Exception as e:
            return ToolResult(success=False, error=f"构造 DropColumnsOperation 失败: {e}")

        try:
            executor = ExcelExecutor(file_collection)
            result = executor._execute_drop_columns(op)
            if result.error:
                return ToolResult(success=False, error=result.error)
            return ToolResult(
                success=True,
                observation=f"删除列完成，保留 {result.value} 列",
                data={"dropped": columns, "output": output}
            )
        except Exception as e:
            return ToolResult(success=False, error=f"删除列执行失败: {e}")
