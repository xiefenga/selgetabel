"""表关系识别器 - 检测多表之间的关联关系"""

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from app.engine.models import FileCollection
    from app.engine.data_profiler import TableProfile, ColumnProfile

logger = logging.getLogger(__name__)


@dataclass
class Relationship:
    """表关系"""
    from_table: str
    from_column: str
    to_table: str
    to_column: str
    match_ratio: float  # 匹配率 0-1
    relationship_type: str  # "exact", "contains", "inferred"
    confidence: str = "high"  # "high", "medium", "low"


class RelationshipDetector:
    """
    表关系识别器

    策略：
    1. 列名匹配（完全匹配 / 包含匹配）
    2. 样本值验证（匹配率 > 80% 则认为有关联）

    用法：
        detector = RelationshipDetector()
        relationships = detector.detect_from_profiles(profiles)
    """

    # 匹配率阈值
    MATCH_RATIO_THRESHOLD = 0.8
    HIGH_MATCH_RATIO = 0.95

    # 常见关联列名模式
    LINK_COLUMN_PATTERNS = [
        'id', '_id', 'code', 'key', 'no', 'number',
        '客户_id', '订单_id', '产品_id', '用户_id',
        'customer_id', 'order_id', 'product_id', 'user_id',
    ]

    def detect_from_profiles(
        self,
        profiles: Dict[str, "TableProfile"]
    ) -> List[Relationship]:
        """
        从表画像检测关系

        Args:
            profiles: 表名 -> TableProfile 的映射

        Returns:
            识别到的关系列表
        """
        relationships: List[Relationship] = []

        # 构建列信息索引
        column_info: Dict[str, List[Tuple[str, "ColumnProfile"]]] = {}
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

                    rel = self._check_relationship(table_a, profile_a, table_b, profile_b)
                    if rel:
                        relationships.append(rel)

        return relationships

    def _check_relationship(
        self,
        table_a: str,
        profile_a: "ColumnProfile",
        table_b: str,
        profile_b: "ColumnProfile"
    ) -> Optional[Relationship]:
        """检查两个列之间是否存在关系"""
        # 获取列样本值
        samples_a = [v["value"] for v in profile_a.top_values[:10]]
        samples_b = [v["value"] for v in profile_b.top_values[:10]]

        if not samples_a or not samples_b:
            return None

        # 计算匹配率
        set_a, set_b = set(samples_a), set(samples_b)
        intersection = len(set_a & set_b)
        match_ratio = intersection / min(len(set_a), len(set_b))

        if match_ratio < self.MATCH_RATIO_THRESHOLD:
            return None

        # 判断关系类型
        if match_ratio >= self.HIGH_MATCH_RATIO:
            rel_type = "exact"
            confidence = "high"
        else:
            rel_type = "contains"
            confidence = "medium"

        return Relationship(
            from_table=table_a,
            from_column=profile_a.name,
            to_table=table_b,
            to_column=profile_b.name,
            match_ratio=match_ratio,
            relationship_type=rel_type,
            confidence=confidence
        )

    def detect_from_tables(
        self,
        tables: "FileCollection",
        sample_count: int = 20
    ) -> List[Relationship]:
        """
        从表集合检测关系（不依赖 DataProfiler）

        Args:
            tables: FileCollection 对象
            sample_count: 采样数量

        Returns:
            识别到的关系列表
        """
        from app.engine.data_profiler import DataProfiler

        profiler = DataProfiler()
        profiles = {}

        # 提取每个表的画像
        for file_id in tables.get_file_ids():
            excel_file = tables.get_file(file_id)
            for sheet_name in excel_file.get_sheet_names():
                table = excel_file.get_sheet(sheet_name)
                profile = profiler.profile_table(table, for_llm=False)
                key = f"{file_id}.{sheet_name}"
                profiles[key] = profile

        return self.detect_from_profiles(profiles)

    def format_relationships_for_llm(
        self,
        relationships: List[Relationship]
    ) -> str:
        """
        将关系列表格式化为 LLM 可读的文本

        Args:
            relationships: 关系列表

        Returns:
            格式化的文本
        """
        if not relationships:
            return "未检测到表间关联关系"

        lines = ["## 表间关系\n"]

        for rel in relationships:
            emoji = "🔗" if rel.confidence == "high" else "🔗"
            lines.append(
                f"{emoji} **{rel.from_table}**.{rel.from_column} ↔ **{rel.to_table}**.{rel.to_column} "
                f"（匹配率：{rel.match_ratio:.0%}，类型：{rel.relationship_type}）"
            )

        return "\n".join(lines)
