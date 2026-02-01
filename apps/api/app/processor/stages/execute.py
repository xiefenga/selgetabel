"""执行操作阶段"""

import logging
from typing import Any, Dict, Generator, List, TYPE_CHECKING

from ..types import ProcessStage, ProcessEvent, ProcessConfig
from .base import Stage
from .analyze import StageError

if TYPE_CHECKING:
    from app.engine.models import FileCollection

logger = logging.getLogger(__name__)


class ExecuteStage(Stage):
    """
    执行操作阶段

    执行已验证的操作，生成 Excel 公式。

    输入:
        - tables: 表集合
        - context["generate"]: GenerateValidateStage 的输出（包含已解析的操作）

    输出:
        {
            "formulas": "公式字符串",
            "variables": {...},
            "new_columns": {...},
            "updated_columns": {...},
            "errors": [...],
            "raw_new_columns": {...},  # 内部使用，完整数据
            "raw_updated_columns": {...},  # 内部使用，完整数据
        }
    """

    stage = ProcessStage.EXECUTE

    def run(
        self,
        tables: "FileCollection",
        query: str,
        config: ProcessConfig,
        context: dict,
    ) -> Generator[ProcessEvent, None, Any]:
        """执行操作"""
        # 生成此阶段的唯一 ID
        stage_id = self._generate_stage_id()

        yield self._event_start(stage_id)

        # 从 GenerateValidateStage 获取已解析的操作
        generate_output = context.get("generate", {})
        operations = generate_output.get("parsed_operations", [])
        validation_errors = generate_output.get("validation_errors", [])

        errors: List[str] = list(validation_errors)  # 继承验证阶段的错误
        variables: Dict[str, Any] = {}
        new_columns: Dict[str, Dict[str, Dict[str, List]]] = {}
        updated_columns: Dict[str, Dict[str, Dict[str, List]]] = {}
        new_sheets: Dict[str, Dict[str, Dict]] = {}  # 新创建的 Sheet 预览
        raw_new_columns: Dict = {}
        raw_updated_columns: Dict = {}
        raw_new_sheets: Dict = {}  # 新创建的 Sheet 完整数据
        formulas = None

        try:
            # 执行操作（仅当验证通过时）
            if operations and not validation_errors:
                from app.engine.executor import execute_operations

                exec_result = execute_operations(operations, tables)

                # 处理变量
                variables = self._make_serializable(exec_result.variables)

                # 处理新列（预览前 10 行）
                raw_new_columns = exec_result.new_columns
                for file_id, sheets in exec_result.new_columns.items():
                    if file_id not in new_columns:
                        new_columns[file_id] = {}
                    for sheet_name, cols in sheets.items():
                        new_columns[file_id][sheet_name] = {
                            col: self._make_serializable(values[:10])
                            for col, values in cols.items()
                        }

                # 处理更新列（预览前 10 行）
                raw_updated_columns = exec_result.updated_columns
                for file_id, sheets in exec_result.updated_columns.items():
                    if file_id not in updated_columns:
                        updated_columns[file_id] = {}
                    for sheet_name, cols in sheets.items():
                        updated_columns[file_id][sheet_name] = {
                            col: self._make_serializable(values[:10])
                            for col, values in cols.items()
                        }

                # 处理新创建的 Sheet（预览信息）
                raw_new_sheets = exec_result.new_sheets
                for file_id, sheets in exec_result.new_sheets.items():
                    if file_id not in new_sheets:
                        new_sheets[file_id] = {}
                    for sheet_name, df in sheets.items():
                        # 存储 Sheet 的预览信息
                        new_sheets[file_id][sheet_name] = {
                            "row_count": len(df),
                            "columns": list(df.columns),
                            "preview": self._make_serializable(
                                df.head(10).to_dict(orient="records")
                            ) if len(df) > 0 else []
                        }

                errors.extend(exec_result.errors)

            # 3. 生成公式
            if operations:
                try:
                    from app.engine.excel_generator import (
                        generate_formulas,
                        format_formula_output,
                    )

                    excel_formulas = generate_formulas(operations, tables)
                    formulas = format_formula_output(excel_formulas)
                except Exception as e:
                    logger.warning(f"生成公式失败: {e}")

            output = {
                "formulas": formulas,
                "variables": variables if variables else None,
                "new_columns": new_columns if new_columns else None,
                "updated_columns": updated_columns if updated_columns else None,
                "new_sheets": new_sheets if new_sheets else None,
                "errors": errors if errors else None,
                "raw_new_columns": raw_new_columns,  # 内部使用
                "raw_updated_columns": raw_updated_columns,  # 内部使用
                "raw_new_sheets": raw_new_sheets,  # 内部使用
            }

            yield self._event_done(
                {
                    "formulas": formulas,
                    "errors": errors if errors else None,
                },
                stage_id,
            )
            return output

        except Exception as e:
            error_msg = f"执行失败: {e}"
            logger.exception(error_msg)
            yield self._event_error(error_msg, stage_id)
            raise StageError(error_msg) from e

    def _make_serializable(self, obj: Any) -> Any:
        """将对象转换为可序列化格式"""
        import math
        from datetime import datetime, date
        from app.engine.models import ExcelError

        if isinstance(obj, ExcelError):
            return str(obj)
        elif isinstance(obj, (datetime, date)):
            return obj.isoformat()
        elif hasattr(obj, 'isoformat'):  # pandas Timestamp 等
            return obj.isoformat()
        elif isinstance(obj, float) and math.isnan(obj):
            return None
        elif isinstance(obj, dict):
            return {k: self._make_serializable(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._make_serializable(item) for item in obj]
        elif isinstance(obj, tuple):
            return tuple(self._make_serializable(item) for item in obj)
        else:
            return obj
