"""UpdateColumnTool — 更新现有列"""

from typing import Any, Union, Dict

from app.agent.tools.base import ExcelBaseTool, ToolResult
from app.engine.executor import ExcelExecutor
from app.engine.models import UpdateColumnOperation


class UpdateColumnTool(ExcelBaseTool):
    """更新现有列（填充空值或批量修改值）"""

    name: str = "update_column"
    description: str = (
        "更新 Excel 中现有列的值（可填充空值或批量修改）。 "
        "参数: file_id: str, table: str, column: str（列名）, "
        "formula: str | dict（计算公式）, "
        "file_collection: FileCollection（必须）。"
    )

    async def _arun(
        self,
        file_id: str,
        table: str,
        column: str,
        formula: Union[str, Dict],
        file_collection: Any = None,
        **kwargs,
    ) -> ToolResult:
        if file_collection is None:
            return ToolResult(success=False, error="file_collection 不能为空")

        try:
            op = UpdateColumnOperation(
                file_id=file_id,
                table=table,
                column=column,
                formula=formula,
            )
        except Exception as e:
            return ToolResult(success=False, error=f"构造 UpdateColumnOperation 失败: {e}")

        try:
            executor = ExcelExecutor(file_collection)
            result = executor._execute_update_column(op)
            if result.error:
                return ToolResult(success=False, error=result.error)
            return ToolResult(
                success=True,
                observation=f"更新列 '{column}' 完成",
                data={"updated_column": column}
            )
        except Exception as e:
            return ToolResult(success=False, error=f"更新列失败: {e}")
