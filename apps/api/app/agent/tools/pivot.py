"""PivotTool — 数据透视"""

from typing import Any, Dict, List, Optional

from app.agent.tools.base import ExcelBaseTool, ToolResult
from app.engine.executor import ExcelExecutor
from app.engine.pivot_models import PivotOperation, PivotAggregation


class PivotTool(ExcelBaseTool):
    """数据透视（Excel 365+ PIVOTBY 函数）"""

    name: str = "pivot"
    description: str = (
        "对 Excel 进行数据透视，按行字段和列字段交叉分组聚合。 "
        "参数: file_id: str, table: str（sheet名）, "
        "row_fields: list[str]（行区域分组列）, "
        "values: list[dict]（值区域聚合，格式：[{'column': '列名', 'function': 'SUM'}]）, "
        "output: dict（输出目标，格式：{'type': 'new_sheet', 'name': '透视表'}), "
        "col_fields: list[str]（可选，列区域分组列）, "
        "file_collection: FileCollection（必须）。"
    )

    async def _arun(
        self,
        file_id: str,
        table: str,
        row_fields: List[str],
        values: List[dict],
        output: Dict[str, Any],
        col_fields: Optional[List[str]] = None,
        file_collection: Any = None,
        **kwargs,
    ) -> ToolResult:
        if file_collection is None:
            return ToolResult(success=False, error="file_collection 不能为空")

        try:
            pivot_values = [
                PivotAggregation(column=v["column"], function=v["function"])
                for v in values
            ]
            op = PivotOperation(
                file_id=file_id,
                table=table,
                row_fields=row_fields,
                col_fields=col_fields,
                values=pivot_values,
                output=output,
            )
        except Exception as e:
            return ToolResult(success=False, error=f"构造 PivotOperation 失败: {e}")

        try:
            executor = ExcelExecutor(file_collection)
            result = executor._execute_pivot(op)
            if result.error:
                return ToolResult(success=False, error=result.error)
            return ToolResult(
                success=True,
                observation=f"透视完成，生成新 Sheet '{output.get('name', '透视表')}'",
                data={"new_sheet": output.get("name")}
            )
        except Exception as e:
            return ToolResult(success=False, error=f"透视执行失败: {e}")
