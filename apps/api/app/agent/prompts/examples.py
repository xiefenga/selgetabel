"""Examples 注册表 — 工具 I/O 示例供 Prompt 注入"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class ToolExample:
    """单个工具的 I/O 示例"""
    tool_name: str
    user_query: str
    expected_tool: str
    expected_args: Optional[dict] = None
    notes: Optional[str] = None


EXAMPLES: list[ToolExample] = [
    # FilterTool
    ToolExample(
        tool_name="filter",
        user_query="只看销售额大于1000的行",
        expected_tool="filter",
        expected_args={"column": "销售额", "op": ">", "value": 1000},
    ),
    ToolExample(
        tool_name="filter",
        user_query="筛选华北地区的数据",
        expected_tool="filter",
        expected_args={"column": "地区", "op": "==", "value": "华北"},
    ),
    ToolExample(
        tool_name="filter",
        user_query="找出年龄小于30的员工",
        expected_tool="filter",
        expected_args={"column": "年龄", "op": "<", "value": 30},
    ),
    # SortTool
    ToolExample(
        tool_name="sort",
        user_query="按销售额从高到低排序",
        expected_tool="sort",
        expected_args={"column": "销售额", "order": "desc"},
    ),
    ToolExample(
        tool_name="sort",
        user_query="按发布时间升序排列",
        expected_tool="sort",
        expected_args={"column": "发布时间", "order": "asc"},
    ),
    # AggregateTool
    ToolExample(
        tool_name="aggregate",
        user_query="各地区的销售总额是多少",
        expected_tool="aggregate",
        expected_args={"column": "销售额", "function": "SUM", "as_var": "total_sales"},
        notes="按隐含的分组维度（地区）聚合，需用 group_by 实现",
    ),
    ToolExample(
        tool_name="aggregate",
        user_query="计算平均工资",
        expected_tool="aggregate",
        expected_args={"column": "工资", "function": "AVERAGE", "as_var": "avg_salary"},
    ),
    # ClarifyTool
    ToolExample(
        tool_name="clarify",
        user_query="分析这份数据",
        expected_tool="clarify",
        expected_args={"question": "您想从哪个维度分析？", "options": ["按地区", "按产品", "按时段"]},
    ),
    ToolExample(
        tool_name="clarify",
        user_query="帮我处理这个文件",
        expected_tool="clarify",
        expected_args={"question": "您想对这个 Excel 文件做什么操作？", "options": ["筛选", "排序", "计算汇总", "新增列"]},
    ),
]


class ExamplesQueryRegistry:
    """
    根据用户 query 特征，注入相关 Examples 到 prompt。
    通过 keyword matching 选择最相关的 examples。
    """

    def __init__(self, examples: list[ToolExample] = None):
        self._examples = examples or EXAMPLES

    def get_relevant_examples(self, query: str, max_examples: int = 5) -> list[ToolExample]:
        """
        根据 query 关键词返回最相关的 examples。

        评分规则：query 中出现的每个词命中 example.user_query 中的词，+1 分。
        按分数降序排列，最多返回 max_examples 条。
        """
        query_lower = query.lower()
        query_words = set(query_lower.split())

        scored = []
        for ex in self._examples:
            ex_words = set(ex.user_query.lower().split())
            score = len(query_words & ex_words)
            if score > 0:
                scored.append((score, ex))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [ex for _, ex in scored[:max_examples]]

    def format_as_prompt(self, examples: list[ToolExample]) -> str:
        """将 examples 格式化为 prompt 文本"""
        if not examples:
            return ""
        lines = ["\n## 参考示例\n"]
        for ex in examples:
            lines.append(f"用户说：「{ex.user_query}」")
            args_str = f"（参数：{ex.expected_args}）" if ex.expected_args else ""
            lines.append(f"  → 调用 {ex.expected_tool}{args_str}")
            if ex.notes:
                lines.append(f"  注：{ex.notes}")
            lines.append("")
        return "\n".join(lines)
