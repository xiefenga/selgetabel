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

    主要处理 ExcelError 等自定义类型
    """
    if isinstance(obj, ExcelError):
        return str(obj)
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

    async def create_turn(
        self,
        thread_id: UUID,
        turn_number: int,
        user_query: str,
    ) -> ThreadTurn:
        """
        创建新的 turn

        Args:
            thread_id: 线程 ID
            turn_number: turn 序号
            user_query: 用户查询

        Returns:
            新创建的 ThreadTurn 对象
        """
        turn = ThreadTurn(
            id=uuid4(),
            thread_id=thread_id,
            turn_number=turn_number,
            user_query=user_query,
            status="pending",
            steps=[],
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
            turn.steps = make_json_serializable(tracker.to_list())
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
            turn.steps = make_json_serializable(tracker.to_list())
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
            turn.steps = make_json_serializable(tracker.to_list())
            flag_modified(turn, "steps")

        # 更新 thread
        thread_stmt = select(Thread).where(Thread.id == thread_id)
        thread_result = await self.db.execute(thread_stmt)
        thread = thread_result.scalar_one_or_none()
        if thread:
            thread.updated_at = now

        await self.db.flush()

    async def mark_failed(
        self,
        turn_id: UUID,
        tracker: StepTracker,
    ) -> None:
        """
        标记 turn 为失败

        Args:
            turn_id: Turn ID
            tracker: 步骤追踪器
        """
        stmt = select(ThreadTurn).where(ThreadTurn.id == turn_id)
        result = await self.db.execute(stmt)
        turn = result.scalar_one_or_none()
        if turn:
            turn.status = "failed"
            turn.steps = make_json_serializable(tracker.to_list())
            flag_modified(turn, "steps")
            await self.db.flush()

    async def commit(self) -> None:
        """提交事务"""
        await self.db.commit()

    async def rollback(self) -> None:
        """回滚事务"""
        await self.db.rollback()
