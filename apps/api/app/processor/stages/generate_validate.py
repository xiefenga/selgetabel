"""生成+验证复合阶段"""

import json
import logging
from typing import Any, Dict, Generator, List, TYPE_CHECKING

from ..types import ProcessStage, EventType, ProcessEvent, ProcessConfig
from .base import Stage
from .analyze import StageError

if TYPE_CHECKING:
    from app.engine.models import FileCollection
    from app.engine.llm_client import LLMClient

logger = logging.getLogger(__name__)


class GenerateValidateStage(Stage):
    """
    生成+验证复合阶段

    内部封装了 generate + validate 的重试循环，但仍然 yield 两种阶段的事件，
    使得前端可以区分生成和验证的状态。

    流程：
    1. 调用 LLM 生成操作 JSON (yield generate 事件)
    2. 解析验证操作 (yield validate 事件)
    3. 如果验证失败且未超过重试次数，带错误信息重新生成

    输入:
        - tables: 表集合
        - query: 用户查询
        - context["analyze"]: 分析结果（可选）

    输出:
        {
            "operations": {...},       # 解析后的操作字典
            "operations_json": "...",  # 原始 JSON 字符串
            "parsed_operations": [...], # 解析后的 Operation 对象列表
            "validation_errors": [...], # 验证错误（如果有）
        }
    """

    # 主阶段标识（用于 context key）
    stage = ProcessStage.GENERATE

    def __init__(self, llm_client: "LLMClient"):
        self.llm_client = llm_client

    def run(
        self,
        tables: "FileCollection",
        query: str,
        config: ProcessConfig,
        context: dict,
    ) -> Generator[ProcessEvent, None, Any]:
        """执行生成+验证流程"""

        # 使用增强的 schema（包含类型和样本数据）
        schemas = tables.get_schemas_with_samples(sample_count=3)
        analysis = context.get("analyze", {}).get("content", "")
        file_sheets = self._build_file_sheets(tables)

        retry_count = 0
        max_retries = config.max_validation_retries

        # 用于重试时传递错误信息
        previous_errors: List[str] = None
        previous_json: str = None

        # 最终输出
        operations_dict = {}
        operations_json = ""
        parsed_operations = []
        validation_errors = []

        while True:
            # ========== 1. 生成阶段 ==========
            try:
                operations_json, operations_dict = yield from self._run_generate(
                    query, analysis, schemas, config,
                    previous_errors=previous_errors,
                    previous_json=previous_json,
                )
            except StageError:
                raise
            except Exception as e:
                # 防御性编程：捕获未预期的异常
                error_msg = f"生成操作失败: {e}"
                yield self._create_event(
                    ProcessStage.GENERATE, EventType.STAGE_ERROR,
                    stage_id=self._generate_stage_id(), error=error_msg
                )
                raise StageError(error_msg) from e

            # ========== 2. 验证阶段 ==========
            try:
                parsed_operations, validation_errors = yield from self._run_validate(
                    operations_json, file_sheets
                )
            except StageError:
                raise
            except Exception as e:
                # 防御性编程：捕获未预期的异常
                error_msg = f"验证失败: {e}"
                yield self._create_event(
                    ProcessStage.VALIDATE, EventType.STAGE_ERROR,
                    stage_id=self._generate_stage_id(), error=error_msg
                )
                raise StageError(error_msg) from e

            # ========== 3. 检查是否需要重试 ==========
            if not validation_errors:
                # 验证通过，跳出循环
                break

            retry_count += 1

            if retry_count > max_retries:
                # 超过最大重试次数
                logger.warning(
                    f"验证失败，已达到最大重试次数 ({max_retries})，继续执行"
                )
                break

            # 准备重试
            logger.info(
                f"验证失败，准备重试 ({retry_count}/{max_retries})，"
                f"错误: {validation_errors}"
            )
            previous_errors = validation_errors
            previous_json = operations_json

        # 返回最终输出
        output = {
            "operations": operations_dict,
            "operations_json": operations_json,
            "parsed_operations": parsed_operations,
            "validation_errors": validation_errors,
        }
        return output

    def _run_generate(
        self,
        query: str,
        analysis: str,
        schemas: dict,
        config: ProcessConfig,
        previous_errors: List[str] = None,
        previous_json: str = None,
    ) -> Generator[ProcessEvent, None, tuple]:
        """
        运行生成子阶段

        Returns:
            (operations_json, operations_dict)
        """
        # 为此次生成子阶段生成唯一 ID
        stage_id = self._generate_stage_id()

        yield self._create_event(ProcessStage.GENERATE, EventType.STAGE_START, stage_id=stage_id)

        try:
            if config.stream_llm:
                # 流式调用
                operations_json = ""
                for delta, full_content in self.llm_client.generate_operations_stream(
                    query, analysis, schemas,
                    previous_errors=previous_errors,
                    previous_json=previous_json,
                ):
                    operations_json = full_content
                    yield self._create_event(
                        ProcessStage.GENERATE, EventType.STAGE_STREAM,
                        stage_id=stage_id, delta=delta
                    )
                operations_json = self._clean_json_response(operations_json)
            else:
                # 非流式调用
                operations_json = self.llm_client.generate_operations(
                    query, analysis, schemas,
                    previous_errors=previous_errors,
                    previous_json=previous_json,
                )

            # 解析 JSON
            try:
                operations_dict = json.loads(operations_json)
            except json.JSONDecodeError as e:
                raise StageError(f"JSON 解析失败: {e}") from e

            yield self._create_event(
                ProcessStage.GENERATE, EventType.STAGE_DONE,
                stage_id=stage_id, output={"operations": operations_dict}
            )

            return operations_json, operations_dict

        except StageError:
            raise
        except Exception as e:
            error_msg = f"生成操作失败: {e}"
            yield self._create_event(
                ProcessStage.GENERATE, EventType.STAGE_ERROR,
                stage_id=stage_id, error=error_msg
            )
            raise StageError(error_msg) from e

    def _run_validate(
        self,
        operations_json: str,
        file_sheets: Dict[str, List[str]],
    ) -> Generator[ProcessEvent, None, tuple]:
        """
        运行验证子阶段

        Returns:
            (parsed_operations, errors)
        """
        # 为此次验证子阶段生成唯一 ID
        stage_id = self._generate_stage_id()

        yield self._create_event(ProcessStage.VALIDATE, EventType.STAGE_START, stage_id=stage_id)

        try:
            from app.engine.parser import parse_and_validate

            parsed_operations, errors = parse_and_validate(operations_json, file_sheets)

            yield self._create_event(
                ProcessStage.VALIDATE, EventType.STAGE_DONE,
                stage_id=stage_id,
                output={
                    "valid": len(errors) == 0,
                    "operation_count": len(parsed_operations),
                    "errors": errors if errors else None,
                }
            )

            return parsed_operations, errors

        except Exception as e:
            error_msg = f"验证失败: {e}"
            logger.exception(error_msg)
            yield self._create_event(
                ProcessStage.VALIDATE, EventType.STAGE_ERROR,
                stage_id=stage_id, error=error_msg
            )
            raise StageError(error_msg) from e

    def _create_event(
        self,
        stage: ProcessStage,
        event_type: EventType,
        stage_id: str = None,
        output: Any = None,
        delta: str = None,
        error: str = None,
    ) -> ProcessEvent:
        """创建指定阶段的事件"""
        return ProcessEvent(
            stage=stage,
            event_type=event_type,
            stage_id=stage_id,
            output=output,
            delta=delta,
            error=error,
        )

    def _build_file_sheets(self, tables: "FileCollection") -> Dict[str, List[str]]:
        """构建 file_id -> sheet_names 映射"""
        file_sheets = {}
        for file_id in tables.get_file_ids():
            excel_file = tables.get_file(file_id)
            file_sheets[file_id] = excel_file.get_sheet_names()
        return file_sheets

    def _clean_json_response(self, content: str) -> str:
        """清理 LLM 响应中可能存在的 markdown 标记"""
        content = content.strip()

        if content.startswith("```json"):
            content = content[7:]
        elif content.startswith("```"):
            content = content[3:]

        if content.endswith("```"):
            content = content[:-3]

        return content.strip()
