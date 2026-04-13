"""ReadExcelTool — 从 MinIO 读取 Excel 文件"""

from typing import Any, List
from uuid import UUID

from sqlalchemy import select

from app.agent.tools.base import ExcelBaseTool, ToolResult
from app.engine.excel_parser import ExcelParser
from app.models.file import File


class ReadExcelTool(ExcelBaseTool):
    """读取 Excel 文件并返回 FileCollection"""

    name: str = "read_excel"
    description: str = (
        "从 MinIO 读取已上传的 Excel 文件，解析为 FileCollection 供后续工具使用。 "
        "参数 file_ids: list[str]（文件 UUID 列表）, user_id: str（用户 ID）, db: AsyncSession。 "
        "返回文件结构和样本数据（每列前3行）。"
    )

    async def _arun(
        self,
        file_ids: List[str],
        user_id: str = "",
        db: Any = None,
    ) -> ToolResult:
        # 优先从实例 context 读取（由 registry.set_context 注入）
        db = db or getattr(self, "_context_db", None)
        user_id = user_id or getattr(self, "_context_user_id", "") or ""
        if not db:
            return ToolResult(success=False, error="db session 未提供")

        if not file_ids:
            return ToolResult(success=False, error="file_ids 不能为空")

        # 从 DB 查找文件记录
        file_uuid_list = [UUID(fid) for fid in file_ids]
        stmt = select(File).where(
            File.id.in_(file_uuid_list),
            File.user_id == UUID(user_id),
        )
        result = await db.execute(stmt)
        files = list(result.scalars().all())

        if len(files) != len(file_ids):
            found_ids = {f.id for f in files}
            missing = [fid for fid in file_ids if UUID(fid) not in found_ids]
            return ToolResult(
                success=False,
                error=f"部分文件不存在或无权访问: {missing}"
            )

        # 构造 file_records: List[(file_id, minio_path, filename)]
        file_records = []
        for f in files:
            filename = f.filename or "unknown.xlsx"
            file_id_str = str(f.id)
            file_records.append((file_id_str, f.file_path, filename))

        try:
            fc = ExcelParser.load_tables_from_minio_paths(file_records)
        except FileNotFoundError as e:
            return ToolResult(success=False, error=f"文件未找到: {e}")
        except Exception as e:
            return ToolResult(success=False, error=f"解析文件失败: {e}")

        # 提取 schema 摘要
        schema_summary = []
        for excel_file in fc._files.values():
            for sheet_name, table in excel_file._sheets.items():
                cols = table.get_columns()
                samples = table._data.head(3).values.tolist()
                schema_summary.append({
                    "file_id": excel_file.file_id,
                    "sheet": sheet_name,
                    "columns": cols,
                    "sample_rows": samples,
                    "row_count": table.row_count(),
                })

        return ToolResult(
            success=True,
            observation=f"成功读取 {len(files)} 个文件，共 {len(schema_summary)} 个表",
            data={
                "file_collection": fc,
                "schema_summary": schema_summary,
            }
        )

