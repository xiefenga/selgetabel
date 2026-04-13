"""Schema Injector — 将 FileCollection 表结构格式化为 prompt 文本"""

from typing import Any

from app.engine.models import FileCollection


def build_schema_section(
    file_collection: FileCollection,
    sample_count: int = 3,
) -> str:
    """
    将 FileCollection 的表结构格式化为 prompt 中的 Schema 段落。

    格式：
    ## 当前 Excel 文件结构

    文件 [filename.xlsx] - Sheet [sheet_name]
    | 列名 | 类型 | 样本 |
    |------|------|------|
    | 姓名 | text | 张三、李四 |
    ...

    Args:
        file_collection: 文件集合
        sample_count: 每列采样的数据条数（默认 3 条）

    Returns:
        格式化的 prompt 文本段落
    """
    if file_collection is None:
        return "\n## 当前 Excel 文件结构\n\n（暂无已加载的文件）\n"

    schemas = file_collection.get_schemas_with_samples(sample_count=sample_count)

    if not schemas:
        return "\n## 当前 Excel 文件结构\n\n（暂无已加载的文件）\n"

    lines = ["\n## 当前 Excel 文件结构\n"]

    for file_id, sheets in schemas.items():
        excel_file = None
        # 找到 file_id 对应的 ExcelFile
        if hasattr(file_collection, '_files'):
            excel_file = file_collection._files.get(file_id)

        for sheet_name, columns in sheets.items():
            filename = excel_file.filename if excel_file else file_id
            lines.append(f"文件 [{filename}] - Sheet [{sheet_name}]")

            # 列信息行
            for col_info in columns:
                col_name = col_info["name"]
                col_type = col_info["type"]
                samples = col_info.get("samples", [])
                sample_str = "、".join(str(s) for s in samples[:sample_count]) if samples else "（无数据）"
                lines.append(f"  - {col_name}（{col_type}）：{sample_str}")

            lines.append("")

    return "\n".join(lines)
