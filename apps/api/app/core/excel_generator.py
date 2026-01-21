"""Excel 公式生成器 - 将 JSON 格式公式转换为 Excel 公式"""

from typing import Dict, List, Any, Union
from app.core.models import TableCollection


class ExcelFormulaGenerator:
    """Excel 公式生成器"""

    def __init__(self, tables: TableCollection):
        self.tables = tables
        self.column_mapping = tables.get_column_mapping()

    def generate_formula(self, expr: Union[Dict, Any], row_placeholder: str = "{row}") -> str:
        """
        将 JSON 表达式转换为 Excel 公式

        Args:
            expr: JSON 表达式对象
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
            # 需要找到这列在哪个表，以及对应的列字母
            col_letter = self._find_column_letter(col_name)
            return f"{col_letter}{row_placeholder}"

        # 跨表引用
        if "ref" in expr:
            return self._generate_ref(expr["ref"])

        # 函数调用
        if "func" in expr:
            return self._generate_function(expr["func"], expr.get("args", []), row_placeholder)

        # 二元运算
        if "op" in expr:
            return self._generate_binary_op(expr["op"], expr["left"], expr["right"], row_placeholder)

        return "#UNKNOWN"

    def _find_column_letter(self, col_name: str) -> str:
        """找到列名对应的 Excel 列字母"""
        for table_name, mapping in self.column_mapping.items():
            if col_name in mapping:
                return mapping[col_name]
        return "?"

    def _generate_ref(self, ref: str) -> str:
        """生成跨表引用"""
        if "." not in ref:
            return f"#{ref}"

        parts = ref.split(".", 1)
        table_name = parts[0]
        col_name = parts[1]

        # 获取列字母
        mapping = self.column_mapping.get(table_name, {})
        col_letter = mapping.get(col_name, "?")

        return f"{table_name}!{col_letter}:{col_letter}"

    def _generate_function(self, func_name: str, args: List, row_placeholder: str) -> str:
        """生成函数调用"""
        func_upper = func_name.upper()

        # COUNTIFS 特殊处理
        if func_upper == "COUNTIFS":
            return self._generate_countifs(args, row_placeholder)

        # VLOOKUP 特殊处理
        if func_upper == "VLOOKUP":
            return self._generate_vlookup(args, row_placeholder)

        # IF
        if func_upper == "IF":
            if len(args) != 3:
                return "#ERROR"
            cond = self.generate_formula(args[0], row_placeholder)
            true_val = self.generate_formula(args[1], row_placeholder)
            false_val = self.generate_formula(args[2], row_placeholder)
            return f"IF({cond}, {true_val}, {false_val})"

        # CONCAT -> 使用 & 连接
        if func_upper == "CONCAT":
            parts = [self.generate_formula(arg, row_placeholder) for arg in args]
            return "&".join(parts)

        # 其他函数
        arg_strs = [self.generate_formula(arg, row_placeholder) for arg in args]
        return f"{func_upper}({', '.join(arg_strs)})"

    def _generate_countifs(self, args: List, row_placeholder: str) -> str:
        """生成 COUNTIFS 公式"""
        if len(args) % 2 != 0:
            return "#ERROR"

        parts = []
        for i in range(0, len(args), 2):
            range_expr = args[i]
            criteria_expr = args[i + 1]

            # 范围
            range_str = self.generate_formula(range_expr, row_placeholder)
            # 条件
            criteria_str = self.generate_formula(criteria_expr, row_placeholder)

            parts.append(range_str)
            parts.append(criteria_str)

        return f"COUNTIFS({', '.join(parts)})"

    def _generate_vlookup(self, args: List, row_placeholder: str) -> str:
        """生成 VLOOKUP 公式"""
        if len(args) != 4:
            return "#ERROR"

        lookup_value = self.generate_formula(args[0], row_placeholder)
        table_name = args[1].get("value", args[1]) if isinstance(args[1], dict) else args[1]
        key_col = args[2].get("value", args[2]) if isinstance(args[2], dict) else args[2]
        value_col = args[3].get("value", args[3]) if isinstance(args[3], dict) else args[3]

        # 获取表的列映射
        mapping = self.column_mapping.get(table_name, {})
        key_letter = mapping.get(key_col, "A")
        value_letter = mapping.get(value_col, "B")

        # 计算列偏移
        key_idx = ord(key_letter) - ord('A')
        value_idx = ord(value_letter) - ord('A')
        col_offset = value_idx - key_idx + 1

        # 确定范围
        start_col = min(key_letter, value_letter)
        end_col = max(key_letter, value_letter)

        return f"VLOOKUP({lookup_value}, {table_name}!{start_col}:{end_col}, {col_offset}, FALSE)"

    def _generate_binary_op(self, op: str, left, right, row_placeholder: str) -> str:
        """生成二元运算"""
        left_str = self.generate_formula(left, row_placeholder)
        right_str = self.generate_formula(right, row_placeholder)

        # 运算符映射
        op_map = {
            "==": "=",
            "!=": "<>",
        }
        excel_op = op_map.get(op, op)

        return f"({left_str}{excel_op}{right_str})"


def generate_formulas(operations: List, tables: TableCollection) -> List[Dict]:
    """
    为操作列表生成 Excel 公式

    Args:
        operations: 操作列表
        tables: 表集合

    Returns:
        公式结果列表
    """
    generator = ExcelFormulaGenerator(tables)
    results = []

    for op in operations:
        if hasattr(op, 'formula') and isinstance(op.formula, dict):
            # add_column 操作
            formula_template = generator.generate_formula(op.formula)
            results.append({
                "type": "add_column",
                "table": op.table,
                "column_name": op.name,
                "formula_template": f"={formula_template}",
                "description": f"新增列: {op.name}"
            })
        elif hasattr(op, 'function'):
            # aggregate 操作
            results.append({
                "type": "aggregate",
                "variable": op.as_var,
                "formula": f"=聚合公式（{op.function}）",
                "description": f"聚合计算: {op.function}"
            })

    return results


def format_formula_output(formula_results: List[Dict]) -> str:
    """格式化公式输出"""
    lines = []
    lines.append("=" * 60)
    lines.append("Excel 复现公式")
    lines.append("=" * 60)

    for i, result in enumerate(formula_results, 1):
        op_type = result["type"]

        if op_type == "add_column":
            lines.append(f"\n{i}. {result['description']}")
            lines.append(f"   表: {result['table']}")
            lines.append(f"   公式模板: {result['formula_template']}")
            lines.append(f"   说明: 将 {{row}} 替换为行号（如 2, 3, 4...），下拉填充")

        elif op_type == "aggregate":
            lines.append(f"\n{i}. {result['description']}")
            lines.append(f"   变量: {result['variable']}")
            lines.append(f"   公式: {result['formula']}")

    return "\n".join(lines)
