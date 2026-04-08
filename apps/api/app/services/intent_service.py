"""意图识别服务 - 处理意图分类和路由决策"""

import logging
from typing import Dict, List, Optional, Tuple
from uuid import UUID

from app.engine.intent_classifier import IntentClassifier, IntentType
from app.core.database import AsyncSessionLocal
from app.api.deps import get_llm_client
from app.persistence import TurnRepository

import asyncio
from app.services.excel import get_files_by_ids_from_db, load_tables_from_files

logger = logging.getLogger(__name__)


class IntentService:
    """
    意图识别服务
    
    负责：
    1. 调用意图分类器识别用户意图
    2. 根据意图决定处理路由
    3. 处理需求澄清逻辑
    4. 管理意图识别相关状态
    """
    
    def __init__(self, intent_classifier: IntentClassifier):
        """
        初始化意图服务
        
        Args:
            intent_classifier: 意图分类器实例
        """
        self.intent_classifier = intent_classifier

    # 新增功能：提取文件表头信息，供分类器使用
    async def _extract_schema_info(self, file_ids: List[str], db_session: AsyncSessionLocal, user_id: UUID) -> str:
        """使用数据管线原生的健壮方法提取 Schema"""
        if not file_ids or not db_session or not user_id:
            return "无可用表头信息"
            
        try:
            from uuid import UUID
            uuid_file_ids = [UUID(fid) if isinstance(fid, str) else fid for fid in file_ids]
            
            # 复用 processing_pipeline.py 同款的文件读取逻辑（跨越 MinIO 障碍）
            files = await get_files_by_ids_from_db(db_session, uuid_file_ids, user_id)
            file_collection = await asyncio.to_thread(load_tables_from_files, files)
            
            schema_lines = []
            for excel_file in file_collection:
                for sheet_name in excel_file.get_sheet_names():
                    table = excel_file.get_sheet(sheet_name)
                    # 提取列名
                    cols = table.get_columns()
                    schema_lines.append(f"- 文件 [{excel_file.filename}] 表 [{sheet_name}] 包含列: {', '.join(cols)}")
                    
            if schema_lines:
                return "\n".join(schema_lines)
            return "当前文件无可用列信息"
        except Exception as e:
            logger.warning(f"获取 Schema 失败: {e}")
            return "无法获取表头信息"

    async def recognize_intent(
        self,
        query: str,
        file_ids: List[str],
        thread_id: Optional[str] = None,
        db_session: Optional[AsyncSessionLocal] = None,
        user_id: Optional[UUID] = None
    ) -> Dict:
        """
        识别用户意图并返回路由决策

        Args:
            query: 用户查询文本
            file_ids: 文件ID列表
            thread_id: 线程ID（可选，用于多轮对话）
            db_session: 数据库会话（可选）
            
        Returns:
            意图识别结果，包含：
            - intent: 意图类型
            - confidence: 置信度
            - requires_clarification: 是否需要澄清
            - clarification_question: 澄清问题
            - processing_route: 建议的处理路由
            - context: 上下文信息
        """
        try:
            # === 加载历史对话 + 继承文件 ===
            history_messages: List[Dict] = []
            if thread_id and db_session:
                try:
                    repo = TurnRepository(db_session)
                    thread_uuid = UUID(thread_id)

                    # 获取全部历史轮次（带文件关联，用于文件继承）
                    recent_turns = await repo.get_thread_turns(
                        thread_uuid, with_files=True
                    )

                    # 1. 继承文件（只有当前没传文件时才继承）
                    if not file_ids:
                        for turn in recent_turns:
                            if turn.files:
                                file_ids = [str(f.id) for f in turn.files]
                                logger.info(
                                    f"🔄 从历史对话(turn={turn.turn_number})"
                                    f"中自动继承了 {len(file_ids)} 个文件"
                                )
                                break

                    # 2. 构建 messages 数组（正序：oldest first）
                    for t in reversed(recent_turns):
                        if t.user_query:
                            history_messages.append({"role": "user", "content": t.user_query})
                        if t.response_text:
                            history_messages.append({"role": "assistant", "content": t.response_text})

                except Exception as db_e:
                    logger.warning(f"尝试继承历史文件或获取历史对话失败: {db_e}")

            has_files = len(file_ids) > 0
            file_count = len(file_ids)

            # 获取真实的 Schema
            schema_info = "当前无文件或无法获取表头信息"
            if has_files and db_session and user_id:
                schema_info = await self._extract_schema_info(file_ids, db_session, user_id)

            classification_result = self.intent_classifier.classify(
                query=query,
                has_files=has_files,
                file_count=file_count,
                history_messages=history_messages,
                schema_info=schema_info
            )

            # 获取意图类型
            intent = classification_result['intent']
            confidence = classification_result['confidence']
            requires_clarification = classification_result['requires_clarification']
            clarification_question = classification_result['clarification_question']
            
            # 根据意图决定处理路由
            processing_route = self._determine_processing_route(
                intent=intent,
                requires_clarification=requires_clarification,
                has_files=has_files
            )
            
            # 构建上下文信息 - 使用增强的ContextService
            context = await self._build_context(
                intent=intent,
                thread_id=thread_id,
                file_ids=file_ids,
                query=query,  # 添加当前查询参数
                db_session=db_session
            )
            
            # 构建最终结果
            result = {
                "intent": intent,
                "confidence": confidence,
                "requires_clarification": requires_clarification,
                "clarification_question": clarification_question,
                "processing_route": processing_route,
                "context": context,
                "file_ids": file_ids if has_files else [],
                "query": query,
                "reasoning": classification_result.get('reasoning', '')
            }
            
            logger.info(f"意图识别完成: intent={intent}, route={processing_route}, "
                       f"clarification={requires_clarification}")
            
            return result
            
        except Exception as e:
            logger.error(f"意图识别失败: {e}", exc_info=True)
            # 返回错误结果
            return self._get_error_result(query, file_ids, str(e))
    
    def _determine_processing_route(
        self,
        intent: str,
        requires_clarification: bool,
        has_files: bool
    ) -> str:
        """
        根据意图决定处理路由
        
        Returns:
            处理路由路径
        """
        # 如果需要澄清，返回澄清路由
        if requires_clarification:
            return "/api/chat/clarify"
        
        # 根据意图类型返回相应路由
        if intent == IntentType.CHAT.value:
            return "/api/chat/conversation"
        elif intent == IntentType.ANALYSIS.value:
            return "/api/analysis"
        elif intent == IntentType.PROCESSING.value:
            return "/api/data/processing"
        elif intent == IntentType.UNCLEAR.value:
            return "/api/chat/clarify"
        else:
            # 未知意图，默认返回澄清路由
            return "/api/chat/clarify"
    
    async def _build_context(
        self,
        intent: str,
        thread_id: Optional[str],
        file_ids: List[str],
        query: str,
        db_session: Optional[AsyncSessionLocal] = None
    ) -> Dict:
        """
        构建上下文信息
        
        Args:
            intent: 意图类型
            thread_id: 线程ID
            file_ids: 文件ID列表
            query: 当前用户查询
            db_session: 数据库会话
            
        Returns:
            上下文信息字典
        """
        # 如果没有数据库会话，返回简化上下文
        if not db_session:
            ctx = {
                "intent": intent,
                "thread_id": thread_id,
                "file_ids": file_ids,
                "has_files": len(file_ids) > 0,
                "current_query": query,
                "timestamp": self._get_current_timestamp(),
                "note": "简化上下文（无数据库会话）"
            }
            # ANALYSIS 意图：添加场景检测
            if intent == IntentType.ANALYSIS.value:
                from app.engine.prompt import detect_analysis_scenario
                ctx["analysis_scenario"] = detect_analysis_scenario(query)
            return ctx
        
        try:
            # 导入ContextService（避免循环导入）
            from app.services.context_service import get_context_service
            
            # 获取上下文服务
            context_service = await get_context_service(db_session)
            
            # 如果有线程ID，构建完整上下文
            if thread_id:
                try:
                    thread_uuid = UUID(thread_id)
                    
                    # 构建完整上下文
                    context_data = await context_service.build_context(
                        thread_id=thread_uuid,
                        current_turn_id=None,  # 当前还没有创建turn
                        intent_type=intent,
                        current_query=query,
                        file_ids=file_ids,
                        max_history=5
                    )

                    # ANALYSIS 意图：添加场景检测
                    if intent == IntentType.ANALYSIS.value:
                        from app.engine.prompt import detect_analysis_scenario
                        context_data["analysis_scenario"] = detect_analysis_scenario(query)

                    return context_data
                    
                except (ValueError, TypeError) as e:
                    logger.warning(f"线程ID格式错误或构建上下文失败: {e}, thread_id={thread_id}")
                    # 继续使用简化上下文
            
            # 返回简化上下文
            ctx = {
                "intent": intent,
                "thread_id": thread_id,
                "file_ids": file_ids,
                "has_files": len(file_ids) > 0,
                "current_query": query,
                "timestamp": self._get_current_timestamp(),
                "note": "简化上下文（无有效线程ID或构建失败）"
            }
            if intent == IntentType.ANALYSIS.value:
                from app.engine.prompt import detect_analysis_scenario
                ctx["analysis_scenario"] = detect_analysis_scenario(query)
            return ctx
            
        except Exception as e:
            logger.error(f"构建上下文失败: {e}", exc_info=True)
            # 返回错误上下文
            ctx = {
                "intent": intent,
                "thread_id": thread_id,
                "file_ids": file_ids,
                "has_files": len(file_ids) > 0,
                "current_query": query,
                "timestamp": self._get_current_timestamp(),
                "error": str(e),
                "note": "上下文构建失败"
            }
            if intent == IntentType.ANALYSIS.value:
                from app.engine.prompt import detect_analysis_scenario
                ctx["analysis_scenario"] = detect_analysis_scenario(query)
            return ctx
    
    def _get_error_result(self, query: str, file_ids: List[str], error_msg: str) -> Dict:
        """获取错误结果"""
        return {
            "intent": IntentType.UNCLEAR.value,
            "confidence": 0.1,
            "requires_clarification": True,
            "clarification_question": f"系统处理出错: {error_msg}。请重新描述您的需求。",
            "processing_route": "/api/chat/clarify",
            "context": {
                "intent": IntentType.UNCLEAR.value,
                "thread_id": None,
                "file_ids": file_ids,
                "has_files": len(file_ids) > 0,
                "error": error_msg,
                "timestamp": self._get_current_timestamp()
            },
            "file_ids": file_ids,
            "query": query,
            "reasoning": f"意图识别失败: {error_msg}"
        }
    
    def _get_current_timestamp(self) -> str:
        """获取当前时间戳"""
        from datetime import datetime
        return datetime.now().isoformat()
    
    async def handle_clarification_response(
        self,
        original_intent_result: Dict,
        user_response: str,
        thread_id: Optional[str] = None
    ) -> Dict:
        """
        处理用户的澄清响应
        
        Args:
            original_intent_result: 原始的意图识别结果
            user_response: 用户的澄清响应
            thread_id: 线程ID
            
        Returns:
            更新后的意图识别结果
        """
        try:
            # 合并原始query和澄清响应
            original_query = original_intent_result.get('query', '')
            combined_query = f"{original_query} {user_response}".strip()
            
            # 重新识别意图
            file_ids = original_intent_result.get('file_ids', [])
            
            # 这里可以优化：使用原始分类结果作为上下文
            new_result = await self.recognize_intent(
                query=combined_query,
                file_ids=file_ids,
                thread_id=thread_id
            )
            
            # 标记这是澄清后的结果
            new_result['is_clarification_result'] = True
            new_result['original_intent'] = original_intent_result.get('intent')
            
            logger.info(f"澄清响应处理完成: 原始意图={original_intent_result.get('intent')}, "
                       f"新意图={new_result.get('intent')}")
            
            return new_result
            
        except Exception as e:
            logger.error(f"处理澄清响应失败: {e}", exc_info=True)
            # 返回错误结果
            return self._get_error_result(
                query=user_response,
                file_ids=original_intent_result.get('file_ids', []),
                error_msg=f"处理澄清响应失败: {str(e)}"
            )
    

# 工厂函数和依赖注入
async def get_intent_service(db_session: Optional[AsyncSessionLocal] = None) -> IntentService:
    """
    获取意图服务实例
    
    Args:
        db_session: 数据库会话（可选）
        
    Returns:
        IntentService实例
    """
    try:
        # 获取LLM客户端
        llm_client = await get_llm_client(db_session)
        
        # 创建意图分类器
        from app.engine.intent_classifier import create_intent_classifier
        intent_classifier = create_intent_classifier(llm_client)
        
        # 创建意图服务
        return IntentService(intent_classifier)
        
    except Exception as e:
        logger.error(f"创建意图服务失败: {e}", exc_info=True)
        raise RuntimeError(f"无法创建意图服务: {str(e)}")
