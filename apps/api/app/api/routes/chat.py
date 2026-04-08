"""聊天路由 - 统一入口端点"""

import logging
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from app.api.deps import get_current_user, get_db
from app.core.sse import sse
from app.engine.intent_classifier import IntentType
from app.models.user import User
from app.services.chat_stream import stream_chat_response
from app.services.intent_service import get_intent_service
from app.services.processing_pipeline import stream_processing_pipeline
from app.services.analysis_stream import stream_analysis_response

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat")


# ============ Request/Response Models ============


class ChatRequest(BaseModel):
    """聊天请求"""

    query: str = Field(..., description="用户查询的自然语言描述")
    file_ids: List[str] = Field(
        default_factory=list,
        description="上传文件返回的 file_id 列表（UUID 字符串），支持多个文件",
    )
    thread_id: Optional[str] = Field(None, description="线程 ID（可选，用于继续会话）")


class ChatResponse(BaseModel):
    """聊天响应 (保留以供非流式接口使用)"""

    intent: str = Field(..., description="意图类型: chat|analysis|processing|unclear")
    confidence: float = Field(..., description="置信度 (0.0-1.0)", ge=0.0, le=1.0)
    requires_clarification: bool = Field(..., description="是否需要澄清")
    clarification_question: Optional[str] = Field(None, description="如果需要澄清的问题")
    processing_route: str = Field(..., description="建议的处理路由")
    context: dict = Field(..., description="上下文信息")
    file_ids: List[str] = Field(..., description="文件ID列表")
    query: str = Field(..., description="用户查询")
    reasoning: Optional[str] = Field(None, description="分类理由")


class ClarifyRequest(BaseModel):
    """澄清请求"""

    original_intent_result: dict = Field(..., description="原始的意图识别结果")
    user_response: str = Field(..., description="用户的澄清响应")
    thread_id: Optional[str] = Field(None, description="线程 ID")


# ============ Error Codes ============


class ChatErrorCode:
    """错误码常量"""

    INVALID_FILE_IDS = "INVALID_FILE_IDS"


# ============ API Endpoints ============


@router.post("")
async def chat(
    request: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    统一入口端点 (SSE 流式返回)

    接收用户请求，识别意图：
    1. 如果需要澄清或意图为 Chat，则直接通过 `generate` step 返回文字流。
    2. 如果为明确的处理任务，则进入处理流程。
    """

    async def stream():
        try:
            # === 验证并转换 file_ids ===
            file_ids: List[str] = []
            if request.file_ids:
                try:
                    file_ids = [str(UUID(fid)) for fid in request.file_ids]
                except ValueError as e:
                    yield sse(
                        {
                            "code": ChatErrorCode.INVALID_FILE_IDS,
                            "message": f"无效的 file_id 格式: {e}",
                        },
                        event="error",
                    )
                    return

            # === 意图识别 ===
            intent_service = await get_intent_service(db)
            intent_result = await intent_service.recognize_intent(
                query=request.query,
                file_ids=file_ids,
                thread_id=request.thread_id,
                db_session=db,
                user_id=current_user.id
            )
            file_ids = intent_result.get("file_ids", file_ids)

            if intent_result.get("requires_clarification") or intent_result.get("intent") == IntentType.CHAT.value:
                async for event in stream_chat_response(
                    query=request.query,
                    user_id=current_user.id,
                    thread_id=request.thread_id,
                    intent_result=intent_result,
                    db=db,
                    file_ids=file_ids,
                ):
                    yield event
                return

            if intent_result.get("intent") == IntentType.ANALYSIS.value:
                # ANALYSIS 走轻量路径，直接流式返回，不经过 ExcelProcessor
                async for event in stream_analysis_response(
                    query=request.query,
                    user_id=current_user.id,
                    thread_id=request.thread_id,
                    db=db,
                    file_ids=[UUID(fid) for fid in file_ids],
                    intent_context=intent_result.get("context", {}),
                ):
                    yield event
                return

            if intent_result.get("intent") == IntentType.PROCESSING.value:
                async for event in stream_processing_pipeline(
                    db=db,
                    user_id=current_user.id,
                    query=request.query,
                    file_ids=[UUID(fid) for fid in file_ids],
                    thread_id=UUID(request.thread_id) if request.thread_id else None,
                    intent_type=intent_result.get("intent"),
                    intent_context=intent_result.get("context", {}),
                    enhance_query_with_history=True,
                ):
                    yield event
                return

        except Exception as e:
            logger.error(f"处理请求流失败: {e}", exc_info=True)
            yield sse({"message": f"处理失败: {str(e)}"}, event="error")

    return EventSourceResponse(stream())


@router.post(
    "/clarify",
    response_model=ChatResponse,
    description="处理用户的澄清响应(备用非流式接口)",
)
async def clarify(
    request: ClarifyRequest,
    _current_user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    """处理澄清响应 (非流式接口)"""
    original_result = request.original_intent_result
    if not original_result or "intent" not in original_result:
        raise HTTPException(status_code=400, detail="无效的原始意图结果")

    try:
        intent_service = await get_intent_service(db)
        updated_result = await intent_service.handle_clarification_response(
            original_intent_result=original_result,
            user_response=request.user_response,
            thread_id=request.thread_id,
        )
        return ChatResponse(**updated_result)
    except Exception as e:
        logger.error(f"处理澄清响应失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"处理澄清响应失败: {str(e)}")


@router.get(
    "/intents",
    description="获取支持的意图类型列表",
)
async def get_supported_intents():
    """获取系统支持的意图类型列表"""
    intents = []
    for intent_type in IntentType:
        intents.append(
            {
                "value": intent_type.value,
                "label": intent_type.name,
                "description": _get_intent_description(intent_type),
            }
        )
    return {"intents": intents, "count": len(intents)}


# ============ Helper Functions ============


def _get_intent_description(intent_type: IntentType) -> str:
    """获取意图类型描述"""
    descriptions = {
        IntentType.CHAT: "纯文本对话，不涉及文件处理",
        IntentType.ANALYSIS: "数据分析总结，生成洞察报告",
        IntentType.PROCESSING: "数据处理操作，修改或转换数据",
        IntentType.UNCLEAR: "需求不明确，需要进一步澄清",
    }
    return descriptions.get(intent_type, "未知意图类型")
