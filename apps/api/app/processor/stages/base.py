"""阶段基类"""

import uuid
from abc import ABC, abstractmethod
from typing import Any, Generator, Optional, TYPE_CHECKING

from ..types import ProcessStage, EventType, ProcessEvent, ProcessConfig

if TYPE_CHECKING:
    from app.engine.models import FileCollection


class Stage(ABC):
    """
    处理阶段基类

    每个阶段负责一个独立的处理步骤，通过 yield ProcessEvent 报告进度。

    实现指南：
    1. 设置 stage 属性标识阶段
    2. 实现 run() 方法，yield 事件，return 输出
    3. 如需流式输出，在 run() 中检查 config.stream_llm
    4. 使用 _generate_stage_id() 生成唯一标识
    """

    stage: ProcessStage

    @abstractmethod
    def run(
        self,
        tables: "FileCollection",
        query: str,
        config: ProcessConfig,
        context: dict,
    ) -> Generator[ProcessEvent, None, Any]:
        """
        执行阶段处理

        Args:
            tables: 表集合
            query: 用户查询
            config: 处理配置
            context: 上下文字典（用于传递前序阶段的输出）

        Yields:
            ProcessEvent: 处理事件

        Returns:
            阶段输出（将存入 context[stage.value]）
        """
        pass

    @staticmethod
    def _generate_stage_id() -> str:
        """生成唯一的 stage_id"""
        return str(uuid.uuid4())

    def _event_start(self, stage_id: Optional[str] = None) -> ProcessEvent:
        """创建开始事件"""
        return ProcessEvent(self.stage, EventType.STAGE_START, stage_id=stage_id)

    def _event_stream(self, delta: str, stage_id: Optional[str] = None) -> ProcessEvent:
        """创建流式事件"""
        return ProcessEvent(self.stage, EventType.STAGE_STREAM, stage_id=stage_id, delta=delta)

    def _event_done(self, output: Any, stage_id: Optional[str] = None) -> ProcessEvent:
        """创建完成事件"""
        return ProcessEvent(self.stage, EventType.STAGE_DONE, stage_id=stage_id, output=output)

    def _event_error(self, error: str, stage_id: Optional[str] = None) -> ProcessEvent:
        """创建错误事件"""
        return ProcessEvent(self.stage, EventType.STAGE_ERROR, stage_id=stage_id, error=error)
