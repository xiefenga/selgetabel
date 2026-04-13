"""SortTool — 排序 Excel 行"""

from typing import Any, List

from app.agent.tools.base import ExcelBaseTool, ToolResult
from app.engine.executor import ExcelExecutor
from app.engine.models import SortOperation


class SortTool(ExcelBaseTool):
    """排序 Excel 行（Excel 365+ SORT 函数）"""

    name: str = "sort"
    description: str = (
        "按一列或多列排序 Excel 行。 "
        "参数: file_id: str, table: str, by: list[dict]（排序规则，格式：[{'column': '列名', 'order': 'asc'}]）, "
        "output: dict（输出目标，默认 {'type': 'in_place'}）, file_collection: FileCollection（必须）。"
    )

    async def _arun(
        self,
        file_id: str,
        table: str,
        by: List[dict],
        output: dict = None,
        file_collection: Any = None,
        **kwargs,
    ) -> ToolResult:
        if file_collection is None:
            return ToolResult(success=False, error="file_collection 不能为空")

        if output is None:
            output = {"type": "in_place"}

        try:
            op = SortOperation(file_id=file_id, table=table, by=by, output=output)
        except Exception as e:
            return ToolResult(success=False, error=f"构造 SortOperation 失败: {e}")

        try:
            executor = ExcelExecutor(file_collection)
            result = executor._execute_sort(op)
            if result.error:
                return ToolResult(success=False, error=result.error)
            return ToolResult(
                success=True,
                observation=f"排序完成（{table} 按 {','.join(r['column'] for r in by)} 排序）",
                data={"result": result.value}
            )
        except Exception as e:
            return ToolResult(success=False, error=f"排序执行失败: {e}")
