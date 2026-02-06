from typing import Dict


def build_initial_user_message(query: str, table_schemas: Dict[str, Dict[str, str]]) -> str:
  """
  构建初始用户消息（包含表结构信息）

  支持两种 schema 格式：
  1. 简单格式（旧）: {file_id: {sheet_name: {col_letter: col_name}}}
  2. 增强格式（新）: {file_id: {sheet_name: [{name, type, samples}, ...]}}
  """
  schema_text = "## 当前Excel文件以及表结构信息\n\n"

  # 两层结构：文件 -> sheets
  for file_id, file_sheets in table_schemas.items():
    schema_text += f"### 文件: {file_id}\n\n"
    for sheet_name, fields in file_sheets.items():
      schema_text += f"#### Sheet: {sheet_name}\n"

      # 检测 schema 格式
      if isinstance(fields, list):
        # 增强格式：包含类型和样本
        schema_text += "| 列名 | 类型 | 样本数据 |\n"
        schema_text += "|------|------|----------|\n"
        for col_info in fields:
          name = col_info.get("name", "")
          col_type = col_info.get("type", "text")
          samples = col_info.get("samples", [])
          # 格式化样本数据
          if samples:
            samples_str = ", ".join(
              f'"{s}"' if isinstance(s, str) else str(s)
              for s in samples[:3]
            )
          else:
            samples_str = "(空)"
          schema_text += f"| {name} | {col_type} | {samples_str} |\n"
      else:
        # 简单格式（兼容旧代码）
        field_list = ", ".join(fields.values())
        schema_text += f"- columns: {field_list}\n"

      schema_text += "\n"

  schema_text += "## 需求描述\n\n"
  schema_text += query

  return schema_text