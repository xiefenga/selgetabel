"""AddColumnTool — 新增计算列"""

from typing import Any, Union, Dict

from app.agent.tools.base import ExcelBaseTool, ToolResult
from app.engine.executor import ExcelExecutor
from app.engine.models import AddColumnOperation


class AddColumnTool(ExcelBaseTool):
    """新增计算列"""

    name: str = "add_column"
    description: str = (
        "在 Excel 中新增一列，该列通过公式计算得出。 "
        "参数: file_id: str, table: str, name: str（新列名）, "
        "formula: str | dict（Excel 公式，dict 格式为 JSON 对象）, "
        "file_collection: FileCollection（必须）。"
    )

    async def _arun(
        self,
        file_id: str,
        table: str,
        name: str,
        formula: Union[str, Dict],
        file_collection: Any = None,
        **kwargs,
    ) -> ToolResult:
        if file_collection is None:
            return ToolResult(success=False, error="file_collection 不能为空")

        try:
            op = AddColumnOperation(
                file_id=file_id,
                table=table,
                name=name,
                formula=formula,
            )
        except Exception as e:
            return ToolResult(success=False, error=f"构造 AddColumnOperation 失败: {e}")

        try:
            executor = ExcelExecutor(file_collection)
            result = executor._execute_add_column(op)
            if result.error:
                return ToolResult(success=False, error=result.error)
            return ToolResult(
                success=True,
                observation=f"新增列 '{name}' 完成",
                data={"new_column": name, "formula": result.excel_formula}
            )
        except Exception as e:
            return ToolResult(success=False, error=f"新增列失败: {e}")
