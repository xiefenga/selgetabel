"""数据画像提取器 - 从 Table 提取结构化统计特征"""

import logging
import random
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any, Tuple
from collections import Counter

import pandas as pd
import numpy as np

from app.engine.models import Table

logger = logging.getLogger(__name__)


# ============ 数据类定义 ============


@dataclass
class ColumnProfile:
    """单列画像"""
    name: str
    type: str  # "number", "text", "date", "boolean", "mixed"
    null_count: int = 0
    null_ratio: float = 0.0
    unique_count: int = 0
    total_count: int = 0

    # 数值列特有
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    mean_value: Optional[float] = None
    median_value: Optional[float] = None
    std_value: Optional[float] = None
    q1_value: Optional[float] = None
    q3_value: Optional[float] = None

    # 文本列特有
    top_values: List[Dict[str, int]] = field(default_factory=list)  # [{"value": count}, ...]
    avg_length: Optional[float] = None
    min_length: Optional[int] = None
    max_length: Optional[int] = None

    # 建议
    suggestion: Optional[str] = None  # 如 "高基数文本，可考虑哈希编码"


@dataclass
class TableProfile:
    """单表画像"""
    table_name: str
    row_count: int
    column_count: int
    is_sampled: bool = False
    sample_ratio: Optional[float] = None
    columns: List[ColumnProfile] = field(default_factory=list)
    date_columns: List[str] = field(default_factory=list)  # 推断出的日期列
    numeric_columns: List[str] = field(default_factory=list)  # 数值列
    text_columns: List[str] = field(default_factory=list)  # 文本列
    suggestions: List[str] = field(default_factory=list)  # 整体建议


@dataclass
class Relationship:
    """表关系"""
    from_table: str
    from_column: str
    to_table: str
    to_column: str
    match_ratio: float  # 匹配率 0-1
    relationship_type: str  # "exact", "contains", "inferred"


@dataclass
class MultiTableProfile:
    """多表画像"""
    profiles: Dict[str, TableProfile] = field(default_factory=dict)  # table_name -> TableProfile
    relationships: List[Relationship] = field(default_factory=list)
    cross_table_suggestions: List[str] = field(default_factory=list)


# ============ 列类型推断 ============


def infer_column_type(series: pd.Series) -> str:
    """推断列类型"""
    # 去除空值
    non_null = series.dropna()

    if len(non_null) == 0:
        return "unknown"

    # 检查是否全为数值
    if pd.api.types.is_numeric_dtype(series):
        return "number"

    # 检查是否为日期
    if pd.api.types.is_datetime64_any_dtype(series):
        return "date"

    # 检查布尔
    unique_vals = set(non_null.unique())
    if len(unique_vals) <= 2:
        sample = list(unique_vals)[0]
        if isinstance(sample, bool) or str(sample).lower() in ('true', 'false', '1', '0', 'yes', 'no'):
            return "boolean"

    # 文本类型
    return "text"


# ============ 列画像提取 ============


def profile_column(series: pd.Series, column_name: str, sample_count: int = 20) -> ColumnProfile:
    """提取单列统计特征"""
    total_count = len(series)
    null_count = series.isna().sum()
    null_ratio = null_count / total_count if total_count > 0 else 0

    non_null = series.dropna()
    unique_count = non_null.nunique()

    col_type = infer_column_type(series)

    profile = ColumnProfile(
        name=column_name,
        type=col_type,
        null_count=null_count,
        null_ratio=null_ratio,
        unique_count=unique_count,
        total_count=total_count
    )

    if col_type == "number":
        # 数值列统计
        numeric_data = pd.to_numeric(non_null, errors='coerce').dropna()
        if len(numeric_data) > 0:
            profile.min_value = float(numeric_data.min())
            profile.max_value = float(numeric_data.max())
            profile.mean_value = float(numeric_data.mean())
            profile.median_value = float(numeric_data.median())
            profile.std_value = float(numeric_data.std()) if len(numeric_data) > 1 else 0
            q1, q3 = numeric_data.quantile([0.25, 0.75])
            profile.q1_value = float(q1)
            profile.q3_value = float(q3)

            # 检测异常值（简单启发式）
            if profile.std_value and profile.std_value > 0:
                z_scores = np.abs((numeric_data - profile.mean_value) / profile.std_value)
                outlier_count = (z_scores > 3).sum()
                if outlier_count > 0:
                    outlier_ratio = outlier_count / len(numeric_data)
                    if outlier_ratio > 0.01:
                        profile.suggestion = f"检测到 {outlier_count} 个异常值（约 {outlier_ratio:.1%}），建议检查"

    elif col_type == "text":
        # 文本列统计
        str_data = non_null.astype(str)

        # 长度统计
        lengths = str_data.str.len()
        profile.avg_length = float(lengths.mean())
        profile.min_length = int(lengths.min())
        profile.max_length = int(lengths.max())

        # 高频值
        value_counts = non_null.value_counts().head(sample_count)
        profile.top_values = [{"value": str(k), "count": int(v)} for k, v in value_counts.items()]

        # 高基数检测
        unique_ratio = unique_count / len(non_null) if len(non_null) > 0 else 0
        if unique_ratio > 0.9 and unique_count > 100:
            profile.suggestion = "高基数文本列，可能不适合作为分组维度"

    elif col_type == "date":
        # 日期列
        pass

    return profile


# ============ 分层采样 ============


def stratified_sample(df: pd.DataFrame, max_rows: int, stratify_column: Optional[str] = None) -> Tuple[pd.DataFrame, bool]:
    """
    分层采样

    Args:
        df: 原始 DataFrame
        max_rows: 最大行数
        stratify_column: 分层列名（优先使用）

    Returns:
        (采样后的 DataFrame, 是否进行了采样)
    """
    if len(df) <= max_rows:
        return df, False

    if stratify_column and stratify_column in df.columns:
        # 按指定列分层采样
        stratify_col = df[stratify_column]
        sampled_dfs = []

        for value, group in df.groupby(stratify_col):
            # 按比例采样
            n_sample = max(1, int(len(group) * max_rows / len(df)))
            if n_sample < len(group):
                sampled_dfs.append(group.sample(n=min(n_sample, len(group)), random_state=42))
            else:
                sampled_dfs.append(group)

        result = pd.concat(sampled_dfs, ignore_index=True)
    else:
        # 随机采样
        result = df.sample(n=max_rows, random_state=42)

    return result, True


# ============ DataProfiler 主类 ============


class DataProfiler:
    """
    数据画像提取器

    职责：
    1. 提取单表统计特征
    2. 识别表间关系
    3. 分层采样
    """

    # 常见日期列名模式
    DATE_COLUMN_PATTERNS = [
        'date', '日期', '时间', 'created', 'updated', 'time', 'datetime',
        '日', '月', '年', 'birth', '生日', '注册'
    ]

    # 采样阈值
    SAMPLE_THRESHOLD = 2000

    def __init__(self, sample_threshold: int = 2000):
        """
        初始化画像提取器

        Args:
            sample_threshold: 采样阈值，超过此行数进行采样
        """
        self.sample_threshold = sample_threshold

    def profile_table(self, table: Table, for_llm: bool = True) -> TableProfile:
        """
        提取单表的画像

        Args:
            table: Table 对象
            for_llm: 是否为 LLM 分析准备（会进行采样）

        Returns:
            TableProfile
        """
        df = table.get_data()

        # 判断是否需要采样
        need_sample = for_llm and len(df) > self.sample_threshold
        sample_ratio = None

        if need_sample:
            # 找出适合分层的列（低基数文本列）
            stratify_col = self._find_stratify_column(df)
            df, _ = stratified_sample(df, self.sample_threshold, stratify_col)
            sample_ratio = len(df) / table.row_count()

        # 提取每列画像
        columns = []
        date_columns = []
        numeric_columns = []
        text_columns = []

        for col_name in df.columns:
            series = df[col_name]
            col_profile = profile_column(series, col_name)
            columns.append(col_profile)

            if col_profile.type == "date":
                date_columns.append(col_name)
            elif col_profile.type == "number":
                numeric_columns.append(col_name)
            elif col_profile.type == "text":
                text_columns.append(col_name)

        # 生成建议
        suggestions = self._generate_suggestions(columns, table.row_count())

        profile = TableProfile(
            table_name=table.name,
            row_count=len(df),
            column_count=len(columns),
            is_sampled=need_sample,
            sample_ratio=sample_ratio,
            columns=columns,
            date_columns=date_columns,
            numeric_columns=numeric_columns,
            text_columns=text_columns,
            suggestions=suggestions
        )

        return profile

    def profile_tables(self, tables: "FileCollection", for_llm: bool = True) -> MultiTableProfile:
        """
        提取多表画像，识别表关系

        Args:
            tables: FileCollection 对象
            for_llm: 是否为 LLM 分析准备

        Returns:
            MultiTableProfile
        """
        from app.engine.models import FileCollection

        profiles: Dict[str, TableProfile] = {}
        relationships: List[Relationship] = []

        # 1. 提取每个表的画像
        for file_id in tables.get_file_ids():
            excel_file = tables.get_file(file_id)
            for sheet_name in excel_file.get_sheet_names():
                table = excel_file.get_sheet(sheet_name)
                profile = self.profile_table(table, for_llm=for_llm)
                profiles[f"{file_id}.{sheet_name}"] = profile

        # 2. 识别表关系
        relationships = self.detect_relationships(profiles)

        # 3. 生成跨表建议
        cross_suggestions = self._generate_cross_table_suggestions(profiles, relationships)

        return MultiTableProfile(
            profiles=profiles,
            relationships=relationships,
            cross_table_suggestions=cross_suggestions
        )

    def detect_relationships(self, profiles: Dict[str, TableProfile]) -> List[Relationship]:
        """
        检测表间关系

        策略：
        1. 列名匹配（完全匹配 / 包含匹配）
        2. 样本值验证（匹配率 > 80% 则认为有关联）

        Args:
            profiles: 表名 -> TableProfile 的映射

        Returns:
            识别到的关系列表
        """
        relationships: List[Relationship] = []
        table_names = list(profiles.keys())

        # 构建列信息索引
        column_info: Dict[str, List[Tuple[str, ColumnProfile]]] = {}  # col_name_lower -> [(table_name, profile), ...]
        for table_name, profile in profiles.items():
            for col_profile in profile.columns:
                col_key = col_profile.name.lower()
                if col_key not in column_info:
                    column_info[col_key] = []
                column_info[col_key].append((table_name, col_profile))

        # 检测关系
        for col_key, info_list in column_info.items():
            if len(info_list) < 2:
                continue

            for i, (table_a, profile_a) in enumerate(info_list):
                for table_b, profile_b in info_list[i + 1:]:
                    if table_a == table_b:
                        continue

                    # 获取列样本值
                    samples_a = [v["value"] for v in profile_a.top_values[:10]]
                    samples_b = [v["value"] for v in profile_b.top_values[:10]]

                    # 计算匹配率
                    set_a, set_b = set(samples_a), set(samples_b)
                    if len(set_a) == 0 or len(set_b) == 0:
                        continue

                    intersection = len(set_a & set_b)
                    match_ratio = intersection / min(len(set_a), len(set_b))

                    if match_ratio > 0.8:
                        relationships.append(Relationship(
                            from_table=table_a,
                            from_column=profile_a.name,
                            to_table=table_b,
                            to_column=profile_b.name,
                            match_ratio=match_ratio,
                            relationship_type="exact" if match_ratio > 0.95 else "contains"
                        ))

        return relationships

    def _find_stratify_column(self, df: pd.DataFrame) -> Optional[str]:
        """找出适合分层的列"""
        for col in df.columns:
            series = df[col]
            unique_ratio = series.nunique() / len(series) if len(series) > 0 else 0
            # 选择低基数文本列作为分层列
            if unique_ratio < 0.1 and unique_ratio > 0 and pd.api.types.is_string_dtype(series):
                return col
        return None

    def _generate_suggestions(self, columns: List[ColumnProfile], total_rows: int) -> List[str]:
        """生成单表建议"""
        suggestions = []

        # 空值检测
        for col in columns:
            if col.null_ratio > 0.3:
                suggestions.append(f"'{col.name}' 列空值率较高（{col.null_ratio:.1%}），建议处理")
            elif col.null_ratio > 0.1:
                suggestions.append(f"'{col.name}' 列有少量空值（{col.null_ratio:.1%}）")

        # 混合类型检测
        for col in columns:
            if col.type == "mixed":
                suggestions.append(f"'{col.name}' 列存在混合类型数据，建议统一格式")

        # 数值列离群点
        for col in columns:
            if col.suggestion and "异常值" in col.suggestion:
                suggestions.append(f"'{col.name}': {col.suggestion}")

        return suggestions

    def _generate_cross_table_suggestions(
        self,
        profiles: Dict[str, TableProfile],
        relationships: List[Relationship]
    ) -> List[str]:
        """生成跨表建议"""
        suggestions = []

        if len(profiles) > 1:
            suggestions.append(f"检测到 {len(profiles)} 个表，可能存在关联")

        if relationships:
            suggestions.append(f"检测到 {len(relationships)} 个可能的表间关联")

        return suggestions

    def format_profile_for_llm(self, profile: TableProfile) -> str:
        """
        将画像格式化为 LLM 可读的文本

        Args:
            profile: TableProfile 对象

        Returns:
            格式化的文本
        """
        lines = [
            f"## 表：{profile.table_name}",
            f"- 行数：{profile.row_count} {'（已采样）' if profile.is_sampled else ''}",
            f"- 列数：{profile.column_count}",
            "",
            "### 列信息："
        ]

        for col in profile.columns:
            lines.append(f"\n**{col.name}**（{col.type}）：")

            if col.type == "number":
                lines.append(f"  - 范围：{col.min_value:.2f} ~ {col.max_value:.2f}")
                lines.append(f"  - 均值：{col.mean_value:.2f}，中位数：{col.median_value:.2f}")
                lines.append(f"  - 标准差：{col.std_value:.2f}")
                if col.null_ratio > 0:
                    lines.append(f"  - 空值率：{col.null_ratio:.1%}")
            elif col.type == "text":
                lines.append(f"  - 唯一值：{col.unique_count}")
                top_vals_str = ", ".join([f"{v['value']}({v['count']})" for v in col.top_values[:5]])
                lines.append(f"  - 高频值：{top_vals_str}")
                if col.null_ratio > 0:
                    lines.append(f"  - 空值率：{col.null_ratio:.1%}")
                if col.avg_length:
                    lines.append(f"  - 平均长度：{col.avg_length:.1f}字符")
            else:
                lines.append(f"  - 唯一值：{col.unique_count}")
                if col.null_ratio > 0:
                    lines.append(f"  - 空值率：{col.null_ratio:.1%}")

            if col.suggestion:
                lines.append(f"  - ⚠️ {col.suggestion}")

        if profile.suggestions:
            lines.append("\n### 建议：")
            for suggestion in profile.suggestions:
                lines.append(f"- {suggestion}")

        return "\n".join(lines)

    def format_multi_profile_for_llm(self, multi_profile: MultiTableProfile) -> str:
        """
        将多表画像格式化为 LLM 可读的文本

        Args:
            multi_profile: MultiTableProfile 对象

        Returns:
            格式化的文本
        """
        lines = ["## 数据概况\n"]

        # 每个表的画像
        for table_name, profile in multi_profile.profiles.items():
            lines.append(self.format_profile_for_llm(profile))
            lines.append("")

        # 表关系
        if multi_profile.relationships:
            lines.append("\n## 表间关系：")
            for rel in multi_profile.relationships:
                lines.append(
                    f"- {rel.from_table}.{rel.from_column} ↔ {rel.to_table}.{rel.to_column} "
                    f"（匹配率：{rel.match_ratio:.0%}）"
                )

        # 跨表建议
        if multi_profile.cross_table_suggestions:
            lines.append("\n## 跨表分析建议：")
            for suggestion in multi_profile.cross_table_suggestions:
                lines.append(f"- {suggestion}")

        return "\n".join(lines)
