"""ComputeTool — 标量运算"""

from typing import Any, Union, Dict

from app.agent.tools.base import ExcelBaseTool, ToolResult
from app.engine.executor import ExcelExecutor
from app.engine.models import ComputeOperation


class ComputeTool(ExcelBaseTool):
    """执行标量运算（基于变量的算术/函数计算）"""

    name: str = "compute"
    description: str = (
        "执行标量运算或函数计算，结果存入变量。 "
        "参数: expression: str | dict（表达式，支持 JSON 对象格式）, "
        "as_var: str（结果变量名）, "
        "file_collection: FileCollection（必须）。"
    )

    async def _arun(
        self,
        expression: Union[str, Dict],
        as_var: str = "",
        file_collection: Any = None,
        **kwargs,
    ) -> ToolResult:
        if file_collection is None:
            return ToolResult(success=False, error="file_collection 不能为空")

        try:
            op = ComputeOperation(
                expression=expression,
                as_var=as_var,
            )
        except Exception as e:
            return ToolResult(success=False, error=f"构造 ComputeOperation 失败: {e}")

        try:
            executor = ExcelExecutor(file_collection)
            result = executor._execute_compute(op)
            if result.error:
                return ToolResult(success=False, error=result.error)
            return ToolResult(
                success=True,
                observation=f"计算完成: {as_var} = {result.value}" if as_var else f"计算完成: {result.value}",
                data={
                    "value": result.value,
                    "formula": result.excel_formula,
                    "as_var": as_var,
                }
            )
        except Exception as e:
            return ToolResult(success=False, error=f"计算执行失败: {e}")
