"""数据分析阶段"""

import logging
import json
import pandas as pd
from dataclasses import asdict
from typing import Any, Dict, Generator, List, Optional, Tuple, TYPE_CHECKING

from ..types import ProcessStage, EventType, ProcessEvent, ProcessConfig
from .base import Stage
from .errors import StageError

if TYPE_CHECKING:
    from app.engine.models import FileCollection
    from app.engine.llm_client import LLMClient
    from app.engine.context_builder import ContextBuilder

logger = logging.getLogger(__name__)


def asdict_safe(obj):
    """安全转换为 dict，处理 dataclass"""
    if hasattr(obj, '__dataclass_fields__'):
        result = {}
        for field_name, field_def in obj.__dataclass_fields__.items():
            value = getattr(obj, field_name)
            if isinstance(value, list):
                result[field_name] = [asdict_safe(v) if hasattr(v, '__dataclass_fields__') else v for v in value]
            elif hasattr(value, '__dataclass_fields__'):
                result[field_name] = asdict_safe(value)
            else:
                result[field_name] = value
        return result
    return obj


class AnalysisStage(Stage):
    """
    数据分析阶段

    流程：
    1. 检测分析场景（从查询和上下文中识别）
    2. 提取数据画像（DataProfiler）
    3. 数据质量检测（QualityChecker）
    4. 根据场景进行专项处理（如需要）
    5. LLM 流式生成分析文字

    输入:
        - tables: 表集合
        - query: 用户查询
        - context: 上下文（含 analysis_scenario 字段可选）

    输出:
        {
            "content": "分析报告文字",
            "profile": {...},      # 数据画像
            "quality_report": {...}, # 质量报告
            "analysis_type": str    # 场景类型
        }
    """

    stage = ProcessStage.ANALYZE

    def __init__(self, llm_client: "LLMClient", context_builder: Optional["ContextBuilder"] = None):
        self.llm_client = llm_client
        self.context_builder = context_builder

    def run(
        self,
        tables: "FileCollection",
        query: str,
        config: ProcessConfig,
        context: dict,
    ) -> Generator[ProcessEvent, None, dict]:
        """
        执行数据分析流程
        """
        # 创建唯一阶段 ID
        stage_id = self._generate_stage_id()

        yield self._create_event(ProcessStage.ANALYZE, EventType.STAGE_START, stage_id=stage_id)

        try:
            # 1. 检测分析场景
            scenario = self._detect_scenario(query, context)

            # 2. 提取数据画像
            from app.engine.data_profiler import DataProfiler

            profiler = DataProfiler()
            multi_profile = profiler.profile_tables(tables, for_llm=True)
            profile_text = profiler.format_multi_profile_for_llm(multi_profile)

            # 3. 数据质量检测
            from app.engine.quality_checker import QualityChecker

            quality_checker = QualityChecker()
            quality_reports = []

            for table_name in [p.table_name for p in multi_profile.profiles.values()]:
                # 找到对应的 table
                for file_id in tables.get_file_ids():
                    excel_file = tables.get_file(file_id)
                    if excel_file.has_sheet(table_name):
                        table = excel_file.get_sheet(table_name)
                        report = quality_checker.check_quality(table)
                        quality_reports.append(report)
                        break

            quality_text = "\n\n".join([
                quality_checker.format_report_for_llm(report)
                for report in quality_reports
            ])

            # 4. 场景特定处理
            extra_context = {}
            if scenario.startswith("l2_"):
                # L2 场景：尝试识别维度和进行聚合
                extra_context = self._handle_l2_scenario(query, tables, multi_profile, scenario)
            elif scenario.startswith("l3_"):
                # L3 场景：进行专项分析
                extra_context = self._handle_l3_scenario(query, tables, multi_profile, scenario)
            elif scenario.startswith("l4_"):
                # L4 场景：智能推断（归因分析 + 关系发现）
                extra_context = self._handle_l4_scenario(query, tables, multi_profile, scenario)

            # 5. 构建分析提示词
            analysis_prompt = self._build_analysis_prompt(
                query, profile_text, quality_text, scenario, extra_context
            )

            # 6. 流式 LLM 生成
            full_content = ""

            if config.stream_llm:
                for delta, content in self.llm_client.analyze_stream(analysis_prompt):
                    if delta:
                        full_content += delta
                    yield self._create_event(
                        ProcessStage.ANALYZE,
                        EventType.STAGE_STREAM,
                        stage_id=stage_id,
                        delta=delta or ""
                    )

                if not full_content.strip():
                    # fallback to non-stream
                    full_content = self.llm_client.analyze(analysis_prompt)
            else:
                full_content = self.llm_client.analyze(analysis_prompt)

            # 构建输出
            output = {
                "content": full_content,
                "profile": {k: asdict(v) for k, v in multi_profile.profiles.items()},
                "quality_report": [
                    asdict(r) for r in quality_reports
                ],
                "relationships": [asdict(r) for r in multi_profile.relationships],
                "analysis_type": scenario
            }

            yield self._create_event(
                ProcessStage.ANALYZE,
                EventType.STAGE_DONE,
                stage_id=stage_id,
                output=output
            )

            return output

        except StageError:
            raise
        except Exception as e:
            error_msg = f"分析阶段失败: {e}"
            logger.exception(error_msg)
            yield self._create_event(
                ProcessStage.ANALYZE,
                EventType.STAGE_ERROR,
                stage_id=stage_id,
                error=error_msg
            )
            raise StageError(error_msg) from e

    def _detect_scenario(self, query: str, context: dict) -> str:
        """
        检测分析场景

        优先级：
        1. 如果上下文中指定了 scenario，使用它
        2. 否则从查询中检测
        """
        # 优先使用上下文中指定的场景
        if context.get("analysis_scenario"):
            return context["analysis_scenario"]

        # 从 prompt.py 导入场景检测函数
        from app.engine.prompt import detect_analysis_scenario
        return detect_analysis_scenario(query)

    def _handle_l2_scenario(
        self,
        query: str,
        tables: "FileCollection",
        multi_profile,
        scenario: str
    ) -> dict:
        """
        L2 场景特定处理

        Args:
            query: 用户查询
            tables: 表集合
            multi_profile: 多表画像
            scenario: 场景类型

        Returns:
            额外上下文（用于提示词构建）
        """
        extra_context = {}

        # 检测是否有维度相关的查询
        if scenario == "l2_dimension":
            # 尝试识别用户指定的维度
            dimension_info = self._extract_dimension_info(query, multi_profile)
            if dimension_info:
                extra_context["dimension_info"] = dimension_info

                # 如果识别到维度，进行聚合
                aggregated_text = self._aggregate_by_dimension(
                    tables, multi_profile, dimension_info
                )
                extra_context["aggregated_text"] = aggregated_text

        # 多表联合分析
        if scenario == "l2_multi_table" and multi_profile.relationships:
            from app.engine.relationship_detector import RelationshipDetector
            detector = RelationshipDetector()
            rel_text = detector.format_relationships_for_llm(multi_profile.relationships)
            extra_context["relationships_text"] = rel_text

        return extra_context

    def _extract_dimension_info(self, query: str, multi_profile) -> Optional[dict]:
        """
        从查询中提取维度信息

        Args:
            query: 用户查询
            multi_profile: 多表画像

        Returns:
            维度信息字典 {dimension_col: ..., metric_cols: [...]}
        """
        query_lower = query.lower()

        # 常见的维度词
        dimension_keywords = ["地区", "区域", "城市", "省份", "产品", "客户", "用户", "日期", "月份", "年份", "类别", "分类"]

        dimension_col = None
        for col_name, profile in multi_profile.profiles.items():
            for col in profile.columns:
                col_lower = col.name.lower()
                # 检查列名是否包含维度关键词
                for kw in dimension_keywords:
                    if kw in col.name:
                        dimension_col = col.name
                        break
                if dimension_col:
                    break
            if dimension_col:
                break

        if not dimension_col:
            return None

        # 常见的指标词
        metric_keywords = ["销售", "金额", "数量", "利润", "成本", "价格"]

        metric_cols = []
        for col_name, profile in multi_profile.profiles.items():
            for col in profile.columns:
                if col.type == "number":
                    for kw in metric_keywords:
                        if kw in col.name:
                            metric_cols.append(col.name)
                            break

        if not metric_cols:
            # 默认使用所有数值列
            for col_name, profile in multi_profile.profiles.items():
                for col in profile.columns:
                    if col.type == "number":
                        metric_cols.append(col.name)

        return {
            "dimension": dimension_col,
            "metrics": metric_cols[:5]  # 最多5个指标
        }

    def _aggregate_by_dimension(
        self,
        tables: "FileCollection",
        multi_profile,
        dimension_info: dict
    ) -> str:
        """
        按维度聚合数据

        Args:
            tables: 表集合
            multi_profile: 多表画像
            dimension_info: 维度信息

        Returns:
            聚合结果的文本描述
        """
        import pandas as pd

        dimension_col = dimension_info["dimension"]
        metric_cols = dimension_info["metrics"]

        lines = [f"## 按 [{dimension_col}] 分组统计\n"]

        # 找到包含维度的表
        target_table = None
        target_profile = None

        for table_name, profile in multi_profile.profiles.items():
            for col in profile.columns:
                if col.name == dimension_col:
                    target_table = table_name
                    target_profile = profile
                    break
            if target_table:
                break

        if not target_table:
            return "未找到指定的维度列"

        # 获取表数据
        table_key = target_table
        file_id, sheet_name = table_key.split(".", 1) if "." in table_key else (None, table_key)

        if file_id:
            excel_file = tables.get_file(file_id)
            if excel_file.has_sheet(sheet_name):
                table = excel_file.get_sheet(sheet_name)
                df = table.get_data()

                if dimension_col in df.columns:
                    # 进行分组聚合
                    agg_dict = {}
                    for metric in metric_cols:
                        if metric in df.columns:
                            agg_dict[metric] = ["sum", "mean", "count"]

                    try:
                        grouped = df.groupby(dimension_col)[metric_cols].agg({
                            m: ["sum", "mean", "count"] for m in metric_cols if m in df.columns
                        })

                        lines.append(f"\n### 分组统计结果\n")
                        lines.append(grouped.to_string())
                    except Exception as e:
                        lines.append(f"\n聚合计算失败: {e}")

        return "\n".join(lines)

    def _handle_l3_scenario(
        self,
        query: str,
        tables: "FileCollection",
        multi_profile,
        scenario: str
    ) -> dict:
        """
        L3 场景特定处理（专项分析）

        Args:
            query: 用户查询
            tables: 表集合
            multi_profile: 多表画像
            scenario: 场景类型

        Returns:
            额外上下文（用于提示词构建）
        """
        from app.engine.analysis_functions import (
            correlation_analysis, format_correlation_for_llm,
            group_comparison, format_comparison_for_llm,
            trend_analysis, format_trend_for_llm,
            distribution_stats, format_distribution_for_llm,
        )

        import pandas as pd

        extra_context = {}
        result_table = None

        # 找到第一个有数据的表
        for file_id in tables.get_file_ids():
            excel_file = tables.get_file(file_id)
            for sheet_name in excel_file.get_sheet_names():
                table = excel_file.get_sheet(sheet_name)
                df = table.get_data()
                if len(df) > 0:
                    result_table = table
                    table_key = f"{file_id}.{sheet_name}"
                    break
            if result_table:
                break

        if result_table is None:
            return extra_context

        df = result_table.get_data()

        # 相关性分析
        if scenario == "l3_correlation":
            # 从查询中提取列名
            col_a, col_b = self._extract_correlation_columns(query, df)
            if col_a and col_b and col_a in df.columns and col_b in df.columns:
                result = correlation_analysis(df, col_a, col_b)
                extra_context["correlation_text"] = format_correlation_for_llm(result)

        # 对比分析
        elif scenario == "l3_comparison":
            dim_info = self._extract_dimension_info(query, multi_profile)
            if dim_info:
                dimension_col = dim_info["dimension"]
                metric_cols = dim_info["metrics"]
                if dimension_col in df.columns:
                    result = group_comparison(df, dimension_col, metric_cols)
                    extra_context["comparison_text"] = format_comparison_for_llm(result)

        # 趋势分析
        elif scenario == "l3_trend":
            date_cols = [c.name for c in multi_profile.profiles[table_key].columns
                        if c.type == "date"]
            numeric_cols = dim_info["metrics"] if dim_info else []
            if not numeric_cols:
                numeric_cols = [c.name for c in multi_profile.profiles[table_key].columns
                              if c.type == "number"]

            if date_cols and numeric_cols:
                result = trend_analysis(df, date_cols[0], numeric_cols[0])
                extra_context["trend_text"] = format_trend_for_llm(result)

        # 分布分析
        elif scenario == "l3_distribution":
            # 找到被分析的列
            target_col = None
            for col in df.columns:
                if any(kw in col.lower() for kw in ["销售", "金额", "价格", "数量", "利润"]):
                    target_col = col
                    break
            if not target_col:
                # 使用第一个数值列
                for col in df.columns:
                    if pd.api.types.is_numeric_dtype(df[col]):
                        target_col = col
                        break

            if target_col:
                result = distribution_stats(df, target_col)
                extra_context["distribution_text"] = format_distribution_for_llm(result)

        return extra_context

    def _extract_correlation_columns(self, query: str, df: pd.DataFrame) -> Tuple[Optional[str], Optional[str]]:
        """从查询中提取相关性分析的两列"""
        # 常见的列名模式
        col_pairs = []
        for col_a in df.columns:
            for col_b in df.columns:
                if col_a != col_b:
                    col_pairs.append((col_a, col_b))

        # 尝试从查询中匹配列名
        query_lower = query.lower()
        for col_a, col_b in col_pairs:
            if (col_a.lower() in query_lower or col_a.lower().replace(" ", "") in query_lower.replace(" ", "")) and \
               (col_b.lower() in query_lower or col_b.lower().replace(" ", "") in query_lower.replace(" ", "")):
                return col_a, col_b

        # 默认返回第一对数值列
        numeric_cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
        if len(numeric_cols) >= 2:
            return numeric_cols[0], numeric_cols[1]

        return None, None

    def _handle_l4_scenario(
        self,
        query: str,
        tables: "FileCollection",
        multi_profile,
        scenario: str
    ) -> dict:
        """
        L4 场景特定处理（智能推断）

        包含：
        - 归因分析：多维度下钻，找出关键因素
        - 关系发现：全列相关性扫描

        Args:
            query: 用户查询
            tables: 表集合
            multi_profile: 多表画像
            scenario: 场景类型

        Returns:
            额外上下文（用于提示词构建）
        """
        from app.engine.analysis_functions import (
            correlation_analysis, format_correlation_for_llm,
            group_comparison, format_comparison_for_llm,
            distribution_stats, format_distribution_for_llm,
            get_numeric_columns,
        )

        extra_context = {}

        # 找到第一个有数据的表
        result_table = None
        table_key = None
        for file_id in tables.get_file_ids():
            excel_file = tables.get_file(file_id)
            for sheet_name in excel_file.get_sheet_names():
                table = excel_file.get_sheet(sheet_name)
                df = table.get_data()
                if len(df) > 0:
                    result_table = table
                    table_key = f"{file_id}.{sheet_name}"
                    break
            if result_table:
                break

        if result_table is None:
            return extra_context

        df = result_table.get_data()

        # L4 归因分析：为什么 X 最大/最高
        if scenario == "l4_causation":
            drilldown_text = self._perform_drilldown_analysis(
                query, df, multi_profile, table_key
            )
            extra_context["drilldown_text"] = drilldown_text

        # L4 关系发现：全列相关性扫描
        if scenario == "l4_relation_discovery":
            correlation_scan_text = self._perform_correlation_scan(df)
            extra_context["correlation_scan_text"] = correlation_scan_text

        return extra_context

    def _perform_drilldown_analysis(
        self,
        query: str,
        df: pd.DataFrame,
        multi_profile,
        table_key: str
    ) -> str:
        """
        执行多维度下钻分析

        目标：解释为什么某个维度值表现突出
        """
        lines = ["## 多维度下钻分析\n"]

        # 从查询中识别目标值
        target_value = None
        dimension_col = None

        # 常见的维度词
        dimension_keywords = ["地区", "区域", "产品", "客户", "类别", "省份", "城市"]

        for col in df.columns:
            if any(kw in col for kw in dimension_keywords):
                # 检查查询中是否提到了这个维度的某个值
                for val in df[col].dropna().unique()[:10]:
                    if str(val) in query or str(val) in query.lower():
                        dimension_col = col
                        target_value = val
                        break
                if target_value:
                    break

        if not dimension_col or not target_value:
            return "未能识别下钻维度"

        # 获取数值列
        numeric_cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]

        if not numeric_cols:
            return "无数值列可分析"

        # 分析目标组的特征
        target_data = df[df[dimension_col] == target_value]
        other_data = df[df[dimension_col] != target_value]

        lines.append(f"\n### [{target_value}] vs 其他组 对比\n")

        for col in numeric_cols[:5]:  # 最多分析5个指标
            target_mean = target_data[col].mean()
            other_mean = other_data[col].mean()
            other_count = len(other_data)

            if pd.isna(target_mean) or pd.isna(other_mean):
                continue

            diff = target_mean - other_mean
            diff_pct = (diff / other_mean * 100) if other_mean != 0 else 0

            lines.append(f"\n**{col}**：")
            lines.append(f"- {target_value}均值: {target_mean:.2f}")
            lines.append(f"- 其他组均值: {other_mean:.2f}")
            lines.append(f"- 差异: {diff:+.2f} ({diff_pct:+.1f}%)")

        # 找出最突出的差异
        max_diff_col = None
        max_diff_pct = 0
        for col in numeric_cols[:5]:
            if col not in df.columns:
                continue
            t_mean = target_data[col].mean()
            o_mean = other_data[col].mean()
            if pd.isna(t_mean) or pd.isna(o_mean) or o_mean == 0:
                continue
            diff_pct = abs(t_mean - o_mean) / o_mean * 100
            if diff_pct > max_diff_pct:
                max_diff_pct = diff_pct
                max_diff_col = col

        if max_diff_col:
            lines.append(f"\n### 关键发现\n")
            lines.append(f"**{max_diff_col}** 是区分 **{target_value}** 与其他组的最关键指标")

        return "\n".join(lines)

    def _perform_correlation_scan(self, df: pd.DataFrame) -> str:
        """
        执行全列相关性扫描

        发现所有数值列之间的相关性
        """
        lines = ["## 全列相关性扫描结果\n"]

        numeric_cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]

        if len(numeric_cols) < 2:
            return "数值列不足，无法进行相关性扫描"

        # 计算相关性矩阵
        corr_matrix = df[numeric_cols].corr()

        # 找出强相关对（|r| > 0.7）
        strong_correlations = []
        for i, col_a in enumerate(numeric_cols):
            for col_b in numeric_cols[i+1:]:
                r = corr_matrix.loc[col_a, col_b]
                if abs(r) > 0.7:
                    strong_correlations.append((col_a, col_b, r))

        if strong_correlations:
            lines.append("\n### 强相关列对（|r| > 0.7）：\n")
            for col_a, col_b, r in sorted(strong_correlations, key=lambda x: abs(x[2]), reverse=True):
                direction = "正相关" if r > 0 else "负相关"
                lines.append(f"- **{col_a}** ↔ **{col_b}**：r={r:.3f}（{direction}）")
        else:
            lines.append("\n未发现强相关列对（|r| > 0.7）")

        # 列出中等相关（0.4 < |r| < 0.7）
        medium_correlations = []
        for i, col_a in enumerate(numeric_cols):
            for col_b in numeric_cols[i+1:]:
                r = corr_matrix.loc[col_a, col_b]
                if 0.4 < abs(r) <= 0.7:
                    medium_correlations.append((col_a, col_b, r))

        if medium_correlations:
            lines.append("\n### 中等相关列对（0.4 < |r| ≤ 0.7）：\n")
            for col_a, col_b, r in sorted(medium_correlations, key=lambda x: abs(x[2]), reverse=True)[:10]:
                direction = "正相关" if r > 0 else "负相关"
                lines.append(f"- **{col_a}** ↔ **{col_b}**：r={r:.3f}（{direction}）")

        return "\n".join(lines)

    def _build_analysis_prompt(
        self,
        query: str,
        profile_text: str,
        quality_text: str,
        scenario: str,
        extra_context: dict
    ) -> str:
        """
        构建分析提示词

        Args:
            query: 用户问题
            profile_text: 数据画像文本
            quality_text: 质量报告文本
            scenario: 分析场景
            extra_context: 额外上下文
        """
        from app.engine.prompt import get_analysis_prompt

        return get_analysis_prompt(
            scenario=scenario,
            query=query,
            profile_text=profile_text,
            quality_text=quality_text,
            relationships_text=extra_context.get("relationships_text", ""),
            aggregated_text=extra_context.get("aggregated_text", ""),
            correlation_text=extra_context.get("correlation_text", ""),
            comparison_text=extra_context.get("comparison_text", ""),
            trend_text=extra_context.get("trend_text", ""),
            distribution_text=extra_context.get("distribution_text", ""),
            drilldown_text=extra_context.get("drilldown_text", ""),
            correlation_scan_text=extra_context.get("correlation_scan_text", ""),
        )

    def _generate_stage_id(self) -> str:
        """生成阶段 ID"""
        import uuid
        return str(uuid.uuid4())[:8]

    def _create_event(
        self,
        stage: ProcessStage,
        event_type: EventType,
        stage_id: str = None,
        output: Any = None,
        delta: str = None,
        error: str = None,
    ) -> ProcessEvent:
        """创建事件"""
        return ProcessEvent(
            stage=stage,
            event_type=event_type,
            stage_id=stage_id,
            output=output,
            delta=delta,
            error=error
        )
