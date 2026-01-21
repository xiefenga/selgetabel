"""JSON 解析器 - 解析和校验 LLM 输出的操作描述"""

import json
from typing import List, Dict, Any, Tuple, Optional
from app.core.models import (
    AggregateOperation,
    AddColumnOperation,
    ComputeOperation,
    Operation,
)


# ==================== 白名单定义 ====================

# 聚合函数白名单
AGGREGATE_FUNCTIONS = {
    "SUM", "COUNT", "COUNTA", "AVERAGE", "MIN", "MAX",
    "SUMIF", "COUNTIF", "AVERAGEIF"
}

# 行级函数白名单（用于 add_column 的 formula）
ROW_FUNCTIONS = {
    # 逻辑
    "IF", "AND", "OR", "NOT",
    # 查找
    "VLOOKUP",
    # 错误处理
    "IFERROR",
    # 数值
    "ROUND", "ABS",
    # 文本
    "LEFT", "RIGHT", "MID", "LEN", "TRIM", "UPPER", "LOWER",
    "CONCAT", "TEXT", "VALUE"
}

# 标量函数白名单（用于 compute 的 expression）
SCALAR_FUNCTIONS = {
    "ROUND", "ABS", "MAX", "MIN"
}

# 操作类型
VALID_TYPES = {"aggregate", "add_column", "compute"}


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
        elif op_type == "compute":
            return OperationParser._parse_compute(op_data, prefix)

        return None, [f"{prefix}: 未知操作类型 '{op_type}'"]

    @staticmethod
    def _parse_aggregate(
        op_data: Dict[str, Any], prefix: str
    ) -> Tuple[Optional[AggregateOperation], List[str]]:
        """解析 aggregate 操作"""
        errors = []

        # 必需字段
        required = ["function", "table", "as"]
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
        needs_column = function in {"SUM", "COUNT", "COUNTA", "AVERAGE", "MIN", "MAX", "SUMIF", "AVERAGEIF"}
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
                table=op_data["table"],
                column=op_data.get("column"),
                condition_column=op_data.get("condition_column"),
                condition=op_data.get("condition"),
                as_var=op_data["as"]
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

        # 必需字段
        required = ["table", "name", "formula"]
        for field in required:
            if field not in op_data:
                errors.append(f"{prefix}: 缺少必需字段 '{field}'")

        if errors:
            return None, errors

        # 创建操作对象
        op = AddColumnOperation(
            table=op_data["table"],
            name=op_data["name"],
            formula=op_data["formula"]
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

        # 创建操作对象
        op = ComputeOperation(
            expression=op_data["expression"],
            as_var=op_data["as"]
        )
        return op, []

    @staticmethod
    def validate_operations(
        operations: List[Operation],
        available_tables: List[str]
    ) -> List[str]:
        """
        验证操作的语义正确性

        Args:
            operations: 操作列表
            available_tables: 可用的表名列表

        Returns:
            错误列表
        """
        errors = []
        defined_vars = set()

        for i, op in enumerate(operations):
            prefix = f"操作 #{i + 1}"

            if isinstance(op, AggregateOperation):
                # 检查表是否存在
                if op.table not in available_tables:
                    errors.append(f"{prefix}: 表 '{op.table}' 不存在")
                # 记录定义的变量
                defined_vars.add(op.as_var)

            elif isinstance(op, AddColumnOperation):
                # 检查表是否存在
                if op.table not in available_tables:
                    errors.append(f"{prefix}: 表 '{op.table}' 不存在")

            elif isinstance(op, ComputeOperation):
                # 记录定义的变量
                defined_vars.add(op.as_var)

        return errors


# ==================== 便捷函数 ====================


def parse_operations(json_str: str) -> Tuple[List[Operation], List[str]]:
    """解析操作描述的便捷函数"""
    return OperationParser.parse(json_str)


def parse_and_validate(
    json_str: str,
    available_tables: List[str]
) -> Tuple[List[Operation], List[str]]:
    """解析并验证操作描述"""
    operations, parse_errors = OperationParser.parse(json_str)

    if parse_errors:
        return operations, parse_errors

    validate_errors = OperationParser.validate_operations(
        operations, available_tables
    )

    return operations, validate_errors
