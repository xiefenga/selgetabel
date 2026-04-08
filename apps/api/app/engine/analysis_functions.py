"""专项分析函数 - 支持 L3 专项分析场景"""

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Any, Tuple
from collections import Counter

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


# ============ 数据类定义 ============


@dataclass
class CorrelationResult:
    """相关性分析结果"""
    column_a: str
    column_b: str
    pearson_r: float  # 皮尔逊相关系数
    p_value: float  # p 值
    interpretation: str  # 解读
    strength: str  # "strong", "moderate", "weak", "none"


@dataclass
class ComparisonResult:
    """对比分析结果"""
    group_column: str
    metric_columns: List[str]
    groups: List[str]
    group_stats: Dict[str, Dict[str, float]]  # group -> metric -> value
    differences: Dict[str, Dict[str, float]]  # metric -> group_a -> (group_b -> diff)
    significant_diffs: List[str]  # 显著差异的描述


@dataclass
class TrendResult:
    """趋势分析结果"""
    date_column: str
    value_column: str
    trend_direction: str  # "increasing", "decreasing", "stable", "volatile"
    overall_change: float  # 整体变化百分比
    period_stats: List[Dict[str, Any]]  # 各时期统计
    seasonality: Optional[str]  # 季节性模式
    volatility: str  # 波动程度


@dataclass
class DistributionResult:
    """分布分析结果"""
    column: str
    total_count: int
    unique_count: int
    distribution_type: str  # "normal", "skewed_left", "skewed_right", "uniform", "bimodal"
    central_tendency: Dict[str, float]  # 均值、中位数、众数
    dispersion: Dict[str, float]  # 标准差、四分位距
    histogram: List[Dict[str, Any]]  # 直方图区间
    percentiles: Dict[str, float]  # 百分位数


# ============ 相关性分析 ============


def pearson_correlation(x: List[float], y: List[float]) -> Tuple[float, float]:
    """
    计算皮尔逊相关系数

    Args:
        x: 第一个变量
        y: 第二个变量

    Returns:
        (r, p_value) - 相关系数和 p 值
    """
    if len(x) != len(y) or len(x) < 3:
        return 0.0, 1.0

    try:
        # 转换为 numpy 数组
        x_arr = np.array(x, dtype=float)
        y_arr = np.array(y, dtype=float)

        # 计算相关系数
        r = np.corrcoef(x_arr, y_arr)[0, 1]

        # 计算 p 值（使用 t 分布近似，不依赖 scipy）
        n = len(x)
        if n > 2 and abs(r) < 1:
            t = r * np.sqrt((n - 2) / (1 - r ** 2))
            # 简化 p 值估算（基于 t 分布自由度 n-2）
            # 使用线性近似：当 |t| > 2 时 p < 0.05, |t| > 3 时 p < 0.01
            abs_t = abs(t)
            if abs_t > 4:
                p_value = 0.001
            elif abs_t > 3:
                p_value = 0.01
            elif abs_t > 2:
                p_value = 0.05
            else:
                p_value = 0.1 + (2 - abs_t) * 0.1
        else:
            p_value = 1.0

        return r, p_value
    except Exception:
        return 0.0, 1.0


def interpret_correlation(r: float, p_value: float = 0.05) -> Tuple[str, str]:
    """
    解读相关性

    Args:
        r: 相关系数
        p_value: p 值

    Returns:
        (strength, interpretation)
    """
    abs_r = abs(r)

    # 强度判断
    if abs_r >= 0.8:
        strength = "强相关"
    elif abs_r >= 0.5:
        strength = "中等相关"
    elif abs_r >= 0.3:
        strength = "弱相关"
    else:
        strength = "几乎无相关"

    # 方向判断
    direction = "正" if r >= 0 else "负"

    # 显著性判断
    significance = "显著" if p_value < 0.05 else "不显著"

    interpretation = f"{strength}（{direction}相关，{significance}）"

    return strength.lower().replace("相关", ""), interpretation


def correlation_analysis(df: pd.DataFrame, col_a: str, col_b: str) -> CorrelationResult:
    """
    对两列进行相关性分析

    Args:
        df: DataFrame
        col_a: 第一列名
        col_b: 第二列名

    Returns:
        CorrelationResult
    """
    # 获取有效数据
    valid_mask = df[col_a].notna() & df[col_b].notna()
    x = df.loc[valid_mask, col_a].astype(float).tolist()
    y = df.loc[valid_mask, col_b].astype(float).tolist()

    if len(x) < 3:
        return CorrelationResult(
            column_a=col_a,
            column_b=col_b,
            pearson_r=0.0,
            p_value=1.0,
            interpretation="数据不足",
            strength="none"
        )

    r, p_value = pearson_correlation(x, y)
    strength, interpretation = interpret_correlation(r, p_value)

    return CorrelationResult(
        column_a=col_a,
        column_b=col_b,
        pearson_r=r,
        p_value=p_value,
        interpretation=interpretation,
        strength=strength
    )


def format_correlation_for_llm(result: CorrelationResult) -> str:
    """将相关性结果格式化为 LLM 可读的文本"""
    lines = [
        f"## 相关性分析：{result.column_a} vs {result.column_b}",
        f"- 皮尔逊相关系数 r = {result.pearson_r:.4f}",
        f"- p 值 = {result.p_value:.4f}",
        f"- 解读：{result.interpretation}",
    ]
    return "\n".join(lines)


# ============ 对比分析 ============


def group_comparison(
    df: pd.DataFrame,
    group_by: str,
    metric_columns: List[str]
) -> ComparisonResult:
    """
    分组对比分析

    Args:
        df: DataFrame
        group_by: 分组列
        metric_columns: 指标列

    Returns:
        ComparisonResult
    """
    groups = df[group_by].dropna().unique().tolist()

    group_stats = {}
    for group in groups:
        group_data = df[df[group_by] == group]
        stats = {}
        for col in metric_columns:
            if col in df.columns:
                col_data = pd.to_numeric(group_data[col], errors='coerce')
                valid_data = col_data.dropna()
                if len(valid_data) > 0:
                    stats[col] = {
                        "sum": float(valid_data.sum()),
                        "mean": float(valid_data.mean()),
                        "count": int(len(valid_data)),
                        "std": float(valid_data.std()) if len(valid_data) > 1 else 0
                    }
        group_stats[str(group)] = stats

    # 计算组间差异
    differences = {}
    significant_diffs = []

    if len(groups) >= 2:
        for col in metric_columns:
            if col not in group_stats.get(str(groups[0]), {}):
                continue

            col_diffs = {}
            base_stats = group_stats[str(groups[0])][col]

            for i, group in enumerate(groups[1:], 1):
                if col not in group_stats.get(str(group), {}):
                    continue

                compare_stats = group_stats[str(group)][col]
                # 计算均值差异
                mean_diff = compare_stats["mean"] - base_stats["mean"]
                pct_diff = (mean_diff / base_stats["mean"] * 100) if base_stats["mean"] != 0 else 0

                col_diffs[str(group)] = {
                    "absolute": mean_diff,
                    "percentage": pct_diff
                }

                # 判断显著性（简单判断：差异超过 20%）
                if abs(pct_diff) > 20:
                    significant_diffs.append(
                        f"{col}在{groups[0]}和{group}之间差异显著（{pct_diff:+.1f}%）"
                    )

            if col_diffs:
                differences[col] = col_diffs

    return ComparisonResult(
        group_column=group_by,
        metric_columns=metric_columns,
        groups=[str(g) for g in groups],
        group_stats=group_stats,
        differences=differences,
        significant_diffs=significant_diffs
    )


def format_comparison_for_llm(result: ComparisonResult) -> str:
    """将对比结果格式化为 LLM 可读的文本"""
    lines = [
        f"## 对比分析：按 [{result.group_column}] 分组",
        f"\n### 分组列表：{', '.join(result.groups)}",
    ]

    # 各组统计
    lines.append("\n### 各组统计：")
    for group, stats in result.group_stats.items():
        lines.append(f"\n**{group}**：")
        for metric, values in stats.items():
            lines.append(
                f"  - {metric}: 总和={values['sum']:.2f}, "
                f"均值={values['mean']:.2f}, 样本数={values['count']}"
            )

    # 显著差异
    if result.significant_diffs:
        lines.append("\n### 显著差异：")
        for diff in result.significant_diffs:
            lines.append(f"- {diff}")

    return "\n".join(lines)


# ============ 趋势分析 ============


def trend_analysis(
    df: pd.DataFrame,
    date_column: str,
    value_column: str,
    freq: str = "ME"  # 月度
) -> TrendResult:
    """
    趋势分析

    Args:
        df: DataFrame
        date_column: 日期列
        value_column: 数值列
        freq: 聚合频率（"ME"月度, "QE"季度, "YE"年度）

    Returns:
        TrendResult
    """
    # 转换日期
    df = df.copy()
    df[date_column] = pd.to_datetime(df[date_column], errors='coerce')
    df = df.dropna(subset=[date_column, value_column])

    if len(df) < 3:
        return TrendResult(
            date_column=date_column,
            value_column=value_column,
            trend_direction="unknown",
            overall_change=0.0,
            period_stats=[],
            seasonality=None,
            volatility="unknown"
        )

    # 按时间聚合
    df_grouped = df.set_index(date_column)[value_column]
    resampled = df_grouped.resample(freq).agg(["sum", "mean", "count"])

    period_stats = []
    for idx, row in resampled.iterrows():
        period_stats.append({
            "period": idx.strftime("%Y-%m") if hasattr(idx, 'strftime') else str(idx),
            "sum": float(row["sum"]) if pd.notna(row["sum"]) else 0,
            "mean": float(row["mean"]) if pd.notna(row["mean"]) else 0,
            "count": int(row["count"]) if pd.notna(row["count"]) else 0
        })

    # 计算整体趋势
    values = resampled["sum"].dropna().values
    if len(values) >= 2:
        # 简单线性回归
        x = np.arange(len(values))
        coeffs = np.polyfit(x, values, 1)
        slope = coeffs[0]

        # 计算整体变化百分比
        first_val = values[0]
        last_val = values[-1]
        if first_val != 0:
            overall_change = ((last_val - first_val) / abs(first_val)) * 100
        else:
            overall_change = 0.0

        # 判断趋势方向
        if slope > values.mean() * 0.05:
            trend_direction = "increasing"
        elif slope < -values.mean() * 0.05:
            trend_direction = "decreasing"
        else:
            trend_direction = "stable"

        # 计算波动性
        std = np.std(values)
        mean = np.mean(values)
        cv = std / mean if mean != 0 else 0

        if cv > 0.5:
            volatility = "高波动"
        elif cv > 0.2:
            volatility = "中等波动"
        else:
            volatility = "稳定"
    else:
        trend_direction = "stable"
        overall_change = 0.0
        volatility = "数据不足"

    # 简化季节性检测
    seasonality = None

    return TrendResult(
        date_column=date_column,
        value_column=value_column,
        trend_direction=trend_direction,
        overall_change=overall_change,
        period_stats=period_stats,
        seasonality=seasonality,
        volatility=volatility
    )


def format_trend_for_llm(result: TrendResult) -> str:
    """将趋势结果格式化为 LLM 可读的文本"""
    trend_emoji = {
        "increasing": "📈",
        "decreasing": "📉",
        "stable": "➡️",
        "unknown": "❓"
    }

    lines = [
        f"## 趋势分析：{result.value_column}（按时间）",
        f"- 趋势方向：{trend_emoji.get(result.trend_direction, '')} {result.trend_direction}",
        f"- 整体变化：{result.overall_change:+.1f}%",
        f"- 波动程度：{result.volatility}",
    ]

    if result.period_stats:
        lines.append("\n### 各时期统计：")
        for stat in result.period_stats[-6:]:  # 只显示最近6期
            lines.append(
                f"- {stat['period']}: 总量={stat['sum']:.2f}, "
                f"均值={stat['mean']:.2f}, 数量={stat['count']}"
            )

    return "\n".join(lines)


# ============ 分布分析 ============


def distribution_stats(
    df: pd.DataFrame,
    column: str,
    bins: int = 10
) -> DistributionResult:
    """
    分布统计

    Args:
        df: DataFrame
        column: 列名
        bins: 直方图区间数

    Returns:
        DistributionResult
    """
    data = pd.to_numeric(df[column], errors='coerce').dropna()

    if len(data) == 0:
        return DistributionResult(
            column=column,
            total_count=0,
            unique_count=0,
            distribution_type="unknown",
            central_tendency={},
            dispersion={},
            histogram=[],
            percentiles={}
        )

    total_count = len(data)
    unique_count = data.nunique()

    # 中心趋势
    mean_val = float(data.mean())
    median_val = float(data.median())
    mode_val = float(data.mode().iloc[0]) if len(data.mode()) > 0 else mean_val

    central_tendency = {
        "mean": mean_val,
        "median": median_val,
        "mode": mode_val
    }

    # 离散程度
    std_val = float(data.std())
    q1 = float(data.quantile(0.25))
    q3 = float(data.quantile(0.75))
    iqr = q3 - q1

    dispersion = {
        "std": std_val,
        "min": float(data.min()),
        "max": float(data.max()),
        "q1": q1,
        "q3": q3,
        "iqr": iqr
    }

    # 百分位数
    percentiles = {
        "p10": float(data.quantile(0.1)),
        "p25": q1,
        "p50": median_val,
        "p75": q3,
        "p90": float(data.quantile(0.9)),
        "p95": float(data.quantile(0.95)),
        "p99": float(data.quantile(0.99))
    }

    # 直方图
    hist_values, bin_edges = np.histogram(data, bins=min(bins, 20))
    histogram = []
    for i in range(len(hist_values)):
        histogram.append({
            "range": f"{bin_edges[i]:.2f}-{bin_edges[i+1]:.2f}",
            "count": int(hist_values[i]),
            "percentage": float(hist_values[i] / total_count * 100)
        })

    # 分布形态判断
    skewness = float(data.skew())

    if abs(skewness) < 0.5:
        dist_type = "normal"
    elif skewness > 0.5:
        dist_type = "skewed_right"
    elif skewness < -0.5:
        dist_type = "skewed_left"
    else:
        dist_type = "unknown"

    return DistributionResult(
        column=column,
        total_count=total_count,
        unique_count=unique_count,
        distribution_type=dist_type,
        central_tendency=central_tendency,
        dispersion=dispersion,
        histogram=histogram,
        percentiles=percentiles
    )


def format_distribution_for_llm(result: DistributionResult) -> str:
    """将分布结果格式化为 LLM 可读的文本"""
    dist_emoji = {
        "normal": "📊",
        "skewed_right": "📈",
        "skewed_left": "📉",
        "uniform": "➡️",
        "bimodal": "📊📊",
        "unknown": "❓"
    }

    lines = [
        f"## 分布分析：{result.column}",
        f"- 总数：{result.total_count}",
        f"- 唯一值：{result.unique_count}",
        f"- 分布形态：{dist_emoji.get(result.distribution_type, '')} {result.distribution_type}",
        "",
        "### 中心趋势：",
        f"- 均值：{result.central_tendency['mean']:.2f}",
        f"- 中位数：{result.central_tendency['median']:.2f}",
        f"- 众数：{result.central_tendency['mode']:.2f}",
        "",
        "### 离散程度：",
        f"- 标准差：{result.dispersion['std']:.2f}",
        f"- 范围：{result.dispersion['min']:.2f} ~ {result.dispersion['max']:.2f}",
        f"- 四分位距：{result.dispersion['iqr']:.2f}",
    ]

    # 主要分布区间
    if result.histogram:
        lines.append("\n### 主要分布区间：")
        sorted_hist = sorted(result.histogram, key=lambda x: x["count"], reverse=True)
        for item in sorted_hist[:5]:
            lines.append(
                f"- {item['range']}: {item['count']}条 ({item['percentage']:.1f}%)"
            )

    return "\n".join(lines)


# ============ 交叉分布表 ============


def cross_tabulation(
    df: pd.DataFrame,
    col_a: str,
    col_b: str,
    normalize: bool = False
) -> Dict[str, Any]:
    """
    交叉分布表

    Args:
        df: DataFrame
        col_a: 第一列
        col_b: 第二列
        normalize: 是否计算百分比

    Returns:
        交叉表字典
    """
    crosstab = pd.crosstab(
        df[col_a],
        df[col_b],
        normalize=normalize if normalize else False
    )

    result = {
        "rows": col_a,
        "columns": col_b,
        "values": crosstab.to_dict(),
        "row_totals": crosstab.sum(axis=1).to_dict(),
        "col_totals": crosstab.sum(axis=0).to_dict(),
        "total": crosstab.sum().sum()
    }

    if normalize:
        result["percentages"] = result["values"]

    return result


def format_crosstab_for_llm(crosstab: Dict[str, Any]) -> str:
    """将交叉表格式化为 LLM 可读的文本"""
    lines = [
        f"## 交叉分布表：{crosstab['rows']} × {crosstab['columns']}",
        f"- 行数：{len(crosstab['row_totals'])}",
        f"- 列数：{len(crosstab['col_totals'])}",
        f"- 总计：{crosstab['total']:.0f}",
    ]

    return "\n".join(lines)


# ============ 工具函数 ============


def get_numeric_columns(df: pd.DataFrame) -> List[str]:
    """获取所有数值列"""
    numeric_cols = []
    for col in df.columns:
        if pd.api.types.is_numeric_dtype(df[col]):
            numeric_cols.append(col)
        else:
            # 尝试转换
            try:
                pd.to_numeric(df[col], errors='coerce')
                numeric_cols.append(col)
            except:
                pass
    return numeric_cols


def get_date_columns(df: pd.DataFrame) -> List[str]:
    """获取所有日期列"""
    date_cols = []
    for col in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[col]):
            date_cols.append(col)
    return date_cols


def get_categorical_columns(df: pd.DataFrame, max_unique: int = 100) -> List[str]:
    """获取所有类别列（唯一值数量有限的列）"""
    cat_cols = []
    for col in df.columns:
        unique_count = df[col].nunique()
        if unique_count <= max_unique and unique_count > 0:
            cat_cols.append(col)
    return cat_cols
