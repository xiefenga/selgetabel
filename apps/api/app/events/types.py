"""事件类型定义"""

from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional


class EventType(str, Enum):
    """
    事件类型枚举

    分为三类：
    1. 管道级事件：PIPELINE_*
    2. 步骤级事件：STEP_*
    3. 会话事件：SESSION_*
    """

    # ===== 管道级事件 =====
    PIPELINE_START = "pipeline.start"
    PIPELINE_END = "pipeline.end"
    PIPELINE_ERROR = "pipeline.error"

    # ===== 步骤级事件 =====
    STEP_START = "step.start"
    STEP_STREAMING = "step.streaming"
    STEP_DONE = "step.done"
    STEP_ERROR = "step.error"

    # ===== 会话事件 =====
    SESSION_CREATED = "session.created"


@dataclass
class Event:
    """
    事件数据

    Attributes:
        type: 事件类型
        step: 关联的步骤名称（步骤级事件必需）
        data: 事件数据
        error_code: 错误码（错误事件时）
        error_message: 错误消息（错误事件时）
    """

    type: EventType
    step: Optional[str] = None
    data: Any = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None

    @classmethod
    def step_start(cls, step: str) -> "Event":
        """创建步骤开始事件"""
        return cls(type=EventType.STEP_START, step=step)

    @classmethod
    def step_streaming(cls, step: str, delta: str) -> "Event":
        """创建步骤流式输出事件"""
        return cls(type=EventType.STEP_STREAMING, step=step, data={"delta": delta})

    @classmethod
    def step_done(cls, step: str, output: Any) -> "Event":
        """创建步骤完成事件"""
        return cls(type=EventType.STEP_DONE, step=step, data=output)

    @classmethod
    def step_error(cls, step: str, code: str, message: str) -> "Event":
        """创建步骤错误事件"""
        return cls(
            type=EventType.STEP_ERROR,
            step=step,
            error_code=code,
            error_message=message,
        )

    @classmethod
    def session_created(
        cls,
        thread_id: str,
        turn_id: str,
        title: str,
        is_new_thread: bool,
    ) -> "Event":
        """创建会话创建事件"""
        return cls(
            type=EventType.SESSION_CREATED,
            data={
                "thread_id": thread_id,
                "turn_id": turn_id,
                "title": title,
                "is_new_thread": is_new_thread,
            },
        )

    @classmethod
    def pipeline_error(cls, code: str, message: str) -> "Event":
        """创建管道错误事件"""
        return cls(
            type=EventType.PIPELINE_ERROR,
            error_code=code,
            error_message=message,
        )

    def __repr__(self) -> str:
        if self.step:
            return f"Event({self.type.value}, step={self.step!r})"
        return f"Event({self.type.value})"
