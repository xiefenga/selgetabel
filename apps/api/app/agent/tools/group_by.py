"""GroupByTool — 分组聚合"""

from typing import Any, Dict, List

from app.agent.tools.base import ExcelBaseTool, ToolResult
from app.engine.executor import ExcelExecutor
from app.engine.models import GroupByOperation


class GroupByTool(ExcelBaseTool):
    """分组聚合（Excel 365+ GROUPBY 函数）"""

    name: str = "group_by"
    description: str = (
        "对 Excel 按分组列进行聚合统计，生成汇总表。 "
        "参数: file_id: str, table: str（sheet名）, "
        "group_columns: list[str]（分组列）, "
        "aggregations: list[dict]（聚合定义，格式：[{'column': '列名', 'function': 'SUM', 'as': '别名'}]）, "
        "output: dict（输出目标，格式：{'type': 'new_sheet', 'name': '统计表'}), "
        "file_collection: FileCollection（必须）。"
    )

    async def _arun(
        self,
        file_id: str,
        table: str,
        group_columns: List[str],
        aggregations: List[Dict[str, Any]],
        output: Dict[str, Any],
        file_collection: Any = None,
        **kwargs,
    ) -> ToolResult:
        if file_collection is None:
            return ToolResult(success=False, error="file_collection 不能为空")

        try:
            op = GroupByOperation(
                file_id=file_id,
                table=table,
                group_columns=group_columns,
                aggregations=aggregations,
                output=output,
            )
        except Exception as e:
            return ToolResult(success=False, error=f"构造 GroupByOperation 失败: {e}")

        try:
            executor = ExcelExecutor(file_collection)
            result = executor._execute_group_by(op)
            if result.error:
                return ToolResult(success=False, error=result.error)
            return ToolResult(
                success=True,
                observation=f"分组聚合完成，生成新 Sheet '{output.get('name', '统计表')}'",
                data={"new_sheet": output.get("name")}
            )
        except Exception as e:
            return ToolResult(success=False, error=f"分组聚合执行失败: {e}")
