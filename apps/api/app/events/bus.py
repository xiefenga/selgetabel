"""事件总线实现"""

import logging
from typing import Callable, Dict, List, Awaitable

from .types import EventType, Event

logger = logging.getLogger(__name__)

# 事件处理器类型：接收 Event，返回 None
EventHandler = Callable[[Event], Awaitable[None]]


class EventBus:
    """
    事件总线 - 解耦事件生产者和消费者

    支持异步事件处理器，同一事件类型可以注册多个处理器。

    用法示例：
        bus = EventBus()

        # 注册处理器
        async def on_step_done(event: Event):
            print(f"Step {event.step} done: {event.data}")

        bus.on(EventType.STEP_DONE, on_step_done)

        # 发布事件
        await bus.emit(Event.step_done("load", {"schemas": {...}}))
    """

    def __init__(self):
        self._handlers: Dict[EventType, List[EventHandler]] = {}

    def on(self, event_type: EventType, handler: EventHandler) -> None:
        """
        注册事件处理器

        Args:
            event_type: 事件类型
            handler: 异步处理函数
        """
        if event_type not in self._handlers:
            self._handlers[event_type] = []
        self._handlers[event_type].append(handler)

    def off(self, event_type: EventType, handler: EventHandler) -> None:
        """
        移除事件处理器

        Args:
            event_type: 事件类型
            handler: 要移除的处理函数
        """
        if event_type in self._handlers:
            try:
                self._handlers[event_type].remove(handler)
            except ValueError:
                pass

    async def emit(self, event: Event) -> None:
        """
        发布事件

        按注册顺序依次调用所有处理器。如果某个处理器抛出异常，
        会记录日志但不会影响其他处理器的执行。

        Args:
            event: 要发布的事件
        """
        handlers = self._handlers.get(event.type, [])
        for handler in handlers:
            try:
                await handler(event)
            except Exception as e:
                logger.exception(
                    f"Event handler error: {handler.__name__} for {event.type.value}: {e}"
                )

    def clear(self) -> None:
        """清除所有处理器"""
        self._handlers.clear()

    def has_handlers(self, event_type: EventType) -> bool:
        """
        检查是否有处理器

        Args:
            event_type: 事件类型

        Returns:
            True 表示有处理器
        """
        return bool(self._handlers.get(event_type))

    def __repr__(self) -> str:
        handler_counts = {
            et.value: len(handlers) for et, handlers in self._handlers.items()
        }
        return f"EventBus(handlers={handler_counts})"
