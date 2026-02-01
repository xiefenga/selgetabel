"""Excel 处理器"""

import logging
from typing import Generator, List, Optional, Tuple, TYPE_CHECKING

from .types import (
    ProcessStage,
    EventType,
    ProcessEvent,
    ProcessConfig,
    ProcessResult,
)
from .stages import AnalyzeStage, GenerateValidateStage, ExecuteStage
from .stages.analyze import StageError

if TYPE_CHECKING:
    from app.engine.models import FileCollection
    from app.engine.llm_client import LLMClient

logger = logging.getLogger(__name__)


class ExcelProcessor:
    """
    Excel 处理器 - 核心处理逻辑

    特点：
    1. 纯数据转换：输入 FileCollection + query，输出 ProcessResult
    2. 无外部依赖：不涉及文件存储、数据库、网络
    3. 可观察：通过生成器 yield 处理事件
    4. 可测试：所有输入输出都是普通 Python 对象
    5. 线性阶段：stages 保持线性结构，复杂逻辑封装在复合阶段内部

    用法示例：

        # 方式 1：同步处理，直接获取结果
        processor = ExcelProcessor(llm_client)
        result = processor.process_sync(tables, query)

        # 方式 2：收集所有事件
        events, result = processor.process_with_events(tables, query)

        # 方式 3：迭代处理事件（用于 SSE 推送）
        for event in processor.process(tables, query, config):
            yield convert_to_sse(event)
    """

    def __init__(self, llm_client: "LLMClient"):
        """
        初始化处理器

        Args:
            llm_client: LLM 客户端
        """
        self.llm_client = llm_client

        # 创建各阶段实例（线性列表，保持可扩展性）
        self._stages = [
            # AnalyzeStage(llm_client),
            GenerateValidateStage(llm_client),  # 复合阶段：生成+验证（支持重试）
            ExecuteStage(),
        ]

    def process(
        self,
        tables: "FileCollection",
        query: str,
        config: Optional[ProcessConfig] = None,
    ) -> Generator[ProcessEvent, None, ProcessResult]:
        """
        处理 Excel 数据（生成器模式）

        Args:
            tables: 已加载的表集合
            query: 用户查询
            config: 处理配置

        Yields:
            ProcessEvent: 处理事件

        Returns:
            ProcessResult: 最终结果（通过 StopIteration.value 获取）

        Example:
            gen = processor.process(tables, query)
            try:
                for event in gen:
                    print(event)
            except StopIteration as e:
                result = e.value
        """
        config = config or ProcessConfig()
        result = ProcessResult()
        context = {}  # 阶段间共享上下文

        for stage in self._stages:
            try:
                # 运行阶段
                stage_gen = stage.run(tables, query, config, context)

                # 收集阶段输出
                stage_output = None
                try:
                    while True:
                        event = next(stage_gen)
                        yield event

                        # 检查是否有错误
                        if event.event_type == EventType.STAGE_ERROR:
                            result.errors.append(event.error)
                            return result

                except StopIteration as e:
                    stage_output = e.value

                # 保存阶段输出到上下文
                if stage_output is not None:
                    context[stage.stage.value] = stage_output

                # 更新结果
                self._update_result(result, stage.stage, stage_output, tables)

            except StageError as e:
                # 阶段抛出错误，yield error 事件并终止处理
                error_msg = str(e)
                result.errors.append(error_msg)
                yield ProcessEvent(
                    stage=stage.stage,
                    event_type=EventType.STAGE_ERROR,
                    error=error_msg,
                )
                return result

            except Exception as e:
                # 未预期的错误，yield error 事件并终止处理
                logger.exception(f"Stage {stage.stage.value} failed: {e}")
                error_msg = f"{stage.stage.value} 阶段异常: {e}"
                result.errors.append(error_msg)
                yield ProcessEvent(
                    stage=stage.stage,
                    event_type=EventType.STAGE_ERROR,
                    error=error_msg,
                )
                return result

        return result

    def process_sync(
        self,
        tables: "FileCollection",
        query: str,
        config: Optional[ProcessConfig] = None,
    ) -> ProcessResult:
        """
        同步处理（便捷方法）

        忽略中间事件，直接返回最终结果。

        Args:
            tables: 已加载的表集合
            query: 用户查询
            config: 处理配置

        Returns:
            ProcessResult: 处理结果
        """
        gen = self.process(tables, query, config)

        # 消费所有事件
        try:
            while True:
                next(gen)
        except StopIteration as e:
            return e.value

    def process_with_events(
        self,
        tables: "FileCollection",
        query: str,
        config: Optional[ProcessConfig] = None,
    ) -> Tuple[List[ProcessEvent], ProcessResult]:
        """
        处理并收集所有事件（便捷方法）

        Args:
            tables: 已加载的表集合
            query: 用户查询
            config: 处理配置

        Returns:
            (events, result): 事件列表和最终结果
        """
        events = []
        gen = self.process(tables, query, config)

        try:
            while True:
                event = next(gen)
                events.append(event)
        except StopIteration as e:
            return events, e.value

    def _update_result(
        self,
        result: ProcessResult,
        stage: ProcessStage,
        output: dict,
        tables: "FileCollection",
    ) -> None:
        """
        根据阶段输出更新结果

        Args:
            result: 处理结果
            stage: 当前阶段
            output: 阶段输出
            tables: 表集合
        """
        if output is None:
            return

        if stage == ProcessStage.ANALYZE:
            result.analysis = output.get("content")

        elif stage == ProcessStage.GENERATE:
            # GenerateValidateStage 复合阶段的输出
            result.operations = output.get("operations")
            # 验证错误会传递给 execute 阶段处理

        elif stage == ProcessStage.EXECUTE:
            result.formulas = output.get("formulas")
            result.variables = output.get("variables") or {}
            result.new_columns = output.get("new_columns") or {}
            result.updated_columns = output.get("updated_columns") or {}
            result.new_sheets = output.get("new_sheets") or {}

            # 处理错误
            if output.get("errors"):
                result.errors.extend(output["errors"])

            # 应用新列、更新列和新 Sheet 到表
            raw_new_columns = output.get("raw_new_columns")
            raw_updated_columns = output.get("raw_updated_columns")
            raw_new_sheets = output.get("raw_new_sheets")
            if raw_new_columns or raw_updated_columns or raw_new_sheets:
                tables.apply_changes(raw_new_columns, raw_updated_columns, raw_new_sheets)
                result.modified_tables = tables
