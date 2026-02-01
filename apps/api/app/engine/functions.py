"""函数库 - 实现聚合函数和行级函数"""

import math
from typing import Any, Union
from app.engine.models import Range, ExcelError


# ==================== 辅助函数 ====================


def _is_valid_number(v: Any) -> bool:
    """检查值是否为有效数值（排除 NaN、None、bool）"""
    if isinstance(v, bool):
        return False
    if isinstance(v, (int, float)):
        if isinstance(v, float) and math.isnan(v):
            return False
        return True
    return False


def _is_blank(value: Any) -> bool:
    """检查值是否为空（None、NaN、空字符串）"""
    if value is None:
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    if value == "":
        return True
    return False


# ==================== 聚合函数 ====================


def SUM(values: Range) -> float:
    """求和（自动排除空值和 NaN）"""
    total = 0.0
    for v in values:
        if _is_valid_number(v):
            total += v
    return total


def COUNT(values: Range) -> int:
    """计数（仅有效数值，排除 NaN）"""
    count = 0
    for v in values:
        if _is_valid_number(v):
            count += 1
    return count


def COUNTA(values: Range) -> int:
    """计数（非空，排除 None、NaN、空字符串）"""
    count = 0
    for v in values:
        if not _is_blank(v):
            count += 1
    return count


def AVERAGE(values: Range) -> Union[float, ExcelError]:
    """平均值（自动排除空值和 NaN）"""
    total = 0.0
    count = 0
    for v in values:
        if _is_valid_number(v):
            total += v
            count += 1
    if count == 0:
        return ExcelError("#DIV/0!")
    return total / count


def MIN(values: Range) -> Union[float, ExcelError]:
    """最小值（自动排除 NaN）"""
    nums = [v for v in values if _is_valid_number(v)]
    if not nums:
        return ExcelError("#VALUE!")
    return min(nums)


def MAX(values: Range) -> Union[float, ExcelError]:
    """最大值（自动排除 NaN）"""
    nums = [v for v in values if _is_valid_number(v)]
    if not nums:
        return ExcelError("#VALUE!")
    return max(nums)


def MEDIAN(values: Range) -> Union[float, ExcelError]:
    """中位数（自动排除 NaN）"""
    nums = sorted([v for v in values if _is_valid_number(v)])
    if not nums:
        return ExcelError("#VALUE!")
    n = len(nums)
    mid = n // 2
    if n % 2 == 0:
        # 偶数个：取中间两个的平均值
        return (nums[mid - 1] + nums[mid]) / 2
    else:
        # 奇数个：取中间值
        return nums[mid]


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
    """条件求和（自动排除空值和 NaN）"""
    if len(sum_range) != len(criteria_range):
        raise ValueError("sum_range 和 criteria_range 长度不匹配")

    total = 0.0
    for value, check_value in zip(sum_range, criteria_range):
        if _match_condition(check_value, criteria):
            if _is_valid_number(value):
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
    """条件平均（自动排除空值和 NaN）"""
    if len(avg_range) != len(criteria_range):
        raise ValueError("avg_range 和 criteria_range 长度不匹配")

    total = 0.0
    count = 0
    for value, check_value in zip(avg_range, criteria_range):
        if _match_condition(check_value, criteria):
            if _is_valid_number(value):
                total += value
                count += 1

    if count == 0:
        return ExcelError("#DIV/0!")
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


# ==================== 空值判断函数 ====================


def ISBLANK(value: Any) -> bool:
    """
    判断是否为空值

    空值包括：None、NaN、空字符串

    Args:
        value: 要检查的值

    Returns:
        如果为空则返回 True
    """
    return _is_blank(value)


def ISNA(value: Any) -> bool:
    """
    判断是否为 #N/A 错误或 NaN

    Args:
        value: 要检查的值

    Returns:
        如果是 #N/A 或 NaN 则返回 True
    """
    if isinstance(value, float) and math.isnan(value):
        return True
    if isinstance(value, ExcelError) and value.code == "#N/A":
        return True
    return False


def ISNUMBER(value: Any) -> bool:
    """
    判断是否为有效数值

    Args:
        value: 要检查的值

    Returns:
        如果是有效数值则返回 True
    """
    return _is_valid_number(value)


def ISERROR(value: Any) -> bool:
    """
    判断是否为错误值

    Args:
        value: 要检查的值

    Returns:
        如果是 ExcelError 则返回 True
    """
    return isinstance(value, ExcelError)


# ==================== 错误处理函数 ====================


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


def _to_int(value: Any) -> Union[int, ExcelError]:
    """将值转换为整数，处理无效输入"""
    _VALUE_ERROR = ExcelError("#VALUE!")
    if isinstance(value, ExcelError):
        return value
    if value is None:
        return _VALUE_ERROR
    if isinstance(value, bool):
        return 1 if value else 0
    if isinstance(value, float):
        if math.isnan(value):
            return _VALUE_ERROR
        return int(value)
    if isinstance(value, int):
        return value
    try:
        return int(float(value))
    except (ValueError, TypeError):
        return _VALUE_ERROR


def LEFT(text: Any, num_chars: Any) -> Union[str, ExcelError]:
    """左截取"""
    n = _to_int(num_chars)
    if isinstance(n, ExcelError):
        return n
    if n < 0:
        return ExcelError("#VALUE!")
    return str(text)[:n]


def RIGHT(text: Any, num_chars: Any) -> Union[str, ExcelError]:
    """右截取"""
    n = _to_int(num_chars)
    if isinstance(n, ExcelError):
        return n
    if n < 0:
        return ExcelError("#VALUE!")
    return str(text)[-n:] if n > 0 else ""


def MID(text: Any, start_num: Any, num_chars: Any) -> Union[str, ExcelError]:
    """中间截取（start_num 从 1 开始，与 Excel 一致）"""
    start = _to_int(start_num)
    if isinstance(start, ExcelError):
        return start
    n = _to_int(num_chars)
    if isinstance(n, ExcelError):
        return n
    if start < 1 or n < 0:
        return ExcelError("#VALUE!")
    text = str(text)
    start_index = start - 1
    return text[start_index:start_index + n]


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


def PROPER(text: str) -> str:
    """
    首字母大写（每个单词的首字母大写，其余小写）

    与 Excel PROPER 函数一致：
    - 将每个单词的首字母转换为大写
    - 将其余字母转换为小写
    - 单词由空格或标点符号分隔

    Args:
        text: 要转换的文本

    Returns:
        转换后的文本

    Examples:
        PROPER("hello world") -> "Hello World"
        PROPER("HELLO WORLD") -> "Hello World"
        PROPER("this is a TEST") -> "This Is A Test"
    """
    return str(text).title()


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
        return ExcelError("#VALUE!")


def FIND(find_text: str, within_text: str, start_num: int = 1) -> Union[int, ExcelError]:
    """
    查找文本位置（区分大小写）

    与 Excel FIND 函数一致：
    - 返回 find_text 在 within_text 中第一次出现的位置（从 1 开始）
    - 区分大小写
    - 找不到返回 #VALUE! 错误

    Args:
        find_text: 要查找的文本
        within_text: 被查找的文本
        start_num: 起始位置（从 1 开始，默认为 1）

    Returns:
        找到的位置（从 1 开始），找不到返回 VALUE 错误
    """
    find_text = str(find_text)
    within_text = str(within_text)

    # 转换为 0-based 索引
    start_index = start_num - 1
    if start_index < 0:
        return ExcelError("#VALUE!")

    # 从 start_index 开始查找
    pos = within_text.find(find_text, start_index)

    if pos == -1:
        return ExcelError("#VALUE!")

    # 返回 1-based 位置
    return pos + 1


def SEARCH(find_text: str, within_text: str, start_num: int = 1) -> Union[int, ExcelError]:
    """
    查找文本位置（不区分大小写）

    与 Excel SEARCH 函数一致：
    - 返回 find_text 在 within_text 中第一次出现的位置（从 1 开始）
    - 不区分大小写
    - 找不到返回 #VALUE! 错误

    Args:
        find_text: 要查找的文本
        within_text: 被查找的文本
        start_num: 起始位置（从 1 开始，默认为 1）

    Returns:
        找到的位置（从 1 开始），找不到返回 VALUE 错误
    """
    find_text = str(find_text).lower()
    within_text_lower = str(within_text).lower()

    # 转换为 0-based 索引
    start_index = start_num - 1
    if start_index < 0:
        return ExcelError("#VALUE!")

    # 从 start_index 开始查找（不区分大小写）
    pos = within_text_lower.find(find_text, start_index)

    if pos == -1:
        return ExcelError("#VALUE!")

    # 返回 1-based 位置
    return pos + 1


def SUBSTITUTE(text: Any, old_text: str, new_text: str, instance_num: int = None) -> str:
    """
    替换文本中的指定字符串

    与 Excel SUBSTITUTE 函数一致：
    - 将 text 中的 old_text 替换为 new_text
    - 如果指定 instance_num，则只替换第 N 次出现的内容
    - 如果不指定 instance_num，则替换所有出现的内容
    - 区分大小写

    Args:
        text: 原始文本
        old_text: 要替换的文本
        new_text: 替换后的文本
        instance_num: 可选，指定替换第几次出现（从 1 开始）

    Returns:
        替换后的文本

    Examples:
        SUBSTITUTE("€150K", "€", "") -> "150K"
        SUBSTITUTE("150K", "K", "") -> "150"
        SUBSTITUTE("a-b-c", "-", "_") -> "a_b_c"
        SUBSTITUTE("a-b-c", "-", "_", 1) -> "a_b-c"  (只替换第一个)
    """
    text = str(text)
    old_text = str(old_text)
    new_text = str(new_text)

    # 如果 old_text 为空，直接返回原文本
    if not old_text:
        return text

    # 如果未指定 instance_num，替换所有
    if instance_num is None:
        return text.replace(old_text, new_text)

    # 替换指定位置的出现
    if instance_num < 1:
        return text  # 无效的 instance_num，返回原文本

    # 找到所有出现位置
    count = 0
    start = 0
    while True:
        pos = text.find(old_text, start)
        if pos == -1:
            break
        count += 1
        if count == instance_num:
            # 替换这个位置
            return text[:pos] + new_text + text[pos + len(old_text):]
        start = pos + 1

    # 没找到指定的出现次数，返回原文本
    return text


# ==================== 聚合函数字典 ====================

AGGREGATE_FUNC_MAP = {
    "SUM": SUM,
    "COUNT": COUNT,
    "COUNTA": COUNTA,
    "AVERAGE": AVERAGE,
    "MIN": MIN,
    "MAX": MAX,
    "MEDIAN": MEDIAN,
    "SUMIF": SUMIF,
    "COUNTIF": COUNTIF,
    "COUNTIFS": COUNTIFS,
    "AVERAGEIF": AVERAGEIF,
}

# ==================== 行级函数字典 ====================

ROW_FUNC_MAP = {
    # 逻辑函数
    "IF": IF,
    "AND": AND,
    "OR": OR,
    "NOT": NOT,
    # 空值判断函数
    "ISBLANK": ISBLANK,
    "ISNA": ISNA,
    "ISNUMBER": ISNUMBER,
    "ISERROR": ISERROR,
    # 错误处理函数
    "IFERROR": IFERROR,
    # 数值函数
    "ROUND": ROUND,
    "ABS": ABS,
    # 文本函数
    "LEFT": LEFT,
    "RIGHT": RIGHT,
    "MID": MID,
    "LEN": LEN,
    "TRIM": TRIM,
    "UPPER": UPPER,
    "LOWER": LOWER,
    "PROPER": PROPER,
    "CONCAT": CONCAT,
    "TEXT": TEXT,
    "VALUE": VALUE,
    "FIND": FIND,
    "SEARCH": SEARCH,
    "SUBSTITUTE": SUBSTITUTE,
    # 多条件计数（也可用于行级公式）
    "COUNTIFS": COUNTIFS,
    # 注意：VLOOKUP 在 FormulaEvaluator 中特殊处理，不在此映射中
}

# ==================== 标量函数字典 ====================

SCALAR_FUNC_MAP = {
    "ROUND": ROUND,
    "ABS": ABS,
    "MAX": lambda a, b: max(a, b),
    "MIN": lambda a, b: min(a, b),
}
