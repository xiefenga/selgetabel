"""AggregateTool — 列聚合计算"""

from typing import Any, Optional

from app.agent.tools.base import ExcelBaseTool, ToolResult
from app.engine.executor import ExcelExecutor
from app.engine.models import AggregateOperation


class AggregateTool(ExcelBaseTool):
    """对列进行聚合计算（SUM/COUNT/AVG 等）"""

    name: str = "aggregate"
    description: str = (
        "对 Excel 列进行聚合计算（求和、计数、平均等）。"
        "参数: file_id: str, table: str（sheet名）, column: str（被聚合的列）, "
        "function: str（SUM/COUNT/COUNTA/AVERAGE/MIN/MAX/MEDIAN/SUMIF/COUNTIF/AVERAGEIF）, "
        "condition_column: str（条件列，SUMIF/COUNTIF/AVERAGEIF 时使用）, "
        "condition: str|number（条件值）, as_var: str（结果变量名）, "
        "file_collection: FileCollection（必须）。"
    )

    async def _arun(
        self,
        file_id: str,
        table: str,
        column: str,
        function: str,
        condition_column: Optional[str] = None,
        condition: Any = None,
        as_var: str = "",
        file_collection: Any = None,
        **kwargs,
    ) -> ToolResult:
        if file_collection is None:
            return ToolResult(success=False, error="file_collection 不能为空")

        try:
            op = AggregateOperation(
                file_id=file_id,
                table=table,
                column=column,
                function=function.upper(),
                condition_column=condition_column,
                condition=condition,
                as_var=as_var,
            )
        except Exception as e:
            return ToolResult(success=False, error=f"构造 AggregateOperation 失败: {e}")

        try:
            executor = ExcelExecutor(file_collection)
            result = executor._execute_aggregate(op)
            if result.error:
                return ToolResult(success=False, error=result.error)
            return ToolResult(
                success=True,
                observation=f"聚合 '{column}' ({function}) = {result.value}",
                data={
                    "value": result.value,
                    "formula": result.excel_formula,
                    "as_var": as_var,
                }
            )
        except Exception as e:
            return ToolResult(success=False, error=f"聚合执行失败: {e}")
