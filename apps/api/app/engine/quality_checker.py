"""数据质量检测器 - 检测空值、重复、异常、格式问题"""

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple
from collections import Counter
import re

import pandas as pd
import numpy as np

from app.engine.models import Table

logger = logging.getLogger(__name__)


# ============ 数据类定义 ============


@dataclass
class NullCheckResult:
    """空值检测结果"""
    column: str
    null_count: int
    total_count: int
    null_ratio: float
    severity: str  # "ok", "warning", "error"


@dataclass
class DuplicateCheckResult:
    """重复检测结果"""
    total_rows: int
    duplicate_rows: int
    duplicate_ratio: float
    duplicate_examples: List[Dict[str, Any]] = field(default_factory=list)
    severity: str = "ok"


@dataclass
class AnomalyCheckResult:
    """异常值检测结果"""
    column: str
    anomaly_count: int
    total_count: int
    anomaly_ratio: float
    anomalies: List[Any] = field(default_factory=list)
    method: str = "sigma_3"  # 检测方法
    severity: str = "ok"


@dataclass
class FormatCheckResult:
    """格式一致性检测结果"""
    column: str
    format_count: int  # 检测到的格式数量
    formats: Dict[str, int] = field(default_factory=dict)  # 格式 -> 数量
    inconsistent_values: List[str] = field(default_factory=list)
    severity: str = "ok"


@dataclass
class TypeCheckResult:
    """类型推断结果"""
    column: str
    declared_type: str  # 声明的类型
    inferred_type: str  # 实际推断的类型
    is_consistent: bool
    sample_values: List[Any] = field(default_factory=list)


@dataclass
class QualityReport:
    """数据质量报告"""
    table_name: str
    row_count: int
    null_results: List[NullCheckResult] = field(default_factory=list)
    duplicate_result: Optional[DuplicateCheckResult] = None
    anomaly_results: List[AnomalyCheckResult] = field(default_factory=list)
    format_results: List[FormatCheckResult] = field(default_factory=list)
    type_results: List[TypeCheckResult] = field(default_factory=list)

    # 汇总
    overall_score: float = 100.0  # 0-100
    issues_count: int = 0
    warnings_count: int = 0
    suggestions: List[str] = field(default_factory=list)


# ============ 辅助函数 ============


def detect_date_formats(series: pd.Series) -> Dict[str, int]:
    """检测日期格式分布"""
    formats: Dict[str, int] = {}

    date_patterns = [
        (r'^\d{4}-\d{2}-\d{2}$', 'YYYY-MM-DD'),
        (r'^\d{4}/\d{2}/\d{2}$', 'YYYY/MM/DD'),
        (r'^\d{2}-\d{2}-\d{4}$', 'DD-MM-YYYY'),
        (r'^\d{2}/\d{2}/\d{4}$', 'DD/MM/YYYY'),
        (r'^\d{4}年\d{1,2}月\d{1,2}日$', 'YYYY年MM月DD日'),
        (r'^\d{1,2}月\d{1,2}日,?\s*\d{4}年$', 'MM月DD日,YYYY年'),
    ]

    for value in series.dropna().astype(str).unique():
        matched = False
        for pattern, format_name in date_patterns:
            if re.match(pattern, value.strip()):
                formats[format_name] = formats.get(format_name, 0) + 1
                matched = True
                break
        if not matched:
            formats['other'] = formats.get('other', 0) + 1

    return formats


def detect_number_formats(series: pd.Series) -> Dict[str, int]:
    """检测数值格式分布"""
    formats: Dict[str, int] = {}

    number_patterns = [
        (r'^-?\d+\.?\d*$', 'plain_number'),
        (r'^-?¥\d+\.?\d*$', 'CNY'),
        (r'^-?\$\d+\.?\d*$', 'USD'),
        (r'^-?€\d+\.?\d*$', 'EUR'),
        (r'^-?\d+\.?\d*%$', 'percentage'),
        (r'^-?\d{1,3}(,\d{3})*\.?\d*$', 'thousands_separator'),
    ]

    for value in series.dropna().astype(str).unique():
        matched = False
        for pattern, format_name in number_patterns:
            if re.match(pattern, value.strip()):
                formats[format_name] = formats.get(format_name, 0) + 1
                matched = True
                break
        if not matched:
            formats['other'] = formats.get('other', 0) + 1

    return formats


def detect_text_patterns(series: pd.Series) -> Dict[str, int]:
    """检测文本模式分布"""
    patterns: Dict[str, int] = {}

    for value in series.dropna().astype(str).unique():
        if len(value) < 5:
            patterns['short_text'] = patterns.get('short_text', 0) + 1
        elif len(value) < 20:
            patterns['medium_text'] = patterns.get('medium_text', 0) + 1
        else:
            patterns['long_text'] = patterns.get('long_text', 0) + 1

    return patterns


# ============ QualityChecker 主类 ============


class QualityChecker:
    """
    数据质量检测器

    检测项：
    1. 空值检测
    2. 重复检测
    3. 异常值检测（3σ 原则）
    4. 格式一致性检测
    5. 类型一致性检测
    """

    # 空值阈值
    NULL_WARNING_THRESHOLD = 0.05  # 5%
    NULL_ERROR_THRESHOLD = 0.3     # 30%

    # 重复阈值
    DUPLICATE_WARNING_THRESHOLD = 0.01  # 1%
    DUPLICATE_ERROR_THRESHOLD = 0.05    # 5%

    # 异常值阈值
    ANOMALY_THRESHOLD = 0.01  # 1%

    def __init__(self):
        pass

    def check_quality(self, table: Table) -> QualityReport:
        """
        执行全面的数据质量检测

        Args:
            table: Table 对象

        Returns:
            QualityReport
        """
        df = table.get_data()

        report = QualityReport(
            table_name=table.name,
            row_count=len(df)
        )

        # 1. 空值检测
        report.null_results = self.check_nulls(df)

        # 2. 重复检测
        report.duplicate_result = self.check_duplicates(df)

        # 3. 数值列异常检测
        report.anomaly_results = self.check_anomalies(df)

        # 4. 格式一致性检测
        report.format_results = self.check_format_consistency(df)

        # 5. 汇总评分
        self._summarize_report(report)

        return report

    def check_nulls(self, df: pd.DataFrame) -> List[NullCheckResult]:
        """检测每列的空值"""
        results = []

        for col in df.columns:
            null_count = df[col].isna().sum()
            null_ratio = null_count / len(df) if len(df) > 0 else 0

            if null_ratio >= self.NULL_ERROR_THRESHOLD:
                severity = "error"
            elif null_ratio >= self.NULL_WARNING_THRESHOLD:
                severity = "warning"
            else:
                severity = "ok"

            results.append(NullCheckResult(
                column=col,
                null_count=null_count,
                total_count=len(df),
                null_ratio=null_ratio,
                severity=severity
            ))

        return results

    def check_duplicates(self, df: pd.DataFrame) -> DuplicateCheckResult:
        """检测完全重复的行"""
        duplicate_rows = df.duplicated().sum()
        duplicate_ratio = duplicate_rows / len(df) if len(df) > 0 else 0

        if duplicate_ratio >= self.DUPLICATE_ERROR_THRESHOLD:
            severity = "error"
        elif duplicate_ratio >= self.DUPLICATE_WARNING_THRESHOLD:
            severity = "warning"
        else:
            severity = "ok"

        # 获取重复行示例
        duplicate_examples = []
        if duplicate_rows > 0:
            dup_mask = df.duplicated(keep=False)
            dup_df = df[dup_mask].head(5)
            for _, row in dup_df.iterrows():
                duplicate_examples.append(row.to_dict())

        return DuplicateCheckResult(
            total_rows=len(df),
            duplicate_rows=int(duplicate_rows),
            duplicate_ratio=duplicate_ratio,
            severity=severity,
            duplicate_examples=duplicate_examples
        )

    def check_anomalies(self, df: pd.DataFrame) -> List[AnomalyCheckResult]:
        """检测数值列的异常值（3σ 原则）"""
        results = []

        for col in df.columns:
            if not pd.api.types.is_numeric_dtype(df[col]):
                continue

            # 转换为数值，非数值变 NaN
            numeric_data = pd.to_numeric(df[col], errors='coerce').dropna()

            if len(numeric_data) < 3:
                continue

            # 计算 3σ 范围
            mean = numeric_data.mean()
            std = numeric_data.std()

            if std == 0:
                continue

            # 标记超出 3σ 的值
            z_scores = np.abs((numeric_data - mean) / std)
            anomalies_mask = z_scores > 3
            anomaly_count = anomalies_mask.sum()
            anomaly_ratio = anomaly_count / len(numeric_data)

            if anomaly_ratio < self.ANOMALY_THRESHOLD:
                continue

            if anomaly_ratio >= 0.1:
                severity = "error"
            else:
                severity = "warning"

            # 获取异常值示例
            anomaly_values = numeric_data[anomalies_mask].head(10).tolist()

            results.append(AnomalyCheckResult(
                column=col,
                anomaly_count=int(anomaly_count),
                total_count=len(numeric_data),
                anomaly_ratio=anomaly_ratio,
                anomalies=anomaly_values,
                severity=severity
            ))

        return results

    def check_format_consistency(self, df: pd.DataFrame) -> List[FormatCheckResult]:
        """检测格式一致性"""
        results = []

        for col in df.columns:
            series = df[col].dropna()

            if len(series) == 0:
                continue

            col_type = self._infer_type(series)

            if col_type == "date":
                formats = detect_date_formats(series)
            elif col_type == "number":
                formats = detect_number_formats(series)
            elif col_type == "text":
                formats = detect_text_patterns(series)
            else:
                continue

            # 如果只有一种格式，认为一致
            if len(formats) <= 1:
                continue

            # 多种格式混用
            inconsistent_values = []
            for value in series.head(20).astype(str):
                for pattern, format_name in formats.items():
                    if pattern != 'other' and re.match(pattern if '(' in pattern else pattern.split('(')[0], value):
                        if len(inconsistent_values) < 10:
                            inconsistent_values.append(value)
                        break

            results.append(FormatCheckResult(
                column=col,
                format_count=len(formats),
                formats=formats,
                severity="warning",
                inconsistent_values=inconsistent_values
            ))

        return results

    def _infer_type(self, series: pd.Series) -> str:
        """推断列类型"""
        if pd.api.types.is_numeric_dtype(series):
            return "number"
        if pd.api.types.is_datetime64_any_dtype(series):
            return "date"

        # 检查布尔
        unique_vals = set(series.astype(str).str.lower().unique())
        if unique_vals.issubset({'true', 'false', '1', '0', 'yes', 'no'}):
            return "boolean"

        return "text"

    def _summarize_report(self, report: QualityReport):
        """汇总质量报告"""
        # 统计问题数
        for result in report.null_results:
            if result.severity == "error":
                report.issues_count += 1
            elif result.severity == "warning":
                report.warnings_count += 1

        if report.duplicate_result:
            if report.duplicate_result.severity == "error":
                report.issues_count += 1
            elif report.duplicate_result.severity == "warning":
                report.warnings_count += 1

        for result in report.anomaly_results:
            if result.severity == "error":
                report.issues_count += 1
            elif result.severity == "warning":
                report.warnings_count += 1

        for result in report.format_results:
            if result.severity == "warning":
                report.warnings_count += 1

        # 计算评分
        score = 100.0
        score -= report.issues_count * 10
        score -= report.warnings_count * 2
        report.overall_score = max(0, score)

        # 生成建议
        for result in report.null_results:
            if result.severity == "error":
                report.suggestions.append(
                    f"'{result.column}' 列空值率过高（{result.null_ratio:.1%}），建议填充或删除"
                )
            elif result.severity == "warning":
                report.suggestions.append(
                    f"'{result.column}' 列有少量空值（{result.null_ratio:.1%}）"
                )

        if report.duplicate_result:
            if report.duplicate_result.severity == "error":
                report.suggestions.append(
                    f"存在 {report.duplicate_result.duplicate_rows} 条重复数据（{report.duplicate_result.duplicate_ratio:.1%}），建议去重"
                )
            elif report.duplicate_result.severity == "warning":
                report.suggestions.append(
                    f"存在少量重复数据（{report.duplicate_result.duplicate_ratio:.1%}）"
                )

        for result in report.anomaly_results:
            if result.severity in ("error", "warning"):
                report.suggestions.append(
                    f"'{result.column}' 列检测到 {result.anomaly_count} 个异常值（{result.anomaly_ratio:.1%}），可能需要检查"
                )

        for result in report.format_results:
            if result.severity == "warning":
                format_str = ", ".join([f"{k}({v}条)" for k, v in result.formats.items()])
                report.suggestions.append(
                    f"'{result.column}' 列存在多种格式混用：{format_str}，建议统一"
                )

    def format_report_for_llm(self, report: QualityReport) -> str:
        """
        将质量报告格式化为 LLM 可读的文本

        Args:
            report: QualityReport 对象

        Returns:
            格式化的文本
        """
        lines = [
            f"## 数据质量报告：{report.table_name}",
            f"- 总行数：{report.row_count}",
            f"- 质量评分：{report.overall_score:.0f}/100",
            ""
        ]

        # 空值问题
        null_issues = [r for r in report.null_results if r.severity != "ok"]
        if null_issues:
            lines.append("### 空值问题：")
            for result in null_issues:
                emoji = "❌" if result.severity == "error" else "⚠️"
                lines.append(
                    f"  {emoji} '{result.column}'：{result.null_count}/{result.total_count} "
                    f"（{result.null_ratio:.1%}）"
                )
            lines.append("")

        # 重复问题
        if report.duplicate_result and report.duplicate_result.severity != "ok":
            emoji = "❌" if report.duplicate_result.severity == "error" else "⚠️"
            lines.append(
                f"### 重复数据：{emoji} {report.duplicate_result.duplicate_rows} 条"
                f"（{report.duplicate_result.duplicate_ratio:.1%}）"
            )
            lines.append("")

        # 异常值问题
        if report.anomaly_results:
            lines.append("### 异常值：")
            for result in report.anomaly_results:
                emoji = "❌" if result.severity == "error" else "⚠️"
                lines.append(
                    f"  {emoji} '{result.column}'：{result.anomaly_count} 个"
                    f"（{result.anomaly_ratio:.1%}），示例值：{result.anomalies[:3]}"
                )
            lines.append("")

        # 格式问题
        if report.format_results:
            lines.append("### 格式不一致：")
            for result in report.format_results:
                formats_str = ", ".join([f"{k}:{v}条" for k, v in result.formats.items()])
                lines.append(f"  ⚠️ '{result.column}'：{formats_str}")
            lines.append("")

        # 建议
        if report.suggestions:
            lines.append("### 处理建议：")
            for suggestion in report.suggestions:
                lines.append(f"- {suggestion}")

        if not any([null_issues, report.duplicate_result and report.duplicate_result.severity != "ok",
                    report.anomaly_results, report.format_results]):
            lines.append("✅ 未检测到明显的数据质量问题")

        return "\n".join(lines)
