"""验证操作阶段"""

import logging
from typing import Any, Dict, Generator, List, TYPE_CHECKING

from ..types import ProcessStage, ProcessEvent, ProcessConfig
from .base import Stage
from .analyze import StageError

if TYPE_CHECKING:
    from app.engine.models import FileCollection

logger = logging.getLogger(__name__)


class ValidateStage(Stage):
    """
    验证操作阶段

    解析并验证 LLM 生成的操作 JSON，确保：
    1. JSON 格式正确
    2. 操作类型有效
    3. file_id 和 sheet_name 存在
    4. 列名存在
    5. 函数在白名单中

    输入:
        - tables: 表集合
        - context["generate"]: 生成的操作

    输出:
        {
            "operations": List[Operation],  # 解析后的操作对象
            "errors": List[str],  # 验证错误列表
        }
    """

    stage = ProcessStage.VALIDATE

    def run(
        self,
        tables: "FileCollection",
        query: str,
        config: ProcessConfig,
        context: dict,
    ) -> Generator[ProcessEvent, None, Any]:
        """验证操作"""
        # 生成此阶段的唯一 ID
        stage_id = self._generate_stage_id()

        yield self._event_start(stage_id)

        generate_output = context.get("generate", {})
        operations_json = generate_output.get("operations_json", "")

        errors: List[str] = []
        operations: List = []

        try:
            # 解析和验证操作
            from app.engine.parser import parse_and_validate

            file_sheets = self._build_file_sheets(tables)
            operations, parse_errors = parse_and_validate(operations_json, file_sheets)
            errors.extend(parse_errors)

            output = {
                "operations": operations,
                "errors": errors,
            }

            yield self._event_done(
                {
                    "valid": len(errors) == 0,
                    "operation_count": len(operations),
                    "errors": errors if errors else None,
                },
                stage_id,
            )
            return output

        except Exception as e:
            error_msg = f"验证失败: {e}"
            logger.exception(error_msg)
            yield self._event_error(error_msg, stage_id)
            raise StageError(error_msg) from e

    def _build_file_sheets(self, tables: "FileCollection") -> Dict[str, List[str]]:
        """构建 file_id -> sheet_names 映射"""
        file_sheets = {}
        for file_id in tables.get_file_ids():
            excel_file = tables.get_file(file_id)
            file_sheets[file_id] = excel_file.get_sheet_names()
        return file_sheets
