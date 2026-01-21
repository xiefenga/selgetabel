"""函数库 - 实现聚合函数和行级函数"""

from typing import Any, Union
from app.core.models import Range, ExcelError, NA, DIV0, VALUE


# ==================== 聚合函数 ====================


def SUM(values: Range) -> float:
    """求和"""
    total = 0.0
    for v in values:
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            total += v
    return total


def COUNT(values: Range) -> int:
    """计数（仅数值）"""
    count = 0
    for v in values:
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            count += 1
    return count


def COUNTA(values: Range) -> int:
    """计数（非空）"""
    count = 0
    for v in values:
        if v is not None and v != "":
            count += 1
    return count


def AVERAGE(values: Range) -> Union[float, ExcelError]:
    """平均值"""
    total = 0.0
    count = 0
    for v in values:
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            total += v
            count += 1
    if count == 0:
        return DIV0
    return total / count


def MIN(values: Range) -> Union[float, ExcelError]:
    """最小值"""
    nums = [v for v in values if isinstance(v, (int, float)) and not isinstance(v, bool)]
    if not nums:
        return VALUE
    return min(nums)


def MAX(values: Range) -> Union[float, ExcelError]:
    """最大值"""
    nums = [v for v in values if isinstance(v, (int, float)) and not isinstance(v, bool)]
    if not nums:
        return VALUE
    return max(nums)


def _match_condition(value: Any, condition: Union[str, int, float]) -> bool:
    """
    检查值是否匹配条件

    支持的条件格式:
    - 精确匹配: "已完成", 100
    - 比较: ">0", "<100", ">=0", "<=100", "<>0"
    """
    if isinstance(condition, (int, float)):
        # 数值精确匹配
        return value == condition

    if isinstance(condition, str):
        condition = condition.strip()

        # 检查比较运算符
        if condition.startswith(">="):
            try:
                num = float(condition[2:])
                return isinstance(value, (int, float)) and value >= num
            except ValueError:
                return False
        elif condition.startswith("<="):
            try:
                num = float(condition[2:])
                return isinstance(value, (int, float)) and value <= num
            except ValueError:
                return False
        elif condition.startswith("<>"):
            cmp_value = condition[2:]
            try:
                num = float(cmp_value)
                return value != num
            except ValueError:
                return str(value) != cmp_value
        elif condition.startswith(">"):
            try:
                num = float(condition[1:])
                return isinstance(value, (int, float)) and value > num
            except ValueError:
                return False
        elif condition.startswith("<"):
            try:
                num = float(condition[1:])
                return isinstance(value, (int, float)) and value < num
            except ValueError:
                return False
        else:
            # 字符串精确匹配
            return str(value) == condition

    return False


def SUMIF(
    sum_range: Range,
    criteria_range: Range,
    criteria: Union[str, int, float]
) -> float:
    """条件求和"""
    if len(sum_range) != len(criteria_range):
        raise ValueError("sum_range 和 criteria_range 长度不匹配")

    total = 0.0
    for value, check_value in zip(sum_range, criteria_range):
        if _match_condition(check_value, criteria):
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                total += value
    return total


def COUNTIF(
    criteria_range: Range,
    criteria: Union[str, int, float]
) -> int:
    """条件计数"""
    count = 0
    for check_value in criteria_range:
        if _match_condition(check_value, criteria):
            count += 1
    return count


def COUNTIFS(*args) -> int:
    """
    多条件计数

    用法: COUNTIFS(range1, criteria1, range2, criteria2, ...)

    参数必须成对出现：(范围, 条件)
    """
    if len(args) % 2 != 0:
        raise ValueError("COUNTIFS 参数必须成对出现")

    if len(args) < 2:
        raise ValueError("COUNTIFS 至少需要一对参数")

    # 收集所有范围和条件
    pairs = []
    for i in range(0, len(args), 2):
        criteria_range = args[i]
        criteria = args[i + 1]
        pairs.append((criteria_range, criteria))

    # 检查所有范围长度一致
    first_len = len(pairs[0][0])
    for criteria_range, _ in pairs:
        if len(criteria_range) != first_len:
            raise ValueError("COUNTIFS 所有范围长度必须一致")

    # 统计满足所有条件的行数
    count = 0
    for row_idx in range(first_len):
        all_match = True
        for criteria_range, criteria in pairs:
            if not _match_condition(criteria_range[row_idx], criteria):
                all_match = False
                break
        if all_match:
            count += 1

    return count


def AVERAGEIF(
    avg_range: Range,
    criteria_range: Range,
    criteria: Union[str, int, float]
) -> Union[float, ExcelError]:
    """条件平均"""
    if len(avg_range) != len(criteria_range):
        raise ValueError("avg_range 和 criteria_range 长度不匹配")

    total = 0.0
    count = 0
    for value, check_value in zip(avg_range, criteria_range):
        if _match_condition(check_value, criteria):
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                total += value
                count += 1

    if count == 0:
        return DIV0
    return total / count


# ==================== 行级函数 ====================


def IF(condition: bool, true_value: Any, false_value: Any) -> Any:
    """条件判断"""
    return true_value if condition else false_value


def AND(*conditions: bool) -> bool:
    """逻辑与"""
    return all(conditions)


def OR(*conditions: bool) -> bool:
    """逻辑或"""
    return any(conditions)


def NOT(condition: bool) -> bool:
    """逻辑非"""
    return not condition


def VLOOKUP(
    lookup_value: Any,
    lookup_table: "Table",
    key_column: str,
    value_column: str
) -> Any:
    """
    查找函数

    Args:
        lookup_value: 要查找的值
        lookup_table: 要查找的表
        key_column: 键列名
        value_column: 值列名

    Returns:
        找到的值，或 #N/A 错误
    """
    try:
        key_values = lookup_table.get_column(key_column)
        result_values = lookup_table.get_column(value_column)

        for i, key in enumerate(key_values):
            if key == lookup_value:
                return result_values[i]

        return NA
    except Exception:
        return NA


def IFERROR(value: Any, value_if_error: Any) -> Any:
    """错误处理"""
    if isinstance(value, ExcelError):
        return value_if_error
    return value


def ROUND(value: Union[int, float], digits: int) -> float:
    """四舍五入"""
    if isinstance(value, ExcelError):
        return value
    return round(float(value), digits)


def ABS(value: Union[int, float]) -> float:
    """绝对值"""
    if isinstance(value, ExcelError):
        return value
    return abs(float(value))


# ==================== 文本函数 ====================


def LEFT(text: str, num_chars: int) -> str:
    """左截取"""
    return str(text)[:num_chars]


def RIGHT(text: str, num_chars: int) -> str:
    """右截取"""
    return str(text)[-num_chars:] if num_chars > 0 else ""


def MID(text: str, start_num: int, num_chars: int) -> str:
    """中间截取（start_num 从 1 开始，与 Excel 一致）"""
    text = str(text)
    start_index = start_num - 1
    return text[start_index:start_index + num_chars]


def LEN(text: str) -> int:
    """文本长度"""
    return len(str(text))


def TRIM(text: str) -> str:
    """去除空格"""
    return str(text).strip()


def UPPER(text: str) -> str:
    """转大写"""
    return str(text).upper()


def LOWER(text: str) -> str:
    """转小写"""
    return str(text).lower()


def CONCAT(*values: Any) -> str:
    """文本拼接"""
    return "".join(str(v) if v is not None else "" for v in values)


def TEXT(value: Any, format_text: str) -> str:
    """数值格式化（简化版本）"""
    # 简化实现，主要支持数字格式
    try:
        if "." in format_text:
            # 提取小数位数
            decimal_places = len(format_text.split(".")[-1].replace("0", "").replace("#", ""))
            if decimal_places == 0:
                decimal_places = len(format_text.split(".")[-1])
            return f"{float(value):.{decimal_places}f}"
        return str(int(float(value)))
    except (ValueError, TypeError):
        return str(value)


def VALUE(text: str) -> Union[float, ExcelError]:
    """文本转数值"""
    try:
        return float(str(text))
    except (ValueError, TypeError):
        return VALUE


# ==================== 聚合函数字典 ====================

AGGREGATE_FUNC_MAP = {
    "SUM": SUM,
    "COUNT": COUNT,
    "COUNTA": COUNTA,
    "AVERAGE": AVERAGE,
    "MIN": MIN,
    "MAX": MAX,
    "SUMIF": SUMIF,
    "COUNTIF": COUNTIF,
    "COUNTIFS": COUNTIFS,
    "AVERAGEIF": AVERAGEIF,
}

# ==================== 行级函数字典 ====================

ROW_FUNC_MAP = {
    "IF": IF,
    "AND": AND,
    "OR": OR,
    "NOT": NOT,
    "VLOOKUP": VLOOKUP,
    "IFERROR": IFERROR,
    "ROUND": ROUND,
    "ABS": ABS,
    "LEFT": LEFT,
    "RIGHT": RIGHT,
    "MID": MID,
    "LEN": LEN,
    "TRIM": TRIM,
    "UPPER": UPPER,
    "LOWER": LOWER,
    "CONCAT": CONCAT,
    "TEXT": TEXT,
    "VALUE": VALUE,
    "COUNTIFS": COUNTIFS,  # 也可用于行级公式
}

# ==================== 标量函数字典 ====================

SCALAR_FUNC_MAP = {
    "ROUND": ROUND,
    "ABS": ABS,
    "MAX": lambda a, b: max(a, b),
    "MIN": lambda a, b: min(a, b),
}
