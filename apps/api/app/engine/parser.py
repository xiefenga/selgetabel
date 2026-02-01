"""JSON 解析器 - 解析和校验 LLM 输出的操作描述"""

import json
from typing import List, Dict, Any, Tuple, Optional, Set
from app.engine.models import (
    AggregateOperation,
    AddColumnOperation,
    UpdateColumnOperation,
    ComputeOperation,
    FilterOperation,
    SortOperation,
    GroupByOperation,
    CreateSheetOperation,
    TakeOperation,
    Operation,
)


# ==================== 白名单定义 ====================

# 聚合函数白名单
AGGREGATE_FUNCTIONS = {
    "SUM", "COUNT", "COUNTA", "AVERAGE", "MIN", "MAX", "MEDIAN",
    "SUMIF", "COUNTIF", "AVERAGEIF"
}

# 行级函数白名单（用于 add_column 的 formula）
ROW_FUNCTIONS = {
    # 逻辑
    "IF", "AND", "OR", "NOT",
    # 空值判断
    "ISBLANK", "ISNA", "ISNUMBER", "ISERROR",
    # 查找
    "VLOOKUP",
    # 错误处理
    "IFERROR",
    # 数值
    "ROUND", "ABS",
    # 文本
    "LEFT", "RIGHT", "MID", "LEN", "TRIM", "UPPER", "LOWER", "PROPER",
    "CONCAT", "TEXT", "VALUE", "SUBSTITUTE",
    # 文本查找
    "FIND", "SEARCH",
    # 多条件计数
    "COUNTIFS"
}

# 标量函数白名单（用于 compute 的 expression）
SCALAR_FUNCTIONS = {
    "ROUND", "ABS", "MAX", "MIN"
}

# 操作类型
VALID_TYPES = {
    "aggregate", "add_column", "update_column", "compute",
    "filter", "sort", "group_by", "create_sheet", "take"
}

# 筛选条件运算符
FILTER_OPERATORS = {"=", "<>", ">", "<", ">=", "<=", "contains"}

# 分组聚合函数
GROUPBY_FUNCTIONS = {"SUM", "COUNT", "AVERAGE", "MIN", "MAX"}


# ==================== 表达式验证器 ====================


class ExpressionValidator:
    """
    表达式验证器 - 递归验证表达式结构和函数白名单

    用于在解析阶段就发现不支持的函数，而不是等到执行时才报错。
    """

    def __init__(self, allowed_functions: set):
        """
        初始化验证器

        Args:
            allowed_functions: 允许的函数集合
        """
        self.allowed_functions = allowed_functions

    def validate(self, expr: Any, prefix: str = "") -> List[str]:
        """
        验证表达式

        Args:
            expr: 表达式对象
            prefix: 错误信息前缀

        Returns:
            错误列表
        """
        errors = []
        self._validate_recursive(expr, errors, prefix)
        return errors

    def _validate_recursive(self, expr: Any, errors: List[str], prefix: str):
        """递归验证表达式"""
        if not isinstance(expr, dict):
            return

        # 验证函数调用
        if "func" in expr:
            func_name = expr["func"].upper()
            if func_name not in self.allowed_functions:
                errors.append(f"{prefix}不支持的函数: {func_name}")

            # 递归验证参数
            for i, arg in enumerate(expr.get("args", [])):
                self._validate_recursive(arg, errors, f"{prefix}参数 {i + 1}: ")

        # 验证二元运算
        if "op" in expr:
            # 使用 Excel 风格的运算符：= (等于), <> (不等于)
            valid_ops = {"+", "-", "*", "/", ">", "<", ">=", "<=", "=", "<>", "&"}
            if expr["op"] not in valid_ops:
                errors.append(f"{prefix}不支持的运算符: {expr['op']}")

            if "left" in expr:
                self._validate_recursive(expr["left"], errors, prefix)
            if "right" in expr:
                self._validate_recursive(expr["right"], errors, prefix)


# ==================== 解析器类 ====================


class OperationParser:
    """操作描述解析器"""

    @staticmethod
    def parse(json_str: str) -> Tuple[List[Operation], List[str]]:
        """
        解析 JSON 字符串为操作列表

        Args:
            json_str: JSON 格式的操作描述字符串

        Returns:
            (操作列表, 错误列表)
        """
        errors = []
        operations = []

        # 1. 解析 JSON
        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as e:
            return [], [f"JSON 解析错误: {str(e)}"]

        # 2. 检查是否有 error 字段（LLM 表示无法处理）
        if "error" in data:
            error_msg = data.get("reason", "未知原因")
            return [], [f"LLM 无法处理: {error_msg}"]

        # 3. 检查 operations 字段
        if "operations" not in data:
            return [], ["缺少 'operations' 字段"]

        if not isinstance(data["operations"], list):
            return [], ["'operations' 必须是数组"]

        # 4. 解析每个操作
        for i, op_data in enumerate(data["operations"]):
            op, op_errors = OperationParser._parse_operation(op_data, i)
            if op_errors:
                errors.extend(op_errors)
            if op:
                operations.append(op)

        return operations, errors

    @staticmethod
    def _parse_operation(
        op_data: Dict[str, Any], index: int
    ) -> Tuple[Optional[Operation], List[str]]:
        """解析单个操作"""
        errors = []
        prefix = f"操作 #{index + 1}"

        # 检查 type 字段
        if "type" not in op_data:
            return None, [f"{prefix}: 缺少 'type' 字段"]

        op_type = op_data["type"]
        if op_type not in VALID_TYPES:
            return None, [f"{prefix}: 无效的操作类型 '{op_type}'"]

        # 根据类型解析
        if op_type == "aggregate":
            return OperationParser._parse_aggregate(op_data, prefix)
        elif op_type == "add_column":
            return OperationParser._parse_add_column(op_data, prefix)
        elif op_type == "update_column":
            return OperationParser._parse_update_column(op_data, prefix)
        elif op_type == "compute":
            return OperationParser._parse_compute(op_data, prefix)
        elif op_type == "filter":
            return OperationParser._parse_filter(op_data, prefix)
        elif op_type == "sort":
            return OperationParser._parse_sort(op_data, prefix)
        elif op_type == "group_by":
            return OperationParser._parse_group_by(op_data, prefix)
        elif op_type == "create_sheet":
            return OperationParser._parse_create_sheet(op_data, prefix)
        elif op_type == "take":
            return OperationParser._parse_take(op_data, prefix)

        return None, [f"{prefix}: 未知操作类型 '{op_type}'"]

    @staticmethod
    def _parse_aggregate(
        op_data: Dict[str, Any], prefix: str
    ) -> Tuple[Optional[AggregateOperation], List[str]]:
        """解析 aggregate 操作"""
        errors = []

        # 必需字段（添加 file_id）
        required = ["function", "file_id", "table", "as"]
        for field in required:
            if field not in op_data:
                errors.append(f"{prefix}: 缺少必需字段 '{field}'")

        if errors:
            return None, errors

        function = op_data["function"].upper()

        # 验证函数
        if function not in AGGREGATE_FUNCTIONS:
            return None, [f"{prefix}: 不支持的聚合函数 '{function}'"]

        # 根据函数检查必需参数
        needs_column = function in {"SUM", "COUNT", "COUNTA", "AVERAGE", "MIN", "MAX", "MEDIAN", "SUMIF", "AVERAGEIF"}
        needs_condition = function in {"SUMIF", "COUNTIF", "AVERAGEIF"}

        if needs_column and "column" not in op_data:
            errors.append(f"{prefix}: 函数 {function} 需要 'column' 参数")

        if needs_condition:
            if "condition_column" not in op_data:
                errors.append(f"{prefix}: 函数 {function} 需要 'condition_column' 参数")
            if "condition" not in op_data:
                errors.append(f"{prefix}: 函数 {function} 需要 'condition' 参数")

        if errors:
            return None, errors

        # 创建操作对象
        try:
            op = AggregateOperation(
                function=function,
                file_id=op_data["file_id"],
                table=op_data["table"],
                column=op_data.get("column"),
                condition_column=op_data.get("condition_column"),
                condition=op_data.get("condition"),
                as_var=op_data["as"],
                description=op_data.get("description")
            )
            return op, []
        except Exception as e:
            return None, [f"{prefix}: 创建操作失败 - {str(e)}"]

    @staticmethod
    def _parse_add_column(
        op_data: Dict[str, Any], prefix: str
    ) -> Tuple[Optional[AddColumnOperation], List[str]]:
        """解析 add_column 操作"""
        errors = []

        # 必需字段（添加 file_id）
        required = ["file_id", "table", "name", "formula"]
        for field in required:
            if field not in op_data:
                errors.append(f"{prefix}: 缺少必需字段 '{field}'")

        if errors:
            return None, errors

        # 验证 formula 中的函数白名单
        formula = op_data["formula"]
        if isinstance(formula, dict):
            validator = ExpressionValidator(ROW_FUNCTIONS)
            formula_errors = validator.validate(formula, f"{prefix} formula: ")
            if formula_errors:
                errors.extend(formula_errors)

        if errors:
            return None, errors

        # 创建操作对象
        op = AddColumnOperation(
            file_id=op_data["file_id"],
            table=op_data["table"],
            name=op_data["name"],
            formula=formula,
            description=op_data.get("description")
        )
        return op, []

    @staticmethod
    def _parse_update_column(
        op_data: Dict[str, Any], prefix: str
    ) -> Tuple[Optional[UpdateColumnOperation], List[str]]:
        """解析 update_column 操作"""
        errors = []

        # 必需字段
        required = ["file_id", "table", "column", "formula"]
        for field in required:
            if field not in op_data:
                errors.append(f"{prefix}: 缺少必需字段 '{field}'")

        if errors:
            return None, errors

        # 验证 formula 中的函数白名单
        formula = op_data["formula"]
        if isinstance(formula, dict):
            validator = ExpressionValidator(ROW_FUNCTIONS)
            formula_errors = validator.validate(formula, f"{prefix} formula: ")
            if formula_errors:
                errors.extend(formula_errors)

        if errors:
            return None, errors

        # 创建操作对象
        op = UpdateColumnOperation(
            file_id=op_data["file_id"],
            table=op_data["table"],
            column=op_data["column"],
            formula=formula,
            description=op_data.get("description")
        )
        return op, []

    @staticmethod
    def _parse_compute(
        op_data: Dict[str, Any], prefix: str
    ) -> Tuple[Optional[ComputeOperation], List[str]]:
        """解析 compute 操作"""
        errors = []

        # 必需字段
        required = ["expression", "as"]
        for field in required:
            if field not in op_data:
                errors.append(f"{prefix}: 缺少必需字段 '{field}'")

        if errors:
            return None, errors

        # 检查 expression 格式
        expression = op_data["expression"]
        if not isinstance(expression, dict):
            errors.append(f"{prefix}: expression 必须是 JSON 对象格式")
            return None, errors

        # 验证 expression 中的函数白名单
        validator = ExpressionValidator(SCALAR_FUNCTIONS)
        expr_errors = validator.validate(expression, f"{prefix} expression: ")
        if expr_errors:
            errors.extend(expr_errors)

        if errors:
            return None, errors

        # 创建操作对象
        op = ComputeOperation(
            expression=expression,
            as_var=op_data["as"],
            description=op_data.get("description")
        )
        return op, []

    # ==================== 新增操作类型解析（Excel 365+）====================

    @staticmethod
    def _parse_filter(
        op_data: Dict[str, Any], prefix: str
    ) -> Tuple[Optional[FilterOperation], List[str]]:
        """解析 filter 操作"""
        errors = []

        # 必需字段
        required = ["file_id", "table", "conditions", "output"]
        for field in required:
            if field not in op_data:
                errors.append(f"{prefix}: 缺少必需字段 '{field}'")

        if errors:
            return None, errors

        # 验证 conditions
        conditions = op_data["conditions"]
        if not isinstance(conditions, list) or len(conditions) == 0:
            errors.append(f"{prefix}: conditions 必须是非空数组")
            return None, errors

        for i, cond in enumerate(conditions):
            if not isinstance(cond, dict):
                errors.append(f"{prefix}: conditions[{i}] 必须是对象")
                continue
            if "column" not in cond:
                errors.append(f"{prefix}: conditions[{i}] 缺少 'column' 字段")
            if "op" not in cond:
                errors.append(f"{prefix}: conditions[{i}] 缺少 'op' 字段")
            elif cond["op"] not in FILTER_OPERATORS:
                errors.append(f"{prefix}: conditions[{i}] 的 op '{cond['op']}' 不支持")
            if "value" not in cond:
                errors.append(f"{prefix}: conditions[{i}] 缺少 'value' 字段")

        # 验证 output
        output = op_data["output"]
        if not isinstance(output, dict):
            errors.append(f"{prefix}: output 必须是对象")
        elif "type" not in output:
            errors.append(f"{prefix}: output 缺少 'type' 字段")
        elif output["type"] not in {"new_sheet", "in_place", "replace"}:
            errors.append(f"{prefix}: output.type 必须是 'new_sheet', 'in_place' 或 'replace'")
        elif output["type"] == "new_sheet" and "name" not in output:
            errors.append(f"{prefix}: output.type 为 'new_sheet' 时必须指定 'name'")

        # 验证 logic
        logic = op_data.get("logic", "AND")
        if logic not in {"AND", "OR"}:
            errors.append(f"{prefix}: logic 必须是 'AND' 或 'OR'")

        if errors:
            return None, errors

        # 创建操作对象
        op = FilterOperation(
            file_id=op_data["file_id"],
            table=op_data["table"],
            conditions=conditions,
            output=output,
            logic=logic,
            description=op_data.get("description")
        )
        return op, []

    @staticmethod
    def _parse_sort(
        op_data: Dict[str, Any], prefix: str
    ) -> Tuple[Optional[SortOperation], List[str]]:
        """解析 sort 操作"""
        errors = []

        # 必需字段
        required = ["file_id", "table", "by"]
        for field in required:
            if field not in op_data:
                errors.append(f"{prefix}: 缺少必需字段 '{field}'")

        if errors:
            return None, errors

        # 验证 by
        by = op_data["by"]
        if not isinstance(by, list) or len(by) == 0:
            errors.append(f"{prefix}: by 必须是非空数组")
            return None, errors

        for i, rule in enumerate(by):
            if not isinstance(rule, dict):
                errors.append(f"{prefix}: by[{i}] 必须是对象")
                continue
            if "column" not in rule:
                errors.append(f"{prefix}: by[{i}] 缺少 'column' 字段")
            order = rule.get("order", "asc")
            if order not in {"asc", "desc"}:
                errors.append(f"{prefix}: by[{i}] 的 order '{order}' 无效，必须是 'asc' 或 'desc'")

        # 验证 output（可选）
        output = op_data.get("output", {"type": "in_place"})
        if not isinstance(output, dict):
            errors.append(f"{prefix}: output 必须是对象")
        elif "type" not in output:
            errors.append(f"{prefix}: output 缺少 'type' 字段")
        elif output["type"] not in {"new_sheet", "in_place"}:
            errors.append(f"{prefix}: output.type 必须是 'new_sheet' 或 'in_place'")
        elif output["type"] == "new_sheet" and "name" not in output:
            errors.append(f"{prefix}: output.type 为 'new_sheet' 时必须指定 'name'")

        if errors:
            return None, errors

        # 创建操作对象
        op = SortOperation(
            file_id=op_data["file_id"],
            table=op_data["table"],
            by=by,
            output=output,
            description=op_data.get("description")
        )
        return op, []

    @staticmethod
    def _parse_group_by(
        op_data: Dict[str, Any], prefix: str
    ) -> Tuple[Optional[GroupByOperation], List[str]]:
        """解析 group_by 操作"""
        errors = []

        # 必需字段
        required = ["file_id", "table", "group_columns", "aggregations", "output"]
        for field in required:
            if field not in op_data:
                errors.append(f"{prefix}: 缺少必需字段 '{field}'")

        if errors:
            return None, errors

        # 验证 group_columns
        group_columns = op_data["group_columns"]
        if not isinstance(group_columns, list) or len(group_columns) == 0:
            errors.append(f"{prefix}: group_columns 必须是非空数组")

        # 验证 aggregations
        aggregations = op_data["aggregations"]
        if not isinstance(aggregations, list) or len(aggregations) == 0:
            errors.append(f"{prefix}: aggregations 必须是非空数组")
        else:
            for i, agg in enumerate(aggregations):
                if not isinstance(agg, dict):
                    errors.append(f"{prefix}: aggregations[{i}] 必须是对象")
                    continue
                if "column" not in agg:
                    errors.append(f"{prefix}: aggregations[{i}] 缺少 'column' 字段")
                if "function" not in agg:
                    errors.append(f"{prefix}: aggregations[{i}] 缺少 'function' 字段")
                elif agg["function"].upper() not in GROUPBY_FUNCTIONS:
                    errors.append(f"{prefix}: aggregations[{i}] 的函数 '{agg['function']}' 不支持")
                if "as" not in agg:
                    errors.append(f"{prefix}: aggregations[{i}] 缺少 'as' 字段")

        # 验证 output
        output = op_data["output"]
        if not isinstance(output, dict):
            errors.append(f"{prefix}: output 必须是对象")
        elif "type" not in output:
            errors.append(f"{prefix}: output 缺少 'type' 字段")
        elif output["type"] != "new_sheet":
            errors.append(f"{prefix}: group_by 的 output.type 必须是 'new_sheet'")
        elif "name" not in output:
            errors.append(f"{prefix}: output 缺少 'name' 字段")

        if errors:
            return None, errors

        # 创建操作对象
        op = GroupByOperation(
            file_id=op_data["file_id"],
            table=op_data["table"],
            group_columns=group_columns,
            aggregations=aggregations,
            output=output,
            description=op_data.get("description")
        )
        return op, []

    @staticmethod
    def _parse_create_sheet(
        op_data: Dict[str, Any], prefix: str
    ) -> Tuple[Optional[CreateSheetOperation], List[str]]:
        """解析 create_sheet 操作"""
        errors = []

        # 必需字段
        required = ["file_id", "name"]
        for field in required:
            if field not in op_data:
                errors.append(f"{prefix}: 缺少必需字段 '{field}'")

        if errors:
            return None, errors

        # 验证 source（可选）
        source = op_data.get("source", {"type": "empty"})
        if not isinstance(source, dict):
            errors.append(f"{prefix}: source 必须是对象")
        elif "type" not in source:
            errors.append(f"{prefix}: source 缺少 'type' 字段")
        elif source["type"] not in {"empty", "copy", "reference"}:
            errors.append(f"{prefix}: source.type 必须是 'empty', 'copy' 或 'reference'")
        elif source["type"] in {"copy", "reference"} and "table" not in source:
            errors.append(f"{prefix}: source.type 为 '{source['type']}' 时必须指定 'table'")

        if errors:
            return None, errors

        # 创建操作对象
        op = CreateSheetOperation(
            file_id=op_data["file_id"],
            name=op_data["name"],
            source=source,
            columns=op_data.get("columns"),
            description=op_data.get("description")
        )
        return op, []

    @staticmethod
    def _parse_take(
        op_data: Dict[str, Any], prefix: str
    ) -> Tuple[Optional[TakeOperation], List[str]]:
        """解析 take 操作（取前/后 N 行）"""
        errors = []

        # 必需字段
        required = ["file_id", "table", "rows"]
        for field in required:
            if field not in op_data:
                errors.append(f"{prefix}: 缺少必需字段 '{field}'")

        if errors:
            return None, errors

        # 验证 rows
        rows = op_data["rows"]
        if not isinstance(rows, int):
            errors.append(f"{prefix}: rows 必须是整数")
        elif rows == 0:
            errors.append(f"{prefix}: rows 不能为 0")

        # 验证 output（可选）
        output = op_data.get("output", {"type": "in_place"})
        if not isinstance(output, dict):
            errors.append(f"{prefix}: output 必须是对象")
        elif "type" not in output:
            errors.append(f"{prefix}: output 缺少 'type' 字段")
        elif output["type"] not in {"new_sheet", "in_place"}:
            errors.append(f"{prefix}: output.type 必须是 'new_sheet' 或 'in_place'")
        elif output["type"] == "new_sheet" and "name" not in output:
            errors.append(f"{prefix}: output.type 为 'new_sheet' 时必须指定 'name'")

        if errors:
            return None, errors

        # 创建操作对象
        op = TakeOperation(
            file_id=op_data["file_id"],
            table=op_data["table"],
            rows=rows,
            output=output,
            description=op_data.get("description")
        )
        return op, []

    @staticmethod
    def validate_operations(
        operations: List[Operation],
        file_sheets: Dict[str, List[str]]
    ) -> List[str]:
        """
        验证操作的语义正确性

        Args:
            operations: 操作列表
            file_sheets: 可用的文件和 sheet 映射 {file_id: [sheet_names]}

        Returns:
            错误列表
        """
        errors = []
        defined_vars = set()
        # 跟踪新创建的 sheet（用于验证后续操作引用）
        created_sheets: Dict[str, List[str]] = {}

        def check_file_and_sheet(file_id: str, table: str, prefix: str) -> bool:
            """检查文件和 sheet 是否存在（包括动态创建的）"""
            if file_id not in file_sheets:
                # 检查是否在已创建的 sheet 中
                if file_id not in created_sheets:
                    errors.append(f"{prefix}: 文件 '{file_id}' 不存在")
                    return False
            # 检查 sheet
            existing_sheets = file_sheets.get(file_id, [])
            new_sheets = created_sheets.get(file_id, [])
            if table not in existing_sheets and table not in new_sheets:
                errors.append(f"{prefix}: Sheet '{table}' 不存在于文件 '{file_id}'")
                return False
            return True

        def register_new_sheet(file_id: str, sheet_name: str):
            """注册新创建的 sheet"""
            if file_id not in created_sheets:
                created_sheets[file_id] = []
            if sheet_name not in created_sheets[file_id]:
                created_sheets[file_id].append(sheet_name)

        for i, op in enumerate(operations):
            prefix = f"操作 #{i + 1}"

            if isinstance(op, AggregateOperation):
                check_file_and_sheet(op.file_id, op.table, prefix)
                defined_vars.add(op.as_var)

            elif isinstance(op, AddColumnOperation):
                check_file_and_sheet(op.file_id, op.table, prefix)

            elif isinstance(op, UpdateColumnOperation):
                check_file_and_sheet(op.file_id, op.table, prefix)

            elif isinstance(op, ComputeOperation):
                defined_vars.add(op.as_var)

            elif isinstance(op, FilterOperation):
                check_file_and_sheet(op.file_id, op.table, prefix)
                # 如果输出到新 sheet，注册它
                if op.output.get("type") == "new_sheet":
                    register_new_sheet(op.file_id, op.output["name"])

            elif isinstance(op, SortOperation):
                check_file_and_sheet(op.file_id, op.table, prefix)
                # 如果输出到新 sheet，注册它
                if op.output and op.output.get("type") == "new_sheet":
                    register_new_sheet(op.file_id, op.output["name"])

            elif isinstance(op, GroupByOperation):
                check_file_and_sheet(op.file_id, op.table, prefix)
                # group_by 总是输出到新 sheet
                register_new_sheet(op.file_id, op.output["name"])

            elif isinstance(op, CreateSheetOperation):
                # 检查文件是否存在
                if op.file_id not in file_sheets and op.file_id not in created_sheets:
                    errors.append(f"{prefix}: 文件 '{op.file_id}' 不存在")
                # 如果是复制或引用，检查源表
                source_type = op.source.get("type") if op.source else "empty"
                if source_type in {"copy", "reference"}:
                    source_table = op.source.get("table")
                    if source_table:
                        check_file_and_sheet(op.file_id, source_table, prefix)
                # 注册新 sheet
                register_new_sheet(op.file_id, op.name)

            elif isinstance(op, TakeOperation):
                check_file_and_sheet(op.file_id, op.table, prefix)
                # 如果输出到新 sheet，注册它
                if op.output and op.output.get("type") == "new_sheet":
                    register_new_sheet(op.file_id, op.output["name"])

        return errors


# ==================== 便捷函数 ====================


def parse_operations(json_str: str) -> Tuple[List[Operation], List[str]]:
    """解析操作描述的便捷函数"""
    return OperationParser.parse(json_str)


def parse_and_validate(
    json_str: str,
    file_sheets: Dict[str, List[str]]
) -> Tuple[List[Operation], List[str]]:
    """
    解析并验证操作描述

    Args:
        json_str: JSON 格式的操作描述
        file_sheets: 文件和 sheet 映射 {file_id: [sheet_names]}

    Returns:
        (操作列表, 错误列表)
    """
    operations, parse_errors = OperationParser.parse(json_str)

    if parse_errors:
        return operations, parse_errors

    validate_errors = OperationParser.validate_operations(
        operations, file_sheets
    )

    return operations, validate_errors
