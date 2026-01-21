"""执行引擎 - 执行操作并计算结果"""

from typing import Any, Dict, List, Union
from app.core.models import (
    TableCollection,
    Operation,
    AggregateOperation,
    AddColumnOperation,
    ComputeOperation,
    ExecutionResult,
    OperationResult,
    ExcelError,
)
from app.core.functions import (
    AGGREGATE_FUNC_MAP,
    ROW_FUNC_MAP,
    SCALAR_FUNC_MAP,
)


class FormulaEvaluator:
    """JSON 格式公式求值器"""

    def __init__(
        self,
        row_context: Dict[str, Any],
        tables: TableCollection,
        functions: Dict[str, callable]
    ):
        """
        初始化求值器

        Args:
            row_context: 当前行的数据 {"列名": 值, ...}
            tables: 表集合（用于跨表访问）
            functions: 可用函数
        """
        self.row_context = row_context
        self.tables = tables
        self.functions = functions

    def evaluate(self, expr: Union[Dict, Any]) -> Any:
        """
        求值表达式

        Args:
            expr: 表达式对象或原始值

        Returns:
            计算结果
        """
        # 如果不是字典，直接返回（兼容旧格式）
        if not isinstance(expr, dict):
            return expr

        # 字面量: {"value": ...}
        if "value" in expr:
            return expr["value"]

        # 列引用: {"col": "列名"}
        if "col" in expr:
            col_name = expr["col"]
            if col_name in self.row_context:
                return self.row_context[col_name]
            raise ValueError(f"未知的列名: {col_name}")

        # 跨表引用: {"ref": "表名.列名"}
        if "ref" in expr:
            return self._get_table_column(expr["ref"])

        # 函数调用: {"func": "IF", "args": [...]}
        if "func" in expr:
            return self._eval_function(expr["func"], expr.get("args", []))

        # 二元运算: {"op": ">", "left": {...}, "right": {...}}
        if "op" in expr:
            return self._eval_binary_op(expr["op"], expr["left"], expr["right"])

        raise ValueError(f"未知的表达式类型: {expr}")

    def _get_table_column(self, ref: str) -> List[Any]:
        """
        获取跨表列引用

        Args:
            ref: "表名.列名" 格式

        Returns:
            列数据
        """
        if "." not in ref:
            raise ValueError(f"无效的跨表引用格式: {ref}")

        parts = ref.split(".", 1)
        table_name = parts[0]
        col_name = parts[1]

        try:
            table = self.tables.get_table(table_name)
            return table.get_column(col_name)
        except Exception as e:
            raise ValueError(f"无法访问 {ref}: {e}")

    def _eval_function(self, func_name: str, args: List) -> Any:
        """求值函数调用"""
        func_name_upper = func_name.upper()

        # 特殊处理 IF（短路求值）
        if func_name_upper == "IF":
            return self._eval_if(args)

        # 特殊处理 AND/OR（短路求值）
        if func_name_upper == "AND":
            return self._eval_and(args)
        if func_name_upper == "OR":
            return self._eval_or(args)

        # 特殊处理 COUNTIFS
        if func_name_upper == "COUNTIFS":
            return self._eval_countifs(args)

        # 特殊处理 VLOOKUP
        if func_name_upper == "VLOOKUP":
            return self._eval_vlookup(args)

        # 其他函数：先求值所有参数
        evaluated_args = [self.evaluate(arg) for arg in args]

        if func_name_upper in self.functions:
            return self.functions[func_name_upper](*evaluated_args)

        raise ValueError(f"未知的函数: {func_name}")

    def _eval_if(self, args: List) -> Any:
        """求值 IF 函数"""
        if len(args) != 3:
            raise ValueError("IF 需要 3 个参数")

        condition = self.evaluate(args[0])
        if condition:
            return self.evaluate(args[1])
        else:
            return self.evaluate(args[2])

    def _eval_and(self, args: List) -> bool:
        """求值 AND 函数"""
        for arg in args:
            if not self.evaluate(arg):
                return False
        return True

    def _eval_or(self, args: List) -> bool:
        """求值 OR 函数"""
        for arg in args:
            if self.evaluate(arg):
                return True
        return False

    def _eval_countifs(self, args: List) -> int:
        """
        求值 COUNTIFS 函数

        args 格式: [范围1, 条件1, 范围2, 条件2, ...]
        范围是 {"ref": "表.列"}，条件是 {"col": "列名"} 或 {"value": ...}
        """
        if len(args) % 2 != 0 or len(args) < 2:
            raise ValueError("COUNTIFS 参数必须成对出现")

        # 收集范围和条件
        ranges = []
        criteria = []

        for i in range(0, len(args), 2):
            range_expr = args[i]
            criteria_expr = args[i + 1]

            # 范围必须是跨表引用
            range_data = self.evaluate(range_expr)
            if not isinstance(range_data, list):
                raise ValueError("COUNTIFS 的范围参数必须是跨表引用 {\"ref\": \"表.列\"}")
            ranges.append(range_data)

            # 条件可以是列引用或字面量
            criteria_value = self.evaluate(criteria_expr)
            criteria.append(criteria_value)

        # 检查所有范围长度一致
        first_len = len(ranges[0])
        for r in ranges:
            if len(r) != first_len:
                raise ValueError("COUNTIFS 所有范围长度必须一致")

        # 统计满足所有条件的行数
        count = 0
        for row_idx in range(first_len):
            all_match = True
            for range_data, criterion in zip(ranges, criteria):
                if range_data[row_idx] != criterion:
                    all_match = False
                    break
            if all_match:
                count += 1

        return count

    def _eval_vlookup(self, args: List) -> Any:
        """
        求值 VLOOKUP 函数

        args: [查找值, 目标表名, 键列名, 值列名]
        """
        if len(args) != 4:
            raise ValueError("VLOOKUP 需要 4 个参数")

        lookup_value = self.evaluate(args[0])
        table_name = self.evaluate(args[1])
        key_col = self.evaluate(args[2])
        value_col = self.evaluate(args[3])

        try:
            table = self.tables.get_table(table_name)
            key_data = table.get_column(key_col)
            value_data = table.get_column(value_col)

            for i, key in enumerate(key_data):
                if key == lookup_value:
                    return value_data[i]

            return ExcelError("#N/A")
        except Exception:
            return ExcelError("#N/A")

    def _eval_binary_op(self, op: str, left_expr, right_expr) -> Any:
        """求值二元运算"""
        left = self.evaluate(left_expr)
        right = self.evaluate(right_expr)

        ops = {
            "+": lambda a, b: a + b,
            "-": lambda a, b: a - b,
            "*": lambda a, b: a * b,
            "/": lambda a, b: a / b if b != 0 else ExcelError("#DIV/0!"),
            ">": lambda a, b: a > b,
            "<": lambda a, b: a < b,
            ">=": lambda a, b: a >= b,
            "<=": lambda a, b: a <= b,
            "==": lambda a, b: a == b,
            "!=": lambda a, b: a != b,
        }

        if op not in ops:
            raise ValueError(f"未知的运算符: {op}")

        return ops[op](left, right)


class Executor:
    """操作执行引擎"""

    def __init__(self, tables: TableCollection):
        self.tables = tables
        self.variables: Dict[str, Any] = {}

    def execute(self, operations: List[Operation]) -> ExecutionResult:
        """执行操作列表"""
        result = ExecutionResult()

        for i, op in enumerate(operations):
            try:
                op_result = self._execute_operation(op)
                result.operation_results.append(op_result)

                if op_result.error:
                    result.add_error(f"操作 #{i + 1}: {op_result.error}")
                else:
                    if isinstance(op, (AggregateOperation, ComputeOperation)):
                        var_name = op.as_var
                        self.variables[var_name] = op_result.value
                        result.add_variable(var_name, op_result.value)

                    if isinstance(op, AddColumnOperation):
                        result.add_column(op.table, op.name, op_result.value)

            except Exception as e:
                error_msg = f"执行错误: {str(e)}"
                result.add_error(f"操作 #{i + 1}: {error_msg}")
                result.operation_results.append(
                    OperationResult(operation=op, error=error_msg)
                )

        return result

    def _execute_operation(self, op: Operation) -> OperationResult:
        """执行单个操作"""
        if isinstance(op, AggregateOperation):
            return self._execute_aggregate(op)
        elif isinstance(op, AddColumnOperation):
            return self._execute_add_column(op)
        elif isinstance(op, ComputeOperation):
            return self._execute_compute(op)
        else:
            return OperationResult(
                operation=op,
                error=f"未知操作类型: {type(op).__name__}"
            )

    def _execute_aggregate(self, op: AggregateOperation) -> OperationResult:
        """执行聚合操作"""
        try:
            table = self.tables.get_table(op.table)
            func = AGGREGATE_FUNC_MAP.get(op.function)

            if not func:
                return OperationResult(
                    operation=op,
                    error=f"未知聚合函数: {op.function}"
                )

            if op.function in {"SUM", "COUNT", "COUNTA", "AVERAGE", "MIN", "MAX"}:
                column_data = table.get_column(op.column)
                value = func(column_data)

            elif op.function == "SUMIF":
                sum_range = table.get_column(op.column)
                criteria_range = table.get_column(op.condition_column)
                value = func(sum_range, criteria_range, op.condition)

            elif op.function == "COUNTIF":
                criteria_range = table.get_column(op.condition_column)
                value = func(criteria_range, op.condition)

            elif op.function == "AVERAGEIF":
                avg_range = table.get_column(op.column)
                criteria_range = table.get_column(op.condition_column)
                value = func(avg_range, criteria_range, op.condition)

            else:
                return OperationResult(
                    operation=op,
                    error=f"未实现的聚合函数: {op.function}"
                )

            return OperationResult(operation=op, value=value)

        except Exception as e:
            return OperationResult(operation=op, error=str(e))

    def _execute_add_column(self, op: AddColumnOperation) -> OperationResult:
        """执行新增列操作"""
        try:
            table = self.tables.get_table(op.table)
            row_count = table.row_count()
            column_values = []
            columns = table.get_columns()

            # 为每一行计算值
            for row_idx in range(row_count):
                # 构建行上下文
                row_context = {}
                for col_name in columns:
                    col_data = table.get_column(col_name)
                    row_context[col_name] = col_data[row_idx]

                # 使用 FormulaEvaluator 计算
                try:
                    evaluator = FormulaEvaluator(
                        row_context,
                        self.tables,
                        ROW_FUNC_MAP
                    )
                    value = evaluator.evaluate(op.formula)
                    column_values.append(value)
                except Exception as e:
                    column_values.append(ExcelError(f"#ERROR: {str(e)}"))

            # 将新列添加到表中
            table.add_column(op.name, column_values)

            return OperationResult(operation=op, value=column_values)

        except Exception as e:
            return OperationResult(operation=op, error=str(e))

    def _execute_compute(self, op: ComputeOperation) -> OperationResult:
        """执行标量运算"""
        try:
            # compute 的 expression 也可以是 JSON 格式
            if isinstance(op.expression, dict):
                evaluator = FormulaEvaluator({}, self.tables, SCALAR_FUNC_MAP)
                # 添加变量到上下文
                evaluator.row_context = self.variables.copy()
                value = evaluator.evaluate(op.expression)
            else:
                # 兼容旧的字符串格式
                safe_env = {**self.variables, **SCALAR_FUNC_MAP}
                value = eval(op.expression, {"__builtins__": {}}, safe_env)

            return OperationResult(operation=op, value=value)

        except Exception as e:
            return OperationResult(operation=op, error=str(e))


def execute_operations(operations: List[Operation], tables: TableCollection) -> ExecutionResult:
    """执行操作的便捷函数"""
    executor = Executor(tables)
    return executor.execute(operations)
