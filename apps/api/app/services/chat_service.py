"""聊天服务 - 处理纯文本对话"""

import logging
from typing import AsyncGenerator, Dict, List, Optional
from uuid import UUID

from app.engine.llm_client import LLMClient
from app.engine.context_builder import ContextBuilder, create_context_builder
from app.core.database import AsyncSessionLocal
from app.api.deps import get_llm_client
from app.persistence.turn_repository import TurnRepository
from app.models.thread import Thread, ThreadTurn
from app.core.branding import get_product_name, get_product_description

logger = logging.getLogger(__name__)


class ChatService:
    """
    聊天服务

    处理纯文本对话，不涉及文件处理。
    支持多轮对话，维护对话历史。
    """

    @staticmethod
    def _get_chat_system_prompt() -> str:
        """获取聊天系统提示词（根据 BOB_RELEASE 动态生成）"""
        product_name = get_product_name()
        product_desc = get_product_description()

        return f"""你是 {product_name} 的 AI 助手。

## 关于 {product_name}
{product_desc}。用户只需用自然语言描述数据处理需求，AI 即可生成可执行操作并输出带有公式的 Excel 文件，结果 100% 可复现，告别繁琐的公式编写。

## 核心能力

### 1. 智能 Excel 处理
- 自然语言 → 结构化 JSON 操作 → Excel 公式，全程自动化
- 支持聚合、计算列、筛选、排序、分组、VLOOKUP 等常见操作
- 输出的 Excel 文件保留完整公式，可审计、可复现

### 2. 数据透视表
- 智能识别维度字段和指标字段
- 自动生成透视表结构（行标签、列标签、数值区域、筛选器）
- 支持多维度交叉分析

### 3. 数据分析（智能洞察）
上传 Excel 文件后，可以用自然语言提出分析需求，系统会：

**L1 信息提取**
- 基本概况："这份数据大概是什么？" → 返回行列数、列名
- 数据质量："这份数据有什么问题吗？" → 检测空值、重复、异常

**L2 通用分析**
- 开放分析："分析一下这份数据" → 全画像 + LLM 全面洞察
- 指定维度："各地区的销售情况怎么样？" → 按维度聚合 + LLM 解读
- 多表联合："结合客户表分析订单" → 表关系识别 + 联合分析

**L3 专项分析**
- 相关性："销售额和销量有什么关系？" → CORREL 函数 + LLM 解读
- 对比分析："华东和华南有什么差异？" → 分组对比 + LLM 解读
- 趋势分析："销售额有什么变化趋势？" → 时间序列 + LLM 解读
- 分布描述："各产品销售分布怎么样？" → 分布统计 + LLM 解读

**L4 智能推断**
- 原因归因："为什么 C 地区销售额最高？" → 多维度下钻 + LLM 推断
- 关系发现："这些列之间有什么关系？" → 全列扫描 + 规律发现

## 你的角色
1. 解答关于 {product_name} 功能和使用方式的问题
2. 引导用户高效地描述数据处理需求
3. 回答一般性的 Excel 和数据处理技术问题
4. 保持友好、专业、简洁的语气

## 注意事项
1. 如果用户想要处理数据但尚未上传文件，提醒他们先上传 Excel 文件
2. 如果用户询问数据分析，可以介绍具体的分析场景
3. 使用中文回答，除非用户明确要求其他语言"""

    @property
    def CHAT_SYSTEM_PROMPT(self) -> str:
        """动态获取聊天系统提示词"""
        return self._get_chat_system_prompt()

    def __init__(self, llm_client: LLMClient, context_builder: Optional[ContextBuilder] = None):
        """
        初始化聊天服务
        
        Args:
            llm_client: LLM客户端
            context_builder: 上下文构建器（可选）
        """
        self.llm_client = llm_client
        self.context_builder = context_builder or create_context_builder()
    
    async def chat_stream(
        self,
        query: str,
        user_id: UUID,
        thread_id: Optional[UUID] = None,
        db_session: Optional[AsyncSessionLocal] = None,
        file_ids: List[str] = None
    ) -> AsyncGenerator[str, None]:
        """
        流式聊天（已接入富上下文系统）
        """
        try:
            # 1. 获取或创建对话线程
            thread, _ = await self._get_or_create_thread(
                user_id=user_id,
                thread_id=thread_id,
                initial_query=query,
                db_session=db_session
            )
            
            from app.services.context_service import get_context_service
            context_service = await get_context_service(db_session)
            
            context_data = await context_service.build_context(
                thread_id=thread.id,
                current_turn_id=None,
                intent_type="chat",
                current_query=query,
                file_ids=[],
                max_history=10
            )
            
            formatted_context = self.context_builder.build_prompt_context(
                intent_type="chat",
                context_data=context_data,
                current_query=query,
                current_files=[]
            )
            
            enhanced_system_prompt = f"{self.CHAT_SYSTEM_PROMPT}\n\n{formatted_context}\n请基于以上上下文回答用户的问题。"
            
            full_response = ""
            async for delta, content in self.llm_client._call_llm_stream_async(
                stage="chat",
                system_prompt=enhanced_system_prompt,
                user_message=query
            ):
                full_response = content
                yield delta
            
            turn = await self._save_conversation_turn(
                thread_id=thread.id,
                query=query,
                response=full_response,
                db_session=db_session,
                user_id=user_id,
                file_ids=file_ids
            )
            
            if turn:
                await context_service.save_context_snapshot(turn.id, context_data)
            
            logger.info(f"流式聊天完成: user={user_id}, thread={thread.id}, "
                       f"response_length={len(full_response)}")
            
        except Exception as e:
            logger.error(f"流式聊天失败: {e}", exc_info=True)
            yield f"聊天处理出错: {str(e)}"
    
    async def _get_or_create_thread(
        self,
        user_id: UUID,
        thread_id: Optional[UUID],
        initial_query: str,
        db_session: AsyncSessionLocal
    ) -> tuple[Thread, bool]:
        """
        获取或创建对话线程
        
        Returns:
            (线程对象, 是否是新线程)
        """
        if db_session is None:
            raise ValueError("需要数据库会话")
        
        repo = TurnRepository(db_session)
        
        if thread_id:
            # 获取现有线程
            thread = await repo.get_thread(thread_id, user_id)
            if not thread:
                raise ValueError(f"线程不存在或无权访问: {thread_id}")
            return thread, False
        else:
            # 创建新线程
            # 生成线程标题（使用查询的前几个词）
            title = self._generate_thread_title(initial_query)
            thread = await repo.create_thread(user_id, title)
            return thread, True

    async def _save_conversation_turn(
        self,
        thread_id: UUID,
        query: str,
        response: str,
        db_session: AsyncSessionLocal,
        user_id: Optional[UUID] = None,
        file_ids: Optional[List[str]] = None
    ) -> Optional[ThreadTurn]:
        """保存对话轮次"""
        if db_session is None: return None
        try:
            repo = TurnRepository(db_session)
            turn_number = await repo.get_next_turn_number(thread_id)
            turn = await repo.create_turn(
                thread_id=thread_id, turn_number=turn_number,
                user_query=query, intent_type="chat", response_text=response
            )
            
            if file_ids and user_id:
                try:
                    from uuid import UUID
                    file_uuids = [UUID(fid) if isinstance(fid, str) else fid for fid in file_ids]
                    await repo.link_files_to_turn(turn.id, file_uuids, user_id)
                except Exception as e:
                    logger.warning(f"聊天轮次关联文件失败: {e}")

            await repo.commit()
            return turn
        except Exception as e:
            logger.error(f"保存对话记录失败: {e}", exc_info=True)
            return None
    
    def _generate_thread_title(self, query: str) -> str:
        """
        生成线程标题
        
        Args:
            query: 初始查询
            
        Returns:
            线程标题
        """
        # 使用查询的前几个词作为标题
        words = query.strip().split()
        if len(words) <= 3:
            title = query[:30]
        else:
            title = " ".join(words[:3]) + "..."
        
        # 确保标题长度合适
        if len(title) > 50:
            title = title[:47] + "..."
        
        return title or "聊天对话"


# 工厂函数
async def get_chat_service(db_session: Optional[AsyncSessionLocal] = None) -> ChatService:
    """
    获取聊天服务实例
    
    Args:
        db_session: 数据库会话（可选）
        
    Returns:
        ChatService实例
    """
    try:
        # 获取LLM客户端
        llm_client = await get_llm_client(db_session)
        
        # 创建ContextBuilder
        context_builder = create_context_builder()
        
        # 创建聊天服务
        return ChatService(llm_client, context_builder)
        
    except Exception as e:
        logger.error(f"创建聊天服务失败: {e}", exc_info=True)
        raise RuntimeError(f"无法创建聊天服务: {str(e)}")
