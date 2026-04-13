"""SelectColumnsTool — 选择列"""

from typing import Any, Dict, List, Optional

from app.agent.tools.base import ExcelBaseTool, ToolResult
from app.engine.executor import ExcelExecutor
from app.engine.models import SelectColumnsOperation


class SelectColumnsTool(ExcelBaseTool):
    """选择指定列（Excel 365+ CHOOSECOLS 函数）"""

    name: str = "select_columns"
    description: str = (
        "按指定列顺序投影输出。 "
        "参数: file_id: str, table: str（sheet名）, "
        "columns: list[str]（要保留的列名顺序）, "
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
            op = SelectColumnsOperation(
                file_id=file_id,
                table=table,
                columns=columns,
                output=output,
            )
        except Exception as e:
            return ToolResult(success=False, error=f"构造 SelectColumnsOperation 失败: {e}")

        try:
            executor = ExcelExecutor(file_collection)
            result = executor._execute_select_columns(op)
            if result.error:
                return ToolResult(success=False, error=result.error)
            return ToolResult(
                success=True,
                observation=f"选择列完成，保留 {len(columns)} 列",
                data={"columns": columns, "output": output}
            )
        except Exception as e:
            return ToolResult(success=False, error=f"选择列执行失败: {e}")
