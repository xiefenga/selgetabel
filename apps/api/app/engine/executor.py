"""执行引擎 - 执行操作并计算结果"""

from typing import Any, Dict, List, Optional, Union
import pandas as pd
from app.engine.models import (
    FileCollection,
    Table,
    Operation,
    AggregateOperation,
    AddColumnOperation,
    UpdateColumnOperation,
    ComputeOperation,
    FilterOperation,
    SortOperation,
    GroupByOperation,
    CreateSheetOperation,
    TakeOperation,
    ExecutionResult,
    OperationResult,
    ExcelError,
)
from app.engine.functions import (
    AGGREGATE_FUNC_MAP,
    ROW_FUNC_MAP,
    SCALAR_FUNC_MAP,
)


class FormulaEvaluator:
    """JSON 格式公式求值器"""

    def __init__(
        self,
        tables: FileCollection,
        functions: Dict[str, callable],
        row_context: Optional[Dict[str, Any]] = None,
        variables: Optional[Dict[str, Any]] = None,
    ):
        """
        初始化求值器

        Args:
            tables: 文件集合（用于跨表访问）
            functions: 可用函数
            row_context: 当前行的数据 {"列名": 值, ...}
            variables: 变量上下文 {"变量名": 值, ...}
        """
        self.tables = tables
        self.functions = functions
        self.row_context = row_context or {}
        self.variables = variables or {}

    def set_row_context(self, row_context: Dict[str, Any]):
        """设置当前行上下文（用于复用 evaluator）"""
        self.row_context = row_context

    def set_variables(self, variables: Dict[str, Any]):
        """设置变量上下文"""
        self.variables = variables

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

        # 变量引用: {"var": "变量名"}
        if "var" in expr:
            var_name = expr["var"]
            if var_name in self.variables:
                return self.variables[var_name]
            raise ValueError(f"未定义的变量: {var_name}")

        # 跨表引用: {"ref": "file_id.sheet_name.column_name"}
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
            ref: "file_id.sheet_name.column_name" 格式（三段式）

        Returns:
            列数据
        """
        parts = ref.split(".")
        if len(parts) != 3:
            raise ValueError(
                f"无效的跨表引用格式: {ref}，应为 'file_id.sheet_name.column_name'"
            )

        file_id, sheet_name, col_name = parts

        try:
            table = self.tables.get_table(file_id, sheet_name)
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

        args: [查找值, 表引用, 键列名, 值列名]
        - 表引用格式: "file_id.sheet_name"
        """
        if len(args) != 4:
            raise ValueError("VLOOKUP 需要 4 个参数")

        lookup_value = self.evaluate(args[0])
        table_ref = self.evaluate(args[1])  # "file_id.sheet_name"
        key_col = self.evaluate(args[2])
        value_col = self.evaluate(args[3])

        try:
            # 解析表引用
            parts = table_ref.split(".")
            if len(parts) != 2:
                raise ValueError(
                    f"无效的表引用格式: {table_ref}，应为 'file_id.sheet_name'"
                )
            file_id, sheet_name = parts

            # 获取表并查找
            table = self.tables.get_table(file_id, sheet_name)
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
        import pandas as pd
        from datetime import datetime, date

        left = self.evaluate(left_expr)
        right = self.evaluate(right_expr)

        # 处理空值（None 或 pandas NaT/NaN）
        def is_null(val):
            if val is None:
                return True
            if pd.isna(val):
                return True
            return False

        def is_numeric(val):
            """检查是否为数值类型（排除 bool）"""
            return isinstance(val, (int, float)) and not isinstance(val, bool)

        def is_datetime(val):
            return isinstance(val, (datetime, date, pd.Timestamp))

        def try_convert_to_number(val):
            """尝试将值转换为数值，返回 (成功, 结果)"""
            if is_numeric(val):
                return True, val
            if isinstance(val, str):
                try:
                    return True, float(val)
                except (ValueError, TypeError):
                    return False, val
            return False, val

        def safe_compare(a, b, compare_func) -> bool:
            """
            安全比较两个值，处理类型不匹配的情况

            比较策略（模拟 Excel 行为）：
            1. 空值：空值参与比较时返回 False
            2. 同类型：直接比较
            3. 数值 vs 字符串：尝试将字符串转为数值
            4. 无法比较：返回 False（而不是报错）
            """
            # 空值处理
            if is_null(a) or is_null(b):
                return False

            # 尝试将两边都转换为数值进行比较
            a_is_num, a_num = try_convert_to_number(a)
            b_is_num, b_num = try_convert_to_number(b)

            if a_is_num and b_is_num:
                # 两边都能转换为数值，用数值比较
                try:
                    return compare_func(a_num, b_num)
                except TypeError:
                    return False

            # 如果有一边是数值另一边是无法转换的字符串
            # Excel 行为：数值永远 < 文本
            if a_is_num and not b_is_num:
                # a 是数值，b 是文本：数值 < 文本
                if compare_func == (lambda x, y: x < y):
                    return True
                elif compare_func == (lambda x, y: x > y):
                    return False
                elif compare_func == (lambda x, y: x <= y):
                    return True
                elif compare_func == (lambda x, y: x >= y):
                    return False
                return False

            if not a_is_num and b_is_num:
                # a 是文本，b 是数值：文本 > 数值
                if compare_func == (lambda x, y: x < y):
                    return False
                elif compare_func == (lambda x, y: x > y):
                    return True
                elif compare_func == (lambda x, y: x <= y):
                    return False
                elif compare_func == (lambda x, y: x >= y):
                    return True
                return False

            # 两边都是字符串，用字符串比较
            try:
                return compare_func(str(a), str(b))
            except TypeError:
                return False

        # 错误传播：如果任一操作数是 ExcelError，直接返回该错误
        if isinstance(left, ExcelError):
            return left
        if isinstance(right, ExcelError):
            return right

        # 对于算术运算，检查空值和类型
        arithmetic_ops = {"+", "-", "*", "/"}
        if op in arithmetic_ops:
            # 检查空值
            if is_null(left) or is_null(right):
                return ExcelError("#VALUE!")

            if is_datetime(left) or is_datetime(right):
                return ExcelError("#VALUE!")

            if not is_numeric(left) or not is_numeric(right):
                # 尝试转换字符串为数字
                try:
                    if isinstance(left, str):
                        left = float(left)
                    if isinstance(right, str):
                        right = float(right)
                except (ValueError, TypeError):
                    return ExcelError("#VALUE!")

        # 比较运算符需要特殊处理类型不匹配
        comparison_ops = {">", "<", ">=", "<="}
        if op in comparison_ops:
            compare_funcs = {
                ">": lambda x, y: x > y,
                "<": lambda x, y: x < y,
                ">=": lambda x, y: x >= y,
                "<=": lambda x, y: x <= y,
            }
            return safe_compare(left, right, compare_funcs[op])

        ops = {
            "+": lambda a, b: a + b,
            "-": lambda a, b: a - b,
            "*": lambda a, b: a * b,
            "/": lambda a, b: a / b if b != 0 else ExcelError("#DIV/0!"),
            "=": lambda a, b: a == b,   # Excel 风格的等于运算符
            "<>": lambda a, b: a != b,  # Excel 风格的不等于运算符
            "&": lambda a, b: str(a if not is_null(a) else "") + str(b if not is_null(b) else ""),  # 文本拼接运算符
        }

        if op not in ops:
            raise ValueError(f"未知的运算符: {op}")

        return ops[op](left, right)


class Executor:
    """操作执行引擎"""

    def __init__(self, tables: FileCollection):
        self.tables = tables
        self.variables: Dict[str, Any] = {}

    def execute(self, operations: List[Operation]) -> ExecutionResult:
        """执行操作列表"""
        result = ExecutionResult()

        for i, op in enumerate(operations):
            try:
                op_result = self._execute_operation(op)
                result.operation_results.append(op_result)

                # 记录错误（如果有）
                if op_result.error:
                    result.add_error(f"操作 #{i + 1}: {op_result.error}")

                # 处理操作结果 - 注意：对于 add_column/update_column，即使有部分行错误，
                # 只要有值就应该继续处理，因为错误行已经用 ExcelError 填充
                has_value = op_result.value is not None

                if isinstance(op, (AggregateOperation, ComputeOperation)):
                    if has_value and not op_result.error:
                        var_name = op.as_var
                        self.variables[var_name] = op_result.value
                        result.add_variable(var_name, op_result.value)

                # 对于 add_column，即使有部分行错误也应该创建列
                # （错误行已经用 ExcelError("#ERROR") 或 ExcelError("#VALUE!") 填充）
                if isinstance(op, AddColumnOperation):
                    if has_value:
                        # 三层结构：file_id -> sheet_name -> column_name -> values
                        result.add_column(op.file_id, op.table, op.name, op_result.value)
                        # 立即将新列应用到表中，以便后续操作可以引用
                        self._apply_new_column(op.file_id, op.table, op.name, op_result.value)

                # 对于 update_column，同样即使有部分行错误也应该更新列
                if isinstance(op, UpdateColumnOperation):
                    if has_value:
                        # 三层结构：file_id -> sheet_name -> column_name -> values
                        result.add_updated_column(op.file_id, op.table, op.column, op_result.value)
                        # 立即将更新后的列应用到表中，以便后续操作可以引用
                        self._apply_updated_column(op.file_id, op.table, op.column, op_result.value)

                # 处理新创建的 Sheet（filter, sort, group_by, create_sheet, take）
                if isinstance(op, (FilterOperation, SortOperation, GroupByOperation, CreateSheetOperation, TakeOperation)):
                    if has_value and isinstance(op_result.value, dict):
                        sheet_data = op_result.value
                        if "sheet_name" in sheet_data and "data" in sheet_data:
                            result.add_new_sheet(
                                sheet_data["file_id"],
                                sheet_data["sheet_name"],
                                sheet_data["data"]
                            )
                            # 同时将新 Sheet 应用到 tables，以便后续操作可以引用
                            self._apply_new_sheet(
                                sheet_data["file_id"],
                                sheet_data["sheet_name"],
                                sheet_data["data"]
                            )

            except Exception as e:
                error_msg = f"执行错误: {str(e)}"
                result.add_error(f"操作 #{i + 1}: {error_msg}")
                result.operation_results.append(
                    OperationResult(operation=op, error=error_msg)
                )

        return result

    def _apply_new_sheet(self, file_id: str, sheet_name: str, data: pd.DataFrame):
        """将新创建的 Sheet 立即应用到 tables，以便后续操作可以引用"""
        if self.tables.has_file(file_id):
            excel_file = self.tables.get_file(file_id)
            table = Table(name=sheet_name, data=data)
            if excel_file.has_sheet(sheet_name):
                # 替换现有 sheet
                excel_file._sheets[sheet_name] = table
            else:
                excel_file.add_sheet(table)

    def _apply_new_column(self, file_id: str, table_name: str, column_name: str, values: List[Any]):
        """将新列立即应用到表中，以便后续操作可以引用"""
        table = self.tables.get_table(file_id, table_name)
        # 如果列已存在则更新，否则添加（处理重复执行的情况）
        if column_name in table.get_columns():
            table.update_column(column_name, values)
        else:
            table.add_column(column_name, values)

    def _apply_updated_column(self, file_id: str, table_name: str, column_name: str, values: List[Any]):
        """将更新后的列立即应用到表中，以便后续操作可以引用"""
        table = self.tables.get_table(file_id, table_name)
        table.update_column(column_name, values)

    def _execute_operation(self, op: Operation) -> OperationResult:
        """执行单个操作"""
        if isinstance(op, AggregateOperation):
            return self._execute_aggregate(op)
        elif isinstance(op, AddColumnOperation):
            return self._execute_add_column(op)
        elif isinstance(op, UpdateColumnOperation):
            return self._execute_update_column(op)
        elif isinstance(op, ComputeOperation):
            return self._execute_compute(op)
        elif isinstance(op, FilterOperation):
            return self._execute_filter(op)
        elif isinstance(op, SortOperation):
            return self._execute_sort(op)
        elif isinstance(op, GroupByOperation):
            return self._execute_group_by(op)
        elif isinstance(op, CreateSheetOperation):
            return self._execute_create_sheet(op)
        elif isinstance(op, TakeOperation):
            return self._execute_take(op)
        else:
            return OperationResult(
                operation=op,
                error=f"未知操作类型: {type(op).__name__}"
            )

    def _execute_aggregate(self, op: AggregateOperation) -> OperationResult:
        """执行聚合操作"""
        try:
            # 使用 file_id 和 table（sheet_name）获取表
            table = self.tables.get_table(op.file_id, op.table)
            func = AGGREGATE_FUNC_MAP.get(op.function)

            if not func:
                return OperationResult(
                    operation=op,
                    error=f"未知聚合函数: {op.function}"
                )

            if op.function in {"SUM", "COUNT", "COUNTA", "AVERAGE", "MIN", "MAX", "MEDIAN"}:
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
        """
        执行新增列操作

        优化点：
        1. 预先缓存所有列数据，避免每行重复获取
        2. 复用 FormulaEvaluator 实例
        3. 支持变量引用
        4. 详细的行级错误报告
        5. 不直接修改 Table（由调用方统一应用）
        """
        try:
            # 使用 file_id 和 table（sheet_name）获取表
            table = self.tables.get_table(op.file_id, op.table)
            row_count = table.row_count()
            columns = table.get_columns()

            # ✅ 优化 1: 预先缓存所有列数据
            column_cache: Dict[str, List[Any]] = {
                col_name: table.get_column(col_name)
                for col_name in columns
            }

            # ✅ 优化 2: 复用 FormulaEvaluator 实例
            evaluator = FormulaEvaluator(
                tables=self.tables,
                functions=ROW_FUNC_MAP,
                variables=self.variables,  # ✅ 支持变量引用
            )

            column_values = []
            row_errors = []  # ✅ 优化 4: 记录行级错误

            # 为每一行计算值
            for row_idx in range(row_count):
                # 构建行上下文（直接从缓存获取，避免重复调用 get_column）
                row_context = {
                    col_name: column_cache[col_name][row_idx]
                    for col_name in columns
                }

                # 设置行上下文（复用 evaluator）
                evaluator.set_row_context(row_context)

                try:
                    value = evaluator.evaluate(op.formula)
                    column_values.append(value)
                except Exception as e:
                    column_values.append(ExcelError("#ERROR"))
                    row_errors.append(f"行 {row_idx + 2}: {str(e)}")

            # ✅ 优化 5: 不直接修改 Table，由调用方统一应用
            # （移除了 table.add_column(op.name, column_values)）

            # 构建结果
            result = OperationResult(operation=op, value=column_values)

            # 如果有行级错误，记录到 error 字段
            if row_errors:
                max_display = 5
                error_summary = "; ".join(row_errors[:max_display])
                if len(row_errors) > max_display:
                    error_summary += f" (共 {len(row_errors)} 个错误)"
                result.error = f"部分行计算失败: {error_summary}"

            return result

        except Exception as e:
            return OperationResult(operation=op, error=str(e))

    def _execute_update_column(self, op: UpdateColumnOperation) -> OperationResult:
        """
        执行更新列操作

        与 add_column 类似，但用于更新现有列（如空值填充）。
        """
        try:
            # 使用 file_id 和 table（sheet_name）获取表
            table = self.tables.get_table(op.file_id, op.table)
            row_count = table.row_count()
            columns = table.get_columns()

            # 检查目标列是否存在
            if op.column not in columns:
                return OperationResult(
                    operation=op,
                    error=f"列 '{op.column}' 不存在，无法更新"
                )

            # 预先缓存所有列数据
            column_cache: Dict[str, List[Any]] = {
                col_name: table.get_column(col_name)
                for col_name in columns
            }

            # 复用 FormulaEvaluator 实例
            evaluator = FormulaEvaluator(
                tables=self.tables,
                functions=ROW_FUNC_MAP,
                variables=self.variables,
            )

            column_values = []
            row_errors = []

            # 为每一行计算值
            for row_idx in range(row_count):
                # 构建行上下文
                row_context = {
                    col_name: column_cache[col_name][row_idx]
                    for col_name in columns
                }

                # 设置行上下文
                evaluator.set_row_context(row_context)

                try:
                    value = evaluator.evaluate(op.formula)
                    column_values.append(value)
                except Exception as e:
                    column_values.append(ExcelError("#ERROR"))
                    row_errors.append(f"行 {row_idx + 2}: {str(e)}")

            # 构建结果
            result = OperationResult(operation=op, value=column_values)

            # 如果有行级错误，记录到 error 字段
            if row_errors:
                max_display = 5
                error_summary = "; ".join(row_errors[:max_display])
                if len(row_errors) > max_display:
                    error_summary += f" (共 {len(row_errors)} 个错误)"
                result.error = f"部分行计算失败: {error_summary}"

            return result

        except Exception as e:
            return OperationResult(operation=op, error=str(e))

    def _execute_compute(self, op: ComputeOperation) -> OperationResult:
        """
        执行标量运算

        改进：
        1. 移除 eval 兼容代码，强制要求 JSON 格式
        2. 使用 FormulaEvaluator 统一处理
        """
        try:
            # 检查 expression 格式
            if not isinstance(op.expression, dict):
                return OperationResult(
                    operation=op,
                    error="expression 必须是 JSON 对象格式，不支持字符串表达式"
                )

            # 使用 FormulaEvaluator 计算
            evaluator = FormulaEvaluator(
                tables=self.tables,
                functions=SCALAR_FUNC_MAP,
                variables=self.variables,  # 支持变量引用
            )
            value = evaluator.evaluate(op.expression)

            return OperationResult(operation=op, value=value)

        except Exception as e:
            return OperationResult(operation=op, error=str(e))

    # ==================== 新增操作执行方法（Excel 365+）====================

    def _execute_filter(self, op: FilterOperation) -> OperationResult:
        """
        执行筛选操作

        使用 pandas 实现，对应 Excel 365 的 FILTER 函数
        """
        try:
            table = self.tables.get_table(op.file_id, op.table)
            df = table.get_data()

            # 构建筛选条件
            conditions = []
            for cond in op.conditions:
                col = cond["column"]
                operator = cond["op"]
                value = cond["value"]

                if col not in df.columns:
                    return OperationResult(
                        operation=op,
                        error=f"列 '{col}' 不存在于表 '{op.table}'"
                    )

                # 获取列数据
                col_data = df[col]

                # 对于比较运算符，需要处理混合类型
                if operator in {">", "<", ">=", "<="}:
                    # 尝试将列转换为数值类型进行比较
                    # 如果 value 是数值，尝试将列转换为数值
                    if isinstance(value, (int, float)):
                        col_numeric = pd.to_numeric(col_data, errors="coerce")
                        if operator == ">":
                            conditions.append(col_numeric > value)
                        elif operator == "<":
                            conditions.append(col_numeric < value)
                        elif operator == ">=":
                            conditions.append(col_numeric >= value)
                        elif operator == "<=":
                            conditions.append(col_numeric <= value)
                    else:
                        # value 是字符串，进行字符串比较
                        col_str = col_data.astype(str)
                        value_str = str(value)
                        if operator == ">":
                            conditions.append(col_str > value_str)
                        elif operator == "<":
                            conditions.append(col_str < value_str)
                        elif operator == ">=":
                            conditions.append(col_str >= value_str)
                        elif operator == "<=":
                            conditions.append(col_str <= value_str)
                elif operator == "=":
                    # 等于比较：尝试类型转换后比较
                    if isinstance(value, (int, float)):
                        # 尝试将列转换为数值比较
                        col_numeric = pd.to_numeric(col_data, errors="coerce")
                        # 同时检查原始值相等或数值相等
                        conditions.append((col_data == value) | (col_numeric == value))
                    else:
                        conditions.append(col_data == value)
                elif operator == "<>":
                    conditions.append(col_data != value)
                elif operator == "contains":
                    conditions.append(col_data.astype(str).str.contains(str(value), na=False))
                else:
                    return OperationResult(
                        operation=op,
                        error=f"不支持的运算符: {operator}"
                    )

            # 组合条件
            if len(conditions) == 0:
                return OperationResult(operation=op, error="没有有效的筛选条件")

            if op.logic == "AND":
                combined = conditions[0]
                for c in conditions[1:]:
                    combined = combined & c
            else:  # OR
                combined = conditions[0]
                for c in conditions[1:]:
                    combined = combined | c

            # 应用筛选
            filtered_df = df[combined].reset_index(drop=True)

            # 确定输出
            output_type = op.output.get("type", "new_sheet")
            if output_type == "new_sheet":
                output_name = op.output["name"]
            else:
                output_name = op.table

            return OperationResult(
                operation=op,
                value={
                    "file_id": op.file_id,
                    "sheet_name": output_name,
                    "data": filtered_df,
                    "row_count": len(filtered_df)
                }
            )

        except Exception as e:
            return OperationResult(operation=op, error=str(e))

    def _execute_sort(self, op: SortOperation) -> OperationResult:
        """
        执行排序操作

        使用 pandas 实现，对应 Excel 365 的 SORT 函数
        """
        try:
            table = self.tables.get_table(op.file_id, op.table)
            df = table.get_data().copy()  # 复制一份，避免修改原数据

            # 构建排序参数
            sort_columns = []
            sort_ascending = []

            for rule in op.by:
                col = rule["column"]
                order = rule.get("order", "asc")

                if col not in df.columns:
                    return OperationResult(
                        operation=op,
                        error=f"列 '{col}' 不存在于表 '{op.table}'"
                    )

                sort_columns.append(col)
                sort_ascending.append(order == "asc")

            # 处理混合类型列的排序问题
            # 对于 object 类型的列，尝试转换为数值类型
            for col in sort_columns:
                if df[col].dtype == "object":
                    # 尝试转换为数值，无法转换的保持原值
                    numeric_col = pd.to_numeric(df[col], errors="coerce")
                    # 如果超过 50% 的值能转换为数值，则使用数值排序
                    non_null_count = numeric_col.notna().sum()
                    total_count = len(df[col])
                    if total_count > 0 and non_null_count / total_count > 0.5:
                        # 创建一个辅助列用于排序
                        # 数值放前面，非数值转为字符串放后面
                        df[f"_sort_{col}"] = numeric_col.fillna(float("inf"))
                        # 替换排序列
                        sort_columns = [f"_sort_{col}" if c == col else c for c in sort_columns]

            # 执行排序
            try:
                sorted_df = df.sort_values(
                    by=sort_columns,
                    ascending=sort_ascending
                ).reset_index(drop=True)
            except TypeError as e:
                # 如果还是报类型错误，回退到字符串排序
                for col in sort_columns:
                    if col.startswith("_sort_"):
                        continue
                    df[col] = df[col].astype(str)
                sorted_df = df.sort_values(
                    by=sort_columns,
                    ascending=sort_ascending
                ).reset_index(drop=True)

            # 删除辅助排序列
            cols_to_drop = [c for c in sorted_df.columns if c.startswith("_sort_")]
            if cols_to_drop:
                sorted_df = sorted_df.drop(columns=cols_to_drop)

            # 确定输出
            output_type = op.output.get("type", "in_place") if op.output else "in_place"
            if output_type == "new_sheet":
                output_name = op.output["name"]
            else:
                output_name = op.table

            return OperationResult(
                operation=op,
                value={
                    "file_id": op.file_id,
                    "sheet_name": output_name,
                    "data": sorted_df,
                    "row_count": len(sorted_df)
                }
            )

        except Exception as e:
            return OperationResult(operation=op, error=str(e))

    def _execute_group_by(self, op: GroupByOperation) -> OperationResult:
        """
        执行分组聚合操作

        使用 pandas 实现，对应 Excel 365 的 GROUPBY 函数
        """
        try:
            table = self.tables.get_table(op.file_id, op.table)
            df = table.get_data()

            # 验证分组列
            for col in op.group_columns:
                if col not in df.columns:
                    return OperationResult(
                        operation=op,
                        error=f"分组列 '{col}' 不存在于表 '{op.table}'"
                    )

            # 构建聚合字典
            agg_dict = {}
            rename_dict = {}

            for agg in op.aggregations:
                col = agg["column"]
                func = agg["function"].lower()
                as_name = agg["as"]

                if col not in df.columns:
                    return OperationResult(
                        operation=op,
                        error=f"聚合列 '{col}' 不存在于表 '{op.table}'"
                    )

                # pandas 聚合函数映射
                func_map = {
                    "sum": "sum",
                    "count": "count",
                    "average": "mean",
                    "min": "min",
                    "max": "max",
                    "median": "median"
                }

                if func not in func_map:
                    return OperationResult(
                        operation=op,
                        error=f"不支持的聚合函数: {func}"
                    )

                agg_dict[col] = func_map[func]
                rename_dict[col] = as_name

            # 数值聚合函数需要数值类型的列，自动转换 object 类型
            numeric_agg_funcs = {"sum", "mean", "min", "max", "median"}
            for col, pandas_func in agg_dict.items():
                if pandas_func in numeric_agg_funcs and df[col].dtype == "object":
                    # 尝试将 object 类型转换为数值，无法转换的值变成 NaN
                    df[col] = pd.to_numeric(df[col], errors="coerce")

            # 执行分组聚合
            grouped_df = df.groupby(op.group_columns, as_index=False).agg(agg_dict)

            # 重命名聚合列
            grouped_df = grouped_df.rename(columns=rename_dict)

            # 输出
            output_name = op.output["name"]

            return OperationResult(
                operation=op,
                value={
                    "file_id": op.file_id,
                    "sheet_name": output_name,
                    "data": grouped_df,
                    "row_count": len(grouped_df)
                }
            )

        except Exception as e:
            return OperationResult(operation=op, error=str(e))

    def _execute_create_sheet(self, op: CreateSheetOperation) -> OperationResult:
        """
        执行创建 Sheet 操作

        支持三种模式：
        - empty: 创建空表（可指定列头）
        - copy: 复制现有表
        - reference: 引用现有表结构（创建空表但列结构相同）
        """
        try:
            source_type = op.source.get("type", "empty") if op.source else "empty"

            if source_type == "empty":
                # 创建空表
                if op.columns:
                    df = pd.DataFrame(columns=op.columns)
                else:
                    df = pd.DataFrame()

            elif source_type == "copy":
                # 复制现有表
                source_table = op.source.get("table")
                if not source_table:
                    return OperationResult(
                        operation=op,
                        error="copy 模式需要指定 source.table"
                    )
                table = self.tables.get_table(op.file_id, source_table)
                df = table.get_data()

            elif source_type == "reference":
                # 引用结构（创建空表但列结构相同）
                source_table = op.source.get("table")
                if not source_table:
                    return OperationResult(
                        operation=op,
                        error="reference 模式需要指定 source.table"
                    )
                table = self.tables.get_table(op.file_id, source_table)
                columns = table.get_columns()
                df = pd.DataFrame(columns=columns)

            else:
                return OperationResult(
                    operation=op,
                    error=f"不支持的 source.type: {source_type}"
                )

            return OperationResult(
                operation=op,
                value={
                    "file_id": op.file_id,
                    "sheet_name": op.name,
                    "data": df,
                    "row_count": len(df)
                }
            )

        except Exception as e:
            return OperationResult(operation=op, error=str(e))

    def _execute_take(self, op: TakeOperation) -> OperationResult:
        """
        执行取前/后 N 行操作

        使用 pandas 实现，对应 Excel 365 的 TAKE 函数
        - rows > 0: 从开头取 N 行（head）
        - rows < 0: 从末尾取 N 行（tail）
        """
        try:
            table = self.tables.get_table(op.file_id, op.table)
            df = table.get_data()

            # 执行取行操作
            if op.rows > 0:
                # 取前 N 行
                result_df = df.head(op.rows).reset_index(drop=True)
            else:
                # 取后 N 行（rows 为负数）
                result_df = df.tail(abs(op.rows)).reset_index(drop=True)

            # 确定输出
            output_type = op.output.get("type", "in_place") if op.output else "in_place"
            if output_type == "new_sheet":
                output_name = op.output["name"]
            else:
                output_name = op.table

            return OperationResult(
                operation=op,
                value={
                    "file_id": op.file_id,
                    "sheet_name": output_name,
                    "data": result_df,
                    "row_count": len(result_df)
                }
            )

        except Exception as e:
            return OperationResult(operation=op, error=str(e))


def execute_operations(operations: List[Operation], tables: FileCollection) -> ExecutionResult:
    """执行操作的便捷函数"""
    executor = Executor(tables)
    return executor.execute(operations)
