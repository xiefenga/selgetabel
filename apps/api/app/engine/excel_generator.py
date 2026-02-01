"""Excel 公式生成器 - 将 JSON 格式公式转换为 Excel 公式"""

from typing import Dict, List, Any, Union
from app.engine.models import (
    FileCollection,
    AddColumnOperation,
    UpdateColumnOperation,
    FilterOperation,
    SortOperation,
    GroupByOperation,
    CreateSheetOperation,
    TakeOperation,
)


class ExcelFormulaGenerator:
    """Excel 公式生成器"""

    def __init__(self, tables: FileCollection):
        self.tables = tables
        self.column_mapping = tables.get_column_mapping()  # 三层：file_id -> sheet_name -> col_name -> letter

    def generate_formula(
        self,
        expr: Union[Dict, Any],
        file_id: str,
        sheet_name: str,
        row_placeholder: str = "{row}"
    ) -> str:
        """
        将 JSON 表达式转换为 Excel 公式

        Args:
            expr: JSON 表达式对象
            file_id: 当前文件 ID
            sheet_name: 当前 sheet 名称
            row_placeholder: 行号占位符

        Returns:
            Excel 公式字符串
        """
        if not isinstance(expr, dict):
            # 原始值
            if isinstance(expr, str):
                return f'"{expr}"'
            return str(expr)

        # 字面量
        if "value" in expr:
            value = expr["value"]
            if isinstance(value, str):
                return f'"{value}"'
            if isinstance(value, bool):
                return "TRUE" if value else "FALSE"
            return str(value)

        # 列引用（当前行）
        if "col" in expr:
            col_name = expr["col"]
            # 从当前表获取列字母
            col_letter = self._find_column_letter(file_id, sheet_name, col_name)
            return f"{col_letter}{row_placeholder}"

        # 跨表引用
        if "ref" in expr:
            return self._generate_ref(expr["ref"])

        # 变量引用 - 引用前面 aggregate/compute 操作的结果
        if "var" in expr:
            var_name = expr["var"]
            # 在 Excel 中，变量通常需要用命名范围或单元格引用
            # 这里生成一个占位符，提示用户替换为实际的聚合结果
            return f"${{{var_name}}}"

        # 函数调用
        if "func" in expr:
            return self._generate_function(
                expr["func"], expr.get("args", []), file_id, sheet_name, row_placeholder
            )

        # 二元运算
        if "op" in expr:
            return self._generate_binary_op(
                expr["op"], expr["left"], expr["right"], file_id, sheet_name, row_placeholder
            )

        return "#UNKNOWN"

    def _find_column_letter(self, file_id: str, sheet_name: str, col_name: str) -> str:
        """找到列名对应的 Excel 列字母"""
        if file_id in self.column_mapping:
            if sheet_name in self.column_mapping[file_id]:
                mapping = self.column_mapping[file_id][sheet_name]
                return mapping.get(col_name, "?")
        return "?"

    def _generate_ref(self, ref: str) -> str:
        """生成跨表引用（三段式：file_id.sheet_name.column_name）"""
        parts = ref.split(".")
        if len(parts) != 3:
            return f"#{ref}"

        file_id, sheet_name, col_name = parts

        # 获取列字母
        col_letter = self._find_column_letter(file_id, sheet_name, col_name)

        # 生成 Excel 引用格式：sheet_name!列:列
        return f"{sheet_name}!{col_letter}:{col_letter}"

    def _generate_function(
        self, func_name: str, args: List, file_id: str, sheet_name: str, row_placeholder: str
    ) -> str:
        """生成函数调用"""
        func_upper = func_name.upper()

        # COUNTIFS 特殊处理
        if func_upper == "COUNTIFS":
            return self._generate_countifs(args, file_id, sheet_name, row_placeholder)

        # VLOOKUP 特殊处理
        if func_upper == "VLOOKUP":
            return self._generate_vlookup(args, file_id, sheet_name, row_placeholder)

        # IF
        if func_upper == "IF":
            if len(args) != 3:
                return "#ERROR"
            cond = self.generate_formula(args[0], file_id, sheet_name, row_placeholder)
            true_val = self.generate_formula(args[1], file_id, sheet_name, row_placeholder)
            false_val = self.generate_formula(args[2], file_id, sheet_name, row_placeholder)
            return f"IF({cond}, {true_val}, {false_val})"

        # CONCAT -> 使用 & 连接
        if func_upper == "CONCAT":
            parts = [self.generate_formula(arg, file_id, sheet_name, row_placeholder) for arg in args]
            return "&".join(parts)

        # 其他函数
        arg_strs = [self.generate_formula(arg, file_id, sheet_name, row_placeholder) for arg in args]
        return f"{func_upper}({', '.join(arg_strs)})"

    def _generate_countifs(
        self, args: List, file_id: str, sheet_name: str, row_placeholder: str
    ) -> str:
        """生成 COUNTIFS 公式"""
        if len(args) % 2 != 0:
            return "#ERROR"

        parts = []
        for i in range(0, len(args), 2):
            range_expr = args[i]
            criteria_expr = args[i + 1]

            # 范围
            range_str = self.generate_formula(range_expr, file_id, sheet_name, row_placeholder)
            # 条件
            criteria_str = self.generate_formula(criteria_expr, file_id, sheet_name, row_placeholder)

            parts.append(range_str)
            parts.append(criteria_str)

        return f"COUNTIFS({', '.join(parts)})"

    def _generate_vlookup(
        self, args: List, file_id: str, sheet_name: str, row_placeholder: str
    ) -> str:
        """生成 VLOOKUP 公式（表引用格式：file_id.sheet_name）"""
        if len(args) != 4:
            return "#ERROR"

        lookup_value = self.generate_formula(args[0], file_id, sheet_name, row_placeholder)
        table_ref = args[1].get("value", args[1]) if isinstance(args[1], dict) else args[1]  # "file_id.sheet_name"
        key_col = args[2].get("value", args[2]) if isinstance(args[2], dict) else args[2]
        value_col = args[3].get("value", args[3]) if isinstance(args[3], dict) else args[3]

        # 解析表引用
        parts = table_ref.split(".")
        if len(parts) != 2:
            return "#ERROR"
        target_file_id, target_sheet = parts

        # 获取表的列映射
        if target_file_id not in self.column_mapping:
            return "#ERROR"
        if target_sheet not in self.column_mapping[target_file_id]:
            return "#ERROR"
        mapping = self.column_mapping[target_file_id][target_sheet]

        key_letter = mapping.get(key_col, "A")
        value_letter = mapping.get(value_col, "B")

        # 计算列偏移
        key_idx = ord(key_letter) - ord('A')
        value_idx = ord(value_letter) - ord('A')
        col_offset = value_idx - key_idx + 1

        # 确定范围
        start_col = min(key_letter, value_letter)
        end_col = max(key_letter, value_letter)

        return f"VLOOKUP({lookup_value}, {target_sheet}!{start_col}:{end_col}, {col_offset}, FALSE)"

    def _generate_binary_op(
        self, op: str, left, right, file_id: str, sheet_name: str, row_placeholder: str
    ) -> str:
        """生成二元运算"""
        left_str = self.generate_formula(left, file_id, sheet_name, row_placeholder)
        right_str = self.generate_formula(right, file_id, sheet_name, row_placeholder)

        # 运算符映射
        op_map = {
            "==": "=",
            "!=": "<>",
        }
        excel_op = op_map.get(op, op)

        return f"({left_str}{excel_op}{right_str})"


def _get_description(op, fallback: str) -> str:
    """
    获取操作描述（优先使用 LLM 生成的描述，否则使用模板兜底）

    Args:
        op: 操作对象
        fallback: 模板生成的兜底描述

    Returns:
        描述文本
    """
    if hasattr(op, 'description') and op.description:
        return op.description
    return fallback


def generate_formulas(operations: List, tables: FileCollection) -> List[Dict]:
    """
    为操作列表生成 Excel 公式

    Args:
        operations: 操作列表
        tables: 文件集合

    Returns:
        公式结果列表
    """
    generator = ExcelFormulaGenerator(tables)
    results = []

    for op in operations:
        if isinstance(op, AddColumnOperation):
            # add_column 操作
            if isinstance(op.formula, dict):
                formula_template = generator.generate_formula(
                    op.formula, op.file_id, op.table
                )
                excel_file = tables.get_file(op.file_id)
                fallback_desc = f"在 {op.table} 表中新增「{op.name}」列"
                results.append({
                    "type": "add_column",
                    "file_id": op.file_id,
                    "filename": excel_file.filename,
                    "sheet": op.table,
                    "column_name": op.name,
                    "formula_template": f"={formula_template}",
                    "description": _get_description(op, fallback_desc)
                })

        elif isinstance(op, UpdateColumnOperation):
            # update_column 操作
            if isinstance(op.formula, dict):
                formula_template = generator.generate_formula(
                    op.formula, op.file_id, op.table
                )
                excel_file = tables.get_file(op.file_id)
                fallback_desc = f"更新 {op.table} 表中「{op.column}」列的值"
                results.append({
                    "type": "update_column",
                    "file_id": op.file_id,
                    "filename": excel_file.filename,
                    "sheet": op.table,
                    "column_name": op.column,
                    "formula_template": f"={formula_template}",
                    "description": _get_description(op, fallback_desc)
                })

        elif isinstance(op, FilterOperation):
            # filter 操作
            excel_file = tables.get_file(op.file_id)
            formula = _generate_filter_formula(op, generator)
            output_name = op.output.get("name", op.table)
            fallback_desc = f"筛选 {op.table} 表中符合条件的数据到 {output_name}"
            results.append({
                "type": "filter",
                "file_id": op.file_id,
                "filename": excel_file.filename,
                "sheet": op.table,
                "output_sheet": output_name,
                "formula": formula,
                "description": _get_description(op, fallback_desc),
                "excel_version": "Excel 365+",
                "note": "此公式需要 Excel 365 或 Excel 2021 及以上版本"
            })

        elif isinstance(op, SortOperation):
            # sort 操作
            excel_file = tables.get_file(op.file_id)
            formula = _generate_sort_formula(op, generator)
            output_type = op.output.get("type", "in_place") if op.output else "in_place"
            output_name = op.output.get("name", op.table) if op.output else op.table
            fallback_desc = f"对 {op.table} 表按指定列排序"
            if output_type == "new_sheet":
                fallback_desc += f"，结果输出到 {output_name}"
            results.append({
                "type": "sort",
                "file_id": op.file_id,
                "filename": excel_file.filename,
                "sheet": op.table,
                "output_sheet": output_name,
                "formula": formula,
                "description": _get_description(op, fallback_desc),
                "excel_version": "Excel 365+",
                "note": "此公式需要 Excel 365 或 Excel 2021 及以上版本"
            })

        elif isinstance(op, GroupByOperation):
            # group_by 操作
            excel_file = tables.get_file(op.file_id)
            formula = _generate_groupby_formula(op, generator)
            output_name = op.output["name"]
            group_cols = ", ".join(op.group_columns)
            fallback_desc = f"按 {group_cols} 分组统计 {op.table} 表，结果输出到 {output_name}"
            results.append({
                "type": "group_by",
                "file_id": op.file_id,
                "filename": excel_file.filename,
                "sheet": op.table,
                "output_sheet": output_name,
                "formula": formula,
                "description": _get_description(op, fallback_desc),
                "excel_version": "Excel 365+",
                "note": "GROUPBY 函数需要 Excel 365（2023年9月更新版本）"
            })

        elif isinstance(op, CreateSheetOperation):
            # create_sheet 操作（无 Excel 公式）
            excel_file = tables.get_file(op.file_id)
            source_type = op.source.get("type", "empty") if op.source else "empty"
            if source_type == "empty":
                fallback_desc = f"创建新工作表 {op.name}"
            elif source_type == "copy":
                fallback_desc = f"复制 {op.source.get('table')} 到新工作表 {op.name}"
            else:
                fallback_desc = f"创建工作表 {op.name}（结构引用 {op.source.get('table')}）"
            results.append({
                "type": "create_sheet",
                "file_id": op.file_id,
                "filename": excel_file.filename,
                "sheet": op.name,
                "formula": "（无对应公式，手动创建工作表）",
                "description": _get_description(op, fallback_desc),
                "note": "这是工作表操作，需要手动在 Excel 中创建"
            })

        elif isinstance(op, TakeOperation):
            # take 操作
            excel_file = tables.get_file(op.file_id)
            formula = _generate_take_formula(op, generator)
            output_type = op.output.get("type", "in_place") if op.output else "in_place"
            output_name = op.output.get("name", op.table) if op.output else op.table

            if op.rows > 0:
                fallback_desc = f"从 {op.table} 表取前 {op.rows} 行"
            else:
                fallback_desc = f"从 {op.table} 表取后 {abs(op.rows)} 行"
            if output_type == "new_sheet":
                fallback_desc += f"，结果输出到 {output_name}"

            results.append({
                "type": "take",
                "file_id": op.file_id,
                "filename": excel_file.filename,
                "sheet": op.table,
                "output_sheet": output_name,
                "formula": formula,
                "description": _get_description(op, fallback_desc),
                "excel_version": "Excel 365+",
                "note": "TAKE 函数需要 Excel 365 或 Excel 2021 及以上版本"
            })

        elif hasattr(op, 'function'):
            # aggregate 操作
            excel_file = tables.get_file(op.file_id)
            # 生成更友好的兜底描述
            func_desc_map = {
                "SUM": "求和",
                "COUNT": "计数",
                "COUNTA": "非空计数",
                "AVERAGE": "平均值",
                "MIN": "最小值",
                "MAX": "最大值",
                "MEDIAN": "中位数",
                "SUMIF": "条件求和",
                "COUNTIF": "条件计数",
                "AVERAGEIF": "条件平均值"
            }
            func_name = func_desc_map.get(op.function, op.function)
            col_part = f"「{op.column}」列" if op.column else ""
            fallback_desc = f"计算 {op.table} 表{col_part}的{func_name}"
            results.append({
                "type": "aggregate",
                "file_id": op.file_id,
                "filename": excel_file.filename,
                "sheet": op.table,
                "variable": op.as_var,
                "formula": f"=聚合公式（{op.function}）",
                "description": _get_description(op, fallback_desc)
            })

    return results


def _generate_filter_formula(op: FilterOperation, generator: ExcelFormulaGenerator) -> str:
    """
    生成 FILTER 公式

    Excel 格式：=FILTER(数据范围, (条件1) * (条件2) * ...)
    """
    table_name = op.table
    file_id = op.file_id

    # 获取表的列信息
    try:
        table = generator.tables.get_table(file_id, table_name)
        columns = table.get_columns()
        first_col = generator._find_column_letter(file_id, table_name, columns[0])
        last_col = generator._find_column_letter(file_id, table_name, columns[-1])
        data_range = f"{table_name}!{first_col}:{last_col}"
    except Exception:
        data_range = f"{table_name}!A:Z"

    # 构建条件表达式
    condition_parts = []
    for cond in op.conditions:
        col_name = cond["column"]
        operator = cond["op"]
        value = cond["value"]

        col_letter = generator._find_column_letter(file_id, table_name, col_name)
        col_range = f"{table_name}!{col_letter}:{col_letter}"

        # 格式化值
        if isinstance(value, str):
            formatted_value = f'"{value}"'
        else:
            formatted_value = str(value)

        # Excel 运算符
        if operator == "contains":
            # contains 需要使用 ISNUMBER + SEARCH
            condition_parts.append(f"ISNUMBER(SEARCH({formatted_value},{col_range}))")
        else:
            excel_op = "=" if operator == "=" else operator
            condition_parts.append(f"({col_range}{excel_op}{formatted_value})")

    # 组合条件
    if op.logic == "AND":
        conditions = " * ".join(condition_parts)  # AND 用 * 连接
    else:
        conditions = " + ".join(condition_parts)  # OR 用 + 连接

    return f"=FILTER({data_range}, {conditions})"


def _generate_sort_formula(op: SortOperation, generator: ExcelFormulaGenerator) -> str:
    """
    生成 SORT 公式

    Excel 格式：=SORT(数据范围, 列索引, 排序方向)
    """
    table_name = op.table
    file_id = op.file_id

    # 获取表的列信息
    try:
        table = generator.tables.get_table(file_id, table_name)
        columns = table.get_columns()
        first_col = generator._find_column_letter(file_id, table_name, columns[0])
        last_col = generator._find_column_letter(file_id, table_name, columns[-1])
        data_range = f"{table_name}!{first_col}:{last_col}"
    except Exception:
        data_range = f"{table_name}!A:Z"

    # 构建排序参数
    if len(op.by) == 1:
        # 单列排序
        rule = op.by[0]
        col_name = rule["column"]
        order = rule.get("order", "asc")

        try:
            col_index = columns.index(col_name) + 1  # Excel 列索引从 1 开始
        except (ValueError, NameError):
            col_index = 1

        sort_order = 1 if order == "asc" else -1
        return f"=SORT({data_range}, {col_index}, {sort_order})"
    else:
        # 多列排序
        col_indices = []
        sort_orders = []
        for rule in op.by:
            col_name = rule["column"]
            order = rule.get("order", "asc")
            try:
                col_index = columns.index(col_name) + 1
            except (ValueError, NameError):
                col_index = 1
            col_indices.append(str(col_index))
            sort_orders.append("1" if order == "asc" else "-1")

        return f"=SORT({data_range}, {{{', '.join(col_indices)}}}, {{{', '.join(sort_orders)}}})"


def _generate_groupby_formula(op: GroupByOperation, generator: ExcelFormulaGenerator) -> str:
    """
    生成 GROUPBY 公式

    Excel 格式：=GROUPBY(分组列, 聚合列, 聚合函数)
    """
    table_name = op.table
    file_id = op.file_id

    # 分组列
    group_ranges = []
    for col_name in op.group_columns:
        col_letter = generator._find_column_letter(file_id, table_name, col_name)
        group_ranges.append(f"{table_name}!{col_letter}:{col_letter}")

    # 如果只有一个分组列
    if len(group_ranges) == 1:
        group_range = group_ranges[0]
    else:
        group_range = f"HSTACK({', '.join(group_ranges)})"

    # 聚合（只支持单个聚合的简单情况）
    if len(op.aggregations) == 1:
        agg = op.aggregations[0]
        agg_col = agg["column"]
        agg_func = agg["function"].upper()
        col_letter = generator._find_column_letter(file_id, table_name, agg_col)
        agg_range = f"{table_name}!{col_letter}:{col_letter}"
        return f"=GROUPBY({group_range}, {agg_range}, {agg_func})"
    else:
        # 多个聚合需要使用更复杂的公式
        agg_parts = []
        for agg in op.aggregations:
            agg_col = agg["column"]
            agg_func = agg["function"].upper()
            col_letter = generator._find_column_letter(file_id, table_name, agg_col)
            agg_parts.append(f"{agg_func}({table_name}!{col_letter}:{col_letter})")

        # 返回说明性公式（Excel 中需要更复杂的 LAMBDA 语法）
        return f"=GROUPBY({group_range}, ..., LAMBDA(x, HSTACK({', '.join(agg_parts)})))"


def _generate_take_formula(op: TakeOperation, generator: ExcelFormulaGenerator) -> str:
    """
    生成 TAKE 公式

    Excel 格式：=TAKE(数据范围, 行数)
    - 正数取前 N 行
    - 负数取后 N 行
    """
    table_name = op.table
    file_id = op.file_id

    # 获取表的列信息
    try:
        table = generator.tables.get_table(file_id, table_name)
        columns = table.get_columns()
        first_col = generator._find_column_letter(file_id, table_name, columns[0])
        last_col = generator._find_column_letter(file_id, table_name, columns[-1])
        data_range = f"{table_name}!{first_col}:{last_col}"
    except Exception:
        data_range = f"{table_name}!A:Z"

    return f"=TAKE({data_range}, {op.rows})"


def format_formula_output(formula_results: List[Dict]) -> str:
    """格式化公式输出"""
    lines = []

    for i, result in enumerate(formula_results, 1):
        op_type = result["type"]

        if op_type == "add_column":
            lines.append(f"{i}. {result['description']}")
            lines.append(f"   文件: {result['filename']}")
            lines.append(f"   Sheet: {result['sheet']}")
            lines.append(f"   公式模板: {result['formula_template']}")
            lines.append(f"   说明: 将 {{row}} 替换为行号（如 2, 3, 4...），下拉填充")

        elif op_type == "update_column":
            lines.append(f"{i}. {result['description']}")
            lines.append(f"   文件: {result['filename']}")
            lines.append(f"   Sheet: {result['sheet']}")
            lines.append(f"   公式模板: {result['formula_template']}")
            lines.append(f"   说明: 将 {{row}} 替换为行号（如 2, 3, 4...），覆盖原列")

        elif op_type == "aggregate":
            lines.append(f"{i}. {result['description']}")
            lines.append(f"   文件: {result['filename']}")
            lines.append(f"   Sheet: {result['sheet']}")
            lines.append(f"   变量: {result['variable']}")
            lines.append(f"   公式: {result['formula']}")

        elif op_type == "filter":
            lines.append(f"{i}. {result['description']}")
            lines.append(f"   文件: {result['filename']}")
            lines.append(f"   源表: {result['sheet']}")
            lines.append(f"   输出表: {result['output_sheet']}")
            lines.append(f"   公式: {result['formula']}")
            lines.append(f"   ⚠️ {result.get('note', '')}")

        elif op_type == "sort":
            lines.append(f"{i}. {result['description']}")
            lines.append(f"   文件: {result['filename']}")
            lines.append(f"   源表: {result['sheet']}")
            lines.append(f"   输出表: {result['output_sheet']}")
            lines.append(f"   公式: {result['formula']}")
            lines.append(f"   ⚠️ {result.get('note', '')}")

        elif op_type == "group_by":
            lines.append(f"{i}. {result['description']}")
            lines.append(f"   文件: {result['filename']}")
            lines.append(f"   源表: {result['sheet']}")
            lines.append(f"   输出表: {result['output_sheet']}")
            lines.append(f"   公式: {result['formula']}")
            lines.append(f"   ⚠️ {result.get('note', '')}")

        elif op_type == "create_sheet":
            lines.append(f"{i}. {result['description']}")
            lines.append(f"   文件: {result['filename']}")
            lines.append(f"   新Sheet: {result['sheet']}")
            lines.append(f"   {result.get('note', '')}")

        elif op_type == "take":
            lines.append(f"{i}. {result['description']}")
            lines.append(f"   文件: {result['filename']}")
            lines.append(f"   源表: {result['sheet']}")
            lines.append(f"   输出表: {result['output_sheet']}")
            lines.append(f"   公式: {result['formula']}")
            lines.append(f"   ⚠️ {result.get('note', '')}")

    return "\n".join(lines)
