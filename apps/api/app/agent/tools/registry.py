"""工具注册表"""

from typing import Any, Optional

from app.agent.tools.base import ExcelBaseTool
from app.agent.tools.hello import HelloTool
from app.agent.tools.clarify import ClarifyTool
from app.agent.tools.read_excel import ReadExcelTool
from app.agent.tools.filter import FilterTool
from app.agent.tools.sort import SortTool
from app.agent.tools.add_column import AddColumnTool
from app.agent.tools.update_column import UpdateColumnTool
from app.agent.tools.aggregate import AggregateTool
from app.agent.tools.compute import ComputeTool
from app.agent.tools.pivot import PivotTool
from app.agent.tools.group_by import GroupByTool
from app.agent.tools.take import TakeTool
from app.agent.tools.select_columns import SelectColumnsTool
from app.agent.tools.drop_columns import DropColumnsTool
from app.agent.tools.export_excel import ExportExcelTool
from app.agent.tools.get_schema import GetSchemaTool
from app.agent.tools.generate_formulas import GenerateFormulasTool


class ExcelToolRegistry:
    """Excel Agent 工具注册表"""

    def __init__(self):
        self._tools: list[ExcelBaseTool] = [
            HelloTool(),
            ClarifyTool(),
            ReadExcelTool(),
            FilterTool(),
            SortTool(),
            AddColumnTool(),
            UpdateColumnTool(),
            AggregateTool(),
            ComputeTool(),
            PivotTool(),
            GroupByTool(),
            TakeTool(),
            SelectColumnsTool(),
            DropColumnsTool(),
            ExportExcelTool(),
            GetSchemaTool(),
            GenerateFormulasTool(),
        ]

    def set_context(
        self,
        user_id: str = "",
        db: Any = None,
        file_collection: Any = None,
    ) -> None:
        """注入请求级上下文到工具"""
        for tool in self._tools:
            tool._context_user_id = user_id
            tool._context_db = db
            tool._context_file_collection = file_collection

    def get_tools(self) -> list[ExcelBaseTool]:
        return self._tools

    def get_tool(self, name: str) -> Optional[ExcelBaseTool]:
        for tool in self._tools:
            if tool.name == name:
                return tool
        return None

    def add_tool(self, tool: ExcelBaseTool) -> None:
        """Phase 2 追加工具时调用"""
        self._tools.append(tool)
