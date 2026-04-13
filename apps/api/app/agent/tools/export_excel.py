"""ExportExcelTool — 导出 Excel 文件"""

from typing import Any

from app.agent.tools.base import ExcelBaseTool, ToolResult


class ExportExcelTool(ExcelBaseTool):
    """将 FileCollection 导出为 Excel 字节流"""

    name: str = "export_excel"
    description: str = (
        "将当前 FileCollection 导出为 Excel 文件字节流。 "
        "参数: file_id: str（可选，导出单个文件；为空则导出全部）, "
        "file_collection: FileCollection（必须）。"
        "返回: Excel 文件字节流。"
    )

    async def _arun(
        self,
        file_id: str = "",
        file_collection: Any = None,
        **kwargs,
    ) -> ToolResult:
        if file_collection is None:
            return ToolResult(success=False, error="file_collection 不能为空")

        try:
            if file_id:
                excel_bytes = file_collection.export_file_to_bytes(file_id)
                filename = file_id
            else:
                excel_bytes = file_collection.export_to_bytes()
                filename = "export"

            return ToolResult(
                success=True,
                observation=f"导出 Excel 完成（{len(excel_bytes)} bytes）",
                data={
                    "excel_bytes": excel_bytes,
                    "filename": filename,
                }
            )
        except Exception as e:
            return ToolResult(success=False, error=f"导出 Excel 失败: {e}")
