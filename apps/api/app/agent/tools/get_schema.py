"""GetSchemaTool — 获取表结构"""

from typing import Any

from app.agent.tools.base import ExcelBaseTool, ToolResult


class GetSchemaTool(ExcelBaseTool):
    """获取 FileCollection 中所有表的结构信息（列名、类型、样本数据）"""

    name: str = "get_schema"
    description: str = (
        "获取 FileCollection 中所有表的结构信息。 "
        "参数: file_id: str（可选，指定文件；为空则返回全部）, "
        "sample_count: int（每列采样行数，默认3）, "
        "file_collection: FileCollection（必须）。"
    )

    async def _arun(
        self,
        file_id: str = "",
        sample_count: int = 3,
        file_collection: Any = None,
        **kwargs,
    ) -> ToolResult:
        if file_collection is None:
            return ToolResult(success=False, error="file_collection 不能为空")

        try:
            schemas = file_collection.get_schemas_with_samples(sample_count=sample_count)

            if file_id:
                if file_id not in schemas:
                    return ToolResult(success=False, error=f"文件不存在: {file_id}")
                schemas = {file_id: schemas[file_id]}

            return ToolResult(
                success=True,
                observation=f"获取表结构完成",
                data={"schemas": schemas}
            )
        except Exception as e:
            return ToolResult(success=False, error=f"获取表结构失败: {e}")
