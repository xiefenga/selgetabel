"""
步骤追踪器

用于管理 ThreadTurn.steps 数组的更新，与 SSE 事件协议对齐。

详见 STEPS_STORAGE_SPEC.md
"""

from datetime import datetime, timezone
from typing import Any, Optional


class StepTracker:
    """
    步骤追踪器，管理 steps 数组的更新

    使用示例:
        tracker = StepTracker()

        tracker.start("load")
        try:
            result = do_load()
            tracker.done("load", {"schemas": result})
        except Exception as e:
            tracker.error("load", "LOAD_FAILED", str(e))
            raise

        # 获取 steps 数组用于持久化
        turn.steps = tracker.to_list()
    """

    def __init__(self, initial_steps: Optional[list] = None):
        """
        初始化步骤追踪器

        Args:
            initial_steps: 初始步骤数组（用于从数据库恢复状态）
        """
        self._steps: list[dict] = list(initial_steps) if initial_steps else []

    def _now(self) -> str:
        """获取当前时间的 ISO 格式字符串"""
        return datetime.now(timezone.utc).isoformat()

    def _find_running(self, step: str) -> Optional[dict]:
        """找到指定步骤最后一个 running 状态的记录"""
        for record in reversed(self._steps):
            if record["step"] == step and record["status"] == "running":
                return record
        return None

    def _find_streaming(self, step: str) -> Optional[dict]:
        """找到指定步骤最后一个 streaming 状态的记录"""
        for record in reversed(self._steps):
            if record["step"] == step and record["status"] == "streaming":
                return record
        return None

    def start(self, step: str) -> dict:
        """
        记录步骤开始

        Args:
            step: 步骤名称 (load, generate, validate, execute, export)

        Returns:
            新创建的步骤记录
        """
        record = {
            "step": step,
            "status": "running",
            "started_at": self._now(),
        }
        self._steps.append(record)
        return record

    def streaming(self, step: str, content: str) -> dict:
        """
        更新流式输出内容

        Args:
            step: 步骤名称
            content: 当前累积的完整内容

        Returns:
            更新后的步骤记录

        Raises:
            ValueError: 如果找不到对应的 running/streaming 状态记录
        """
        # 先查找 running 状态，再查找 streaming 状态（支持多次调用）
        record = self._find_running(step)
        if not record:
            record = self._find_streaming(step)
        if not record:
            raise ValueError(f"No running/streaming record found for step: {step}")

        record["status"] = "streaming"
        record["streaming_content"] = content
        return record

    def done(self, step: str, output: Any) -> dict:
        """
        记录步骤完成

        Args:
            step: 步骤名称
            output: 步骤输出数据

        Returns:
            更新后的步骤记录

        Raises:
            ValueError: 如果找不到对应的 running/streaming 状态记录
        """
        record = self._find_running(step)
        # 也支持从 streaming 状态转换
        if not record:
            record = self._find_streaming(step)
        if not record:
            raise ValueError(f"No running/streaming record found for step: {step}")

        record["status"] = "done"
        record["output"] = output
        record["completed_at"] = self._now()
        # 清理流式内容字段
        record.pop("streaming_content", None)
        return record

    def error(self, step: str, code: str, message: str) -> dict:
        """
        记录步骤失败

        Args:
            step: 步骤名称
            code: 错误码
            message: 错误消息

        Returns:
            更新后的步骤记录

        Raises:
            ValueError: 如果找不到对应的 running/streaming 状态记录
        """
        record = self._find_running(step)
        # 也支持从 streaming 状态转换
        if not record:
            record = self._find_streaming(step)
        if not record:
            raise ValueError(f"No running/streaming record found for step: {step}")

        record["status"] = "error"
        record["error"] = {"code": code, "message": message}
        record["completed_at"] = self._now()
        # 清理流式内容字段
        record.pop("streaming_content", None)
        return record

    def to_list(self) -> list:
        """
        获取 steps 数组

        Returns:
            步骤记录数组（可直接赋值给 ThreadTurn.steps）
        """
        return self._steps

    def get_latest(self, step: str) -> Optional[dict]:
        """
        获取指定步骤的最后一条记录

        Args:
            step: 步骤名称

        Returns:
            最后一条记录，如果没有则返回 None
        """
        for record in reversed(self._steps):
            if record["step"] == step:
                return record
        return None

    def get_all_latest(self) -> dict[str, dict]:
        """
        获取所有步骤的最后一条记录

        Returns:
            以步骤名为 key 的字典，便于前端回填
        """
        result = {}
        for record in self._steps:
            result[record["step"]] = record
        return result

    def has_error(self) -> bool:
        """检查是否有任何步骤失败（且没有后续成功）"""
        latest = self.get_all_latest()
        return any(r.get("status") == "error" for r in latest.values())

    def __len__(self) -> int:
        return len(self._steps)

    def __repr__(self) -> str:
        return f"StepTracker({self._steps})"
