"""Fixture 测试数据服务"""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from app.core.config import settings

logger = logging.getLogger(__name__)

# Fixture 目录路径（相对于项目根目录）
FIXTURES_DIR = Path(settings.PROJECT_ROOT) / "fixtures"


@dataclass
class FixtureCase:
    """测试用例"""

    id: str
    name: str
    prompt: str
    tags: List[str]


@dataclass
class FixtureDataset:
    """数据集信息"""

    file: str
    description: str
    path: Path  # 完整路径


@dataclass
class FixtureScenario:
    """测试场景"""

    id: str
    name: str
    description: str
    group: str
    path: str
    tags: List[str]
    datasets: List[FixtureDataset]
    cases: List[FixtureCase]


@dataclass
class FixtureGroup:
    """测试分组"""

    id: str
    name: str
    description: str
    scenario_ids: List[str]


@dataclass
class FixtureIndex:
    """Fixture 索引"""

    groups: List[FixtureGroup]
    scenarios: List[Dict[str, Any]]  # 简略场景信息


class FixtureService:
    """
    Fixture 测试数据服务

    负责加载和管理 fixtures/ 目录下的测试数据。
    """

    def __init__(self, fixtures_dir: Optional[Path] = None):
        self.fixtures_dir = fixtures_dir or FIXTURES_DIR

    def load_index(self) -> FixtureIndex:
        """
        加载 Fixture 索引

        Returns:
            FixtureIndex: 包含分组和场景列表
        """
        index_path = self.fixtures_dir / "index.yaml"
        if not index_path.exists():
            raise FileNotFoundError(f"Fixture 索引文件不存在: {index_path}")

        with open(index_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        groups = []
        for g in data.get("groups", []):
            groups.append(
                FixtureGroup(
                    id=g["id"],
                    name=g["name"],
                    description=g.get("description", ""),
                    scenario_ids=g.get("scenarios", []),
                )
            )

        scenarios = data.get("scenarios", [])

        return FixtureIndex(groups=groups, scenarios=scenarios)

    def load_scenario(self, scenario_id: str) -> FixtureScenario:
        """
        加载单个场景的完整信息

        Args:
            scenario_id: 场景 ID（如 "01-titanic"）

        Returns:
            FixtureScenario: 场景完整信息，包含数据集和用例
        """
        # 从索引中获取场景基本信息
        index = self.load_index()
        scenario_info = next(
            (s for s in index.scenarios if s["id"] == scenario_id), None
        )
        if not scenario_info:
            raise ValueError(f"场景不存在: {scenario_id}")

        # 加载场景元数据
        scenario_path = self.fixtures_dir / scenario_info["path"]
        meta_path = scenario_path / "meta.yaml"

        if not meta_path.exists():
            raise FileNotFoundError(f"场景元数据不存在: {meta_path}")

        with open(meta_path, "r", encoding="utf-8") as f:
            meta = yaml.safe_load(f)

        # 构建数据集列表
        datasets = []
        datasets_dir = scenario_path / "datasets"
        for ds in meta.get("datasets", []):
            datasets.append(
                FixtureDataset(
                    file=ds["file"],
                    description=ds.get("description", ""),
                    path=datasets_dir / ds["file"],
                )
            )

        # 构建用例列表
        cases = []
        for c in meta.get("cases", []):
            cases.append(
                FixtureCase(
                    id=c["id"],
                    name=c["name"],
                    prompt=c["prompt"].strip(),
                    tags=c.get("tags", []),
                )
            )

        return FixtureScenario(
            id=meta["id"],
            name=meta["name"],
            description=meta.get("description", ""),
            group=scenario_info.get("group", ""),
            path=scenario_info["path"],
            tags=scenario_info.get("tags", []),
            datasets=datasets,
            cases=cases,
        )

    def get_case(self, scenario_id: str, case_id: str) -> tuple[FixtureScenario, FixtureCase]:
        """
        获取特定用例

        Args:
            scenario_id: 场景 ID
            case_id: 用例 ID

        Returns:
            (scenario, case): 场景和用例
        """
        scenario = self.load_scenario(scenario_id)
        case = next((c for c in scenario.cases if c.id == case_id), None)
        if not case:
            raise ValueError(f"用例不存在: {scenario_id}/{case_id}")
        return scenario, case

    def list_all_cases(self) -> List[Dict[str, Any]]:
        """
        列出所有测试用例

        Returns:
            用例列表，每个元素包含 scenario_id, case_id, name 等
        """
        index = self.load_index()
        all_cases = []

        for scenario_info in index.scenarios:
            try:
                scenario = self.load_scenario(scenario_info["id"])
                for case in scenario.cases:
                    all_cases.append(
                        {
                            "scenario_id": scenario.id,
                            "scenario_name": scenario.name,
                            "case_id": case.id,
                            "case_name": case.name,
                            "tags": case.tags,
                            "group": scenario.group,
                        }
                    )
            except Exception as e:
                logger.warning(f"加载场景 {scenario_info['id']} 失败: {e}")

        return all_cases

    def list_cases_by_group(self, group_id: str) -> List[Dict[str, Any]]:
        """
        按分组列出测试用例

        Args:
            group_id: 分组 ID（如 "basic", "advanced", "multi-table"）

        Returns:
            用例列表
        """
        index = self.load_index()
        group = next((g for g in index.groups if g.id == group_id), None)
        if not group:
            raise ValueError(f"分组不存在: {group_id}")

        cases = []
        for scenario_id in group.scenario_ids:
            try:
                scenario = self.load_scenario(scenario_id)
                for case in scenario.cases:
                    cases.append(
                        {
                            "scenario_id": scenario.id,
                            "scenario_name": scenario.name,
                            "case_id": case.id,
                            "case_name": case.name,
                            "tags": case.tags,
                        }
                    )
            except Exception as e:
                logger.warning(f"加载场景 {scenario_id} 失败: {e}")

        return cases


# 全局服务实例
_fixture_service: Optional[FixtureService] = None


def get_fixture_service() -> FixtureService:
    """获取 Fixture 服务实例"""
    global _fixture_service
    if _fixture_service is None:
        _fixture_service = FixtureService()
    return _fixture_service
