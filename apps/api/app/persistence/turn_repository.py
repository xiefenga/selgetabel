"""Turn 数据访问对象"""

import logging
from datetime import datetime, timezone
from typing import Any, List, Optional
from uuid import UUID, uuid4

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.models.thread import Thread, ThreadTurn, TurnFile
from app.models.file import File
from app.engine.step_tracker import StepTracker
from app.engine.models import ExcelError

logger = logging.getLogger(__name__)


def make_json_serializable(obj: Any) -> Any:
    """
    将对象转换为可 JSON 序列化的格式

    主要处理 ExcelError、numpy 类型等
    """
    import numpy as np

    if isinstance(obj, ExcelError):
        return str(obj)
    elif isinstance(obj, np.integer):
        return int(obj)
    elif isinstance(obj, np.floating):
        return float(obj)
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    elif isinstance(obj, dict):
        return {k: make_json_serializable(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [make_json_serializable(item) for item in obj]
    elif isinstance(obj, tuple):
        return tuple(make_json_serializable(item) for item in obj)
    else:
        return obj


class TurnRepository:
    """
    Turn 数据访问对象

    封装所有与 Thread/Turn 相关的数据库操作。

    用法示例：
        repo = TurnRepository(db)
        thread = await repo.get_or_create_thread(ctx)
        turn = await repo.create_turn(thread.id, ctx)
        await repo.update_step(turn.id, tracker)
        await repo.mark_completed(turn.id)
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    def _serialize_steps(self, tracker: StepTracker) -> list:
        """
        将 tracker.to_list() 序列化为完全兼容 JSON 的纯 Python 对象。

        使用 JSON 往返确保所有 numpy/pandas 类型被彻底转换为原生类型。
        """
        import json as _json
        import numpy as _np

        raw = make_json_serializable(tracker.to_list())

        def _convert(obj):
            if isinstance(obj, _np.integer):
                return int(obj)
            if isinstance(obj, _np.floating):
                return float(obj)
            if isinstance(obj, _np.ndarray):
                return obj.tolist()
            if isinstance(obj, _np.bool_):
                return bool(obj)
            if isinstance(obj, dict):
                return {k: _convert(v) for k, v in obj.items()}
            if isinstance(obj, list):
                return [_convert(i) for i in obj]
            if isinstance(obj, tuple):
                return tuple(_convert(i) for i in obj)
            return obj

        cleaned = _convert(raw)
        return _json.loads(_json.dumps(cleaned))

    async def get_thread(self, thread_id: UUID, user_id: UUID) -> Optional[Thread]:
        """
        获取线程

        Args:
            thread_id: 线程 ID
            user_id: 用户 ID（用于权限验证）

        Returns:
            Thread 对象，如果不存在或无权限则返回 None
        """
        stmt = (
            select(Thread)
            .where(Thread.id == thread_id)
            .where(Thread.user_id == user_id)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()
    
    async def get_thread_turns(
        self,
        thread_id: UUID,
        limit: Optional[int] = None,
        with_files: bool = False,
    ) -> List[ThreadTurn]:
        """
        获取线程的历史对话轮次

        Args:
            thread_id: 线程 ID
            limit: 返回的最大轮次数，None 表示不限
            with_files: 是否 eager load 关联文件

        Returns:
            按轮次倒序排列的 ThreadTurn 列表（最新的在前）
        """
        from sqlalchemy.orm import selectinload

        stmt = (
            select(ThreadTurn)
            .where(ThreadTurn.thread_id == thread_id)
            .order_by(ThreadTurn.turn_number.desc())
        )
        if with_files:
            stmt = stmt.options(selectinload(ThreadTurn.files))
        if limit is not None:
            stmt = stmt.limit(limit)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def create_thread(
        self,
        user_id: UUID,
        title: str,
    ) -> Thread:
        """
        创建新线程

        Args:
            user_id: 用户 ID
            title: 线程标题

        Returns:
            新创建的 Thread 对象
        """
        thread = Thread(
            id=uuid4(),
            user_id=user_id,
            title=title,
            status="active",
        )
        self.db.add(thread)
        await self.db.flush()
        return thread

    async def get_next_turn_number(self, thread_id: UUID) -> int:
        """
        获取下一个 turn 序号

        Args:
            thread_id: 线程 ID

        Returns:
            下一个 turn 序号
        """
        stmt = select(func.max(ThreadTurn.turn_number)).where(
            ThreadTurn.thread_id == thread_id
        )
        result = await self.db.execute(stmt)
        max_turn_number = result.scalar_one_or_none() or 0
        return max_turn_number + 1

    async def get_turn(self, turn_id: UUID) -> Optional[ThreadTurn]:
        """根据 turn_id 获取 turn"""
        stmt = select(ThreadTurn).where(ThreadTurn.id == turn_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def create_turn(
        self,
        thread_id: UUID,
        turn_number: int,
        user_query: str,
        intent_type: Optional[str] = None,
        response_text: Optional[str] = None,
        parent_turn_id: Optional[UUID] = None,
        context_snapshot: Optional[dict] = None,
    ) -> ThreadTurn:
        """
        创建新的 turn

        Args:
            thread_id: 线程 ID
            turn_number: turn 序号
            user_query: 用户查询
            intent_type: 意图类型（可选）
            response_text: AI 回复文本（可选）
            parent_turn_id: 父轮次ID（可选，用于对话链）
            context_snapshot: 上下文快照（可选）

        Returns:
            新创建的 ThreadTurn 对象
        """
        turn = ThreadTurn(
            id=uuid4(),
            thread_id=thread_id,
            turn_number=turn_number,
            user_query=user_query,
            status="pending",
            intent_type=intent_type,
            response_text=response_text,
            steps=[],
            parent_turn_id=parent_turn_id,
            context_snapshot=context_snapshot,
        )
        self.db.add(turn)
        await self.db.flush()
        return turn

    async def link_files_to_turn(
        self,
        turn_id: UUID,
        file_ids: List[UUID],
        user_id: UUID,
    ) -> List[UUID]:
        """
        关联文件到 turn

        Args:
            turn_id: Turn ID
            file_ids: 文件 ID 列表
            user_id: 用户 ID（用于权限验证）

        Returns:
            成功关联的文件 ID 列表

        Raises:
            ValueError: 如果某个文件不存在或无权限
        """
        linked_ids = []
        for file_id in file_ids:
            # 验证文件权限
            stmt = (
                select(File)
                .where(File.id == file_id)
                .where(File.user_id == user_id)
            )
            result = await self.db.execute(stmt)
            file_record = result.scalar_one_or_none()
            if not file_record:
                raise ValueError(f"文件不存在或无权访问: {file_id}")

            # 创建关联
            turn_file = TurnFile(
                id=uuid4(),
                turn_id=turn_id,
                file_id=file_id,
            )
            self.db.add(turn_file)
            linked_ids.append(file_id)

        await self.db.flush()
        return linked_ids

    async def update_turn_status(
        self,
        turn_id: UUID,
        status: str,
        started_at: Optional[datetime] = None,
        completed_at: Optional[datetime] = None,
    ) -> None:
        """
        更新 turn 状态

        Args:
            turn_id: Turn ID
            status: 新状态
            started_at: 开始时间
            completed_at: 完成时间
        """
        stmt = select(ThreadTurn).where(ThreadTurn.id == turn_id)
        result = await self.db.execute(stmt)
        turn = result.scalar_one_or_none()
        if turn:
            turn.status = status
            if started_at:
                turn.started_at = started_at
            if completed_at:
                turn.completed_at = completed_at
            await self.db.flush()

    async def save_steps(
        self,
        turn_id: UUID,
        tracker: StepTracker,
    ) -> None:
        """
        保存步骤状态

        Args:
            turn_id: Turn ID
            tracker: 步骤追踪器
        """
        stmt = select(ThreadTurn).where(ThreadTurn.id == turn_id)
        result = await self.db.execute(stmt)
        turn = result.scalar_one_or_none()
        if turn:
            turn.steps = self._serialize_steps(tracker)
            flag_modified(turn, "steps")
            await self.db.flush()

    async def mark_processing(self, turn_id: UUID, tracker: StepTracker) -> None:
        """
        标记 turn 为处理中

        Args:
            turn_id: Turn ID
            tracker: 步骤追踪器
        """
        stmt = select(ThreadTurn).where(ThreadTurn.id == turn_id)
        result = await self.db.execute(stmt)
        turn = result.scalar_one_or_none()
        if turn:
            turn.status = "processing"
            turn.started_at = datetime.now(timezone.utc)
            turn.steps = self._serialize_steps(tracker)
            flag_modified(turn, "steps")
            await self.db.flush()

    async def mark_completed(
        self,
        turn_id: UUID,
        thread_id: UUID,
        tracker: StepTracker,
    ) -> None:
        """
        标记 turn 为完成

        Args:
            turn_id: Turn ID
            thread_id: Thread ID（用于更新线程时间）
            tracker: 步骤追踪器
        """
        now = datetime.now(timezone.utc)

        # 更新 turn
        turn_stmt = select(ThreadTurn).where(ThreadTurn.id == turn_id)
        turn_result = await self.db.execute(turn_stmt)
        turn = turn_result.scalar_one_or_none()
        if turn:
            turn.status = "completed"
            turn.completed_at = now
            turn.steps = self._serialize_steps(tracker)
            flag_modified(turn, "steps")

        # 更新 thread
        thread_stmt = select(Thread).where(Thread.id == thread_id)
        thread_result = await self.db.execute(thread_stmt)
        thread = thread_result.scalar_one_or_none()
        if thread:
            thread.updated_at = now
            # 检查是否有错误步骤，如有则标记为异常
            if tracker.has_error():
                thread.health_status = "error"

        await self.db.flush()

    async def mark_failed(
        self,
        turn_id: UUID,
        thread_id: UUID,
        tracker: StepTracker,
    ) -> None:
        """
        标记 turn 为失败

        Args:
            turn_id: Turn ID
            thread_id: Thread ID（用于更新线程健康状态）
            tracker: 步骤追踪器
        """
        stmt = select(ThreadTurn).where(ThreadTurn.id == turn_id)
        result = await self.db.execute(stmt)
        turn = result.scalar_one_or_none()
        if turn:
            turn.status = "failed"
            turn.steps = self._serialize_steps(tracker)
            flag_modified(turn, "steps")

        # 更新线程健康状态为异常
        thread_stmt = select(Thread).where(Thread.id == thread_id)
        thread_result = await self.db.execute(thread_stmt)
        thread = thread_result.scalar_one_or_none()
        if thread:
            thread.health_status = "error"

        await self.db.flush()

    async def update_context_snapshot(
        self,
        turn_id: UUID,
        context_snapshot: dict,
    ) -> bool:
        """
        更新上下文快照

        Args:
            turn_id: Turn ID
            context_snapshot: 上下文快照数据

        Returns:
            是否更新成功
        """
        try:
            stmt = select(ThreadTurn).where(ThreadTurn.id == turn_id)
            result = await self.db.execute(stmt)
            turn = result.scalar_one_or_none()
            
            if not turn:
                logger.error(f"更新上下文快照失败: 找不到轮次 {turn_id}")
                return False
            
            # 更新上下文快照
            turn.context_snapshot = make_json_serializable(context_snapshot)
            flag_modified(turn, "context_snapshot")
            await self.db.flush()
            
            logger.info(f"更新上下文快照成功: turn_id={turn_id}")
            return True
            
        except Exception as e:
            logger.error(f"更新上下文快照失败: {e}", exc_info=True)
            return False

    async def get_or_create_thread(
        self,
        user_id: UUID,
        thread_id: Optional[UUID],
        initial_query: str,
    ) -> tuple["Thread", bool]:
        """
        获取或创建线程。

        Args:
            user_id: 用户 ID
            thread_id: 线程 ID（None 表示创建新线程）
            initial_query: 初始查询（用于生成标题）

        Returns:
            (Thread, is_new): 线程对象 + 是否是新创建
        """
        if thread_id:
            existing = await self.get_thread(thread_id, user_id)
            if existing:
                return existing, False

        title = self._generate_thread_title(initial_query)
        thread = await self.create_thread(user_id, title)
        return thread, True

    def _generate_thread_title(self, query: str) -> str:
        """生成线程标题（取查询前3个词）"""
        words = query.strip().split()
        title = " ".join(words[:3])[:50]
        return title or "新对话"

    async def get_latest_turn(self, thread_id: UUID) -> Optional["ThreadTurn"]:
        """
        获取线程最新的一个 Turn。

        Args:
            thread_id: 线程 ID

        Returns:
            最新 Turn 或 None（线程无 Turn 时）
        """
        turns = await self.get_thread_turns(thread_id, limit=1)
        return turns[0] if turns else None

    async def save_messages_history(
        self,
        turn_id: UUID,
        messages: list[dict],
    ) -> None:
        """
        保存对话历史到 Turn。

        Args:
            turn_id: Turn ID
            messages: [{"role": "user"|"assistant", "content": str}] 列表
        """
        turn = await self.get_turn(turn_id)
        if not turn:
            logger.warning(f"save_messages_history: turn {turn_id} 不存在，跳过")
            return
        turn.messages_history = {"messages": messages}
        flag_modified(turn, "messages_history")
        await self.flush()

    async def load_messages_history(
        self,
        thread_id: UUID,
    ) -> list[dict]:
        """
        从线程最新 Turn 加载对话历史。

        Args:
            thread_id: 线程 ID

        Returns:
            [{"role": ..., "content": ...}] 列表，空列表表示无历史
        """
        turn = await self.get_latest_turn(thread_id)
        if not turn or not turn.messages_history:
            return []
        return turn.messages_history.get("messages", [])

    async def flush(self) -> None:
        """Flush 当前 session（不 commit）"""
        await self.db.flush()

    async def commit(self) -> None:
        """提交事务"""
        await self.db.commit()

    async def rollback(self) -> None:
        """回滚事务"""
        await self.db.rollback()
