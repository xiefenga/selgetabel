from typing import List, Optional
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from app.schemas.response import ApiResponse
from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.models.thread import Thread, ThreadTurn

router = APIRouter(prefix="/threads", tags=["threads"])

# ========== 线程管理 API ==========

class ThreadListItem(BaseModel):
    """线程列表项"""
    id: str
    title: Optional[str]
    status: str
    created_at: datetime
    updated_at: datetime
    turn_count: int = Field(default=0, description="消息数量")


class ThreadDetail(BaseModel):
    """线程详情"""
    id: str
    title: Optional[str]
    status: str
    created_at: datetime
    updated_at: datetime
    turns: List[dict] = Field(default_factory=list, description="消息列表")


@router.get("", response_model=ApiResponse[List[ThreadListItem]], summary="获取线程列表", description="获取当前用户的所有线程列表")
async def get_threads(limit: int = 50, offset: int = 0, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """获取用户的线程列表"""
    try:
        # 查询线程，按更新时间倒序
        stmt = (
            select(Thread, func.count(ThreadTurn.id).label("turn_count"))
            .outerjoin(ThreadTurn, Thread.id == ThreadTurn.thread_id)
            .where(Thread.user_id == current_user.id)
            .where(Thread.status == "active")
            .group_by(Thread.id)
            .order_by(Thread.updated_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await db.execute(stmt)
        rows = result.all()

        threads = []
        for thread, turn_count in rows:
            threads.append(ThreadListItem(
                id=str(thread.id),
                title=thread.title,
                status=thread.status,
                created_at=thread.created_at,
                updated_at=thread.updated_at,
                turn_count=turn_count or 0,
            ))

        return ApiResponse(
            code=0,
            data=threads,
            msg="获取成功"
        )
    except Exception as e:
        return ApiResponse(
            code=500,
            data=None,
            msg=f"获取失败: {str(e)}"
        )


@router.get("/{thread_id}", response_model=ApiResponse[ThreadDetail], summary="获取线程详情", description="获取指定线程的详细信息，包含所有消息")
async def get_thread_detail(thread_id: str, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """获取线程详情"""
    try:
        # 转换 thread_id 为 UUID
        try:
            thread_id_uuid = UUID(thread_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="无效的 thread_id 格式")

        # 查询线程
        stmt = select(Thread).where(Thread.id == thread_id_uuid).where(Thread.user_id == current_user.id)
        result = await db.execute(stmt)
        thread = result.scalar_one_or_none()

        if not thread:
            raise HTTPException(status_code=404, detail="线程不存在或无权访问")

        # 查询消息列表，预加载关联的文件
        turns_stmt = (
            select(ThreadTurn)
            .options(selectinload(ThreadTurn.files))
            .where(ThreadTurn.thread_id == thread_id_uuid)
            .order_by(ThreadTurn.turn_number.asc())
        )
        turns_result = await db.execute(turns_stmt)
        turns = turns_result.scalars().all()

        # 构建消息列表
        turns_data = []
        for turn in turns:
            # 从 steps 中提取各步骤的最终状态
            steps = turn.steps or []
            latest_steps = {}
            for step in steps:
                latest_steps[step.get("step")] = step

            turn_data = {
                "id": str(turn.id),
                "turn_number": turn.turn_number,
                "user_query": turn.user_query,
                "status": turn.status,
                "steps": steps,  # 返回完整的步骤数组，便于前端渲染
                "created_at": turn.created_at.isoformat(),
                "completed_at": turn.completed_at.isoformat() if turn.completed_at else None,
            }

            # 获取关联的文件
            if turn.files:
                files_data = []
                for f in turn.files:
                    # 构造可访问的文件 URL（与静态目录挂载保持一致）
                    file_url = "/" + f.file_path.lstrip("/")
                    files_data.append({
                        "id": str(f.id),
                        "filename": f.filename,
                        "path": file_url,
                        "size": f.file_size,
                        "mime_type": f.mime_type,
                        "uploaded_at": f.uploaded_at.isoformat(),
                    })

                turn_data["files"] = files_data

            turns_data.append(turn_data)

        return ApiResponse(
            code=0,
            data=ThreadDetail(
                id=str(thread.id),
                title=thread.title,
                status=thread.status,
                created_at=thread.created_at,
                updated_at=thread.updated_at,
                turns=turns_data,
            ),
            msg="获取成功"
        )
    except HTTPException:
        raise
    except Exception as e:
        return ApiResponse(
            code=500,
            data=None,
            msg=f"获取失败: {str(e)}"
        )


@router.delete("/{thread_id}", response_model=ApiResponse[None], summary="删除线程", description="删除指定的线程")
async def delete_thread(thread_id: str, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """删除线程"""
    try:
        # 转换 thread_id 为 UUID
        try:
            thread_id_uuid = UUID(thread_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="无效的 thread_id 格式")

        # 查询线程
        stmt = select(Thread).where(Thread.id == thread_id_uuid).where(Thread.user_id == current_user.id)
        result = await db.execute(stmt)
        thread = result.scalar_one_or_none()

        if not thread:
            raise HTTPException(status_code=404, detail="线程不存在或无权访问")

        # 软删除：更新状态
        thread.status = "deleted"
        await db.commit()

        return ApiResponse(
            code=0,
            data=None,
            msg="删除成功"
        )
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        return ApiResponse(
            code=500,
            data=None,
            msg=f"删除失败: {str(e)}"
        )