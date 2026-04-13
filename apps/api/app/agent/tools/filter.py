"""FilterTool — 筛选 Excel 行"""

from typing import Any, List

from app.agent.tools.base import ExcelBaseTool, ToolResult
from app.engine.executor import ExcelExecutor
from app.engine.models import FilterOperation


class FilterTool(ExcelBaseTool):
    """筛选 Excel 行（Excel 365+ FILTER 函数）"""

    name: str = "filter"
    description: str = (
        "按条件筛选 Excel 行。 "
        "参数: file_id: str, table: str（sheet名）, conditions: list[dict]（筛选条件，格式：[{'column': '列名', 'op': '>', 'value': 100}]）, "
        "logic: str = 'AND'（'AND'或'OR'）, output: dict（输出目标，格式：{'type': 'new_sheet', 'name': '结果'} 或 {'type': 'in_place'}）, "
        "file_collection: FileCollection（必须，上下文）。"
    )

    async def _arun(
        self,
        file_id: str,
        table: str,
        conditions: List[dict],
        logic: str = "AND",
        output: dict = None,
        file_collection: Any = None,
        **kwargs,
    ) -> ToolResult:
        if file_collection is None:
            return ToolResult(success=False, error="file_collection 不能为空，请先调用 read_excel")

        if output is None:
            output = {"type": "in_place"}

        try:
            op = FilterOperation(
                file_id=file_id,
                table=table,
                conditions=conditions,
                logic=logic,
                output=output,
            )
        except Exception as e:
            return ToolResult(success=False, error=f"构造 FilterOperation 失败: {e}")

        try:
            executor = ExcelExecutor(file_collection)
            result = executor._execute_filter(op)

            if result.error:
                return ToolResult(success=False, error=result.error, observation=str(result.value) if result.value else "")

            return ToolResult(
                success=True,
                observation=f"筛选完成，保留 {len(result.value) if result.value else 0} 行",
                data={
                    "filtered_count": len(result.value) if result.value else 0,
                    "result_value": result.value,
                }
            )
        except Exception as e:
            return ToolResult(success=False, error=f"筛选执行失败: {e}")
