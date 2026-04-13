"""GenerateFormulasTool — 生成 Excel 公式"""

from typing import Any, Dict, List, Union

from app.agent.tools.base import ExcelBaseTool, ToolResult
from app.engine.executor import ExcelExecutor
from app.engine.models import (
    AggregateOperation,
    AddColumnOperation,
    UpdateColumnOperation,
    FilterOperation,
    SortOperation,
    GroupByOperation,
    TakeOperation,
    SelectColumnsOperation,
    DropColumnsOperation,
)


class GenerateFormulasTool(ExcelBaseTool):
    """根据已执行的操作生成 Excel 公式"""

    name: str = "generate_formulas"
    description: str = (
        "根据操作历史生成 Excel 公式。 "
        "参数: operations: list[dict]（操作定义列表）, "
        "file_collection: FileCollection（必须）。"
    )

    async def _arun(
        self,
        operations: List[Dict[str, Any]],
        file_collection: Any = None,
        **kwargs,
    ) -> ToolResult:
        if file_collection is None:
            return ToolResult(success=False, error="file_collection 不能为空")

        try:
            executor = ExcelExecutor(file_collection)
            formulas = []

            for op_dict in operations:
                op_type = op_dict.get("type", "")
                try:
                    if op_type == "add_column":
                        op = AddColumnOperation(**op_dict)
                        result = executor._execute_add_column(op)
                    elif op_type == "update_column":
                        op = UpdateColumnOperation(**op_dict)
                        result = executor._execute_update_column(op)
                    elif op_type == "filter":
                        op = FilterOperation(**op_dict)
                        result = executor._execute_filter(op)
                    elif op_type == "sort":
                        op = SortOperation(**op_dict)
                        result = executor._execute_sort(op)
                    elif op_type == "aggregate":
                        op = AggregateOperation(**op_dict)
                        result = executor._execute_aggregate(op)
                    elif op_type == "group_by":
                        op = GroupByOperation(**op_dict)
                        result = executor._execute_group_by(op)
                    elif op_type == "take":
                        op = TakeOperation(**op_dict)
                        result = executor._execute_take(op)
                    elif op_type == "select_columns":
                        op = SelectColumnsOperation(**op_dict)
                        result = executor._execute_select_columns(op)
                    elif op_type == "drop_columns":
                        op = DropColumnsOperation(**op_dict)
                        result = executor._execute_drop_columns(op)
                    else:
                        formulas.append({"type": op_type, "error": f"未知操作类型: {op_type}"})
                        continue

                    formulas.append({
                        "type": op_type,
                        "formula": result.excel_formula,
                        "value": result.value,
                    })
                except Exception as e:
                    formulas.append({"type": op_type, "error": str(e)})

            return ToolResult(
                success=True,
                observation=f"生成 {len(formulas)} 条公式",
                data={"formulas": formulas}
            )
        except Exception as e:
            return ToolResult(success=False, error=f"生成公式失败: {e}")
