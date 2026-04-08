"""LLM 客户端模块 - 通过 Provider 适配层调用 LLM，支持两步流程"""

import logging
import asyncio
from typing import Optional, Dict, List, Generator, Tuple, AsyncGenerator
from app.engine.llm_providers import ProviderRegistry
from app.engine.llm_types import (
    LLMStageConfig,
    LLMRequest,
)
from app.engine.prompt import (
    get_analysis_prompt_with_schema,
    get_generation_prompt_with_context,
)

logging.basicConfig(level=logging.INFO)

logger = logging.getLogger("llm_client")

logger.setLevel(logging.INFO)

class LLMClient:
    """LLM 客户端类，支持两步流程生成操作描述"""

    def __init__(
        self,
        stage_configs: Dict[str, LLMStageConfig],
        provider_registry: Optional[ProviderRegistry] = None,
    ):
        """
        初始化 LLM 客户端

        Args:
            stage_configs: 阶段路由配置（stage -> LLMStageConfig），必须从数据库加载
            provider_registry: Provider Registry（可注入用于扩展或测试）
        """
        if not stage_configs:
            raise ValueError("未配置 LLM 路由，请在管理后台配置 llm_stage_routes。")
        self.stage_configs = stage_configs
        self.provider_registry = provider_registry or ProviderRegistry()

    def _resolve_stage_config(self, stage: str) -> LLMStageConfig:
        if stage in self.stage_configs:
            return self.stage_configs[stage]
        if "default" in self.stage_configs:
            return self.stage_configs["default"]
        raise ValueError(f"未配置 LLM 路由: {stage}")

    def _build_request(
        self,
        stage_config: LLMStageConfig,
        messages: List[Dict[str, str]],
    ) -> LLMRequest:
        defaults = stage_config.model.defaults or {}
        # 合并 extra_params，支持 provider 特定参数（如 endpoint_suffix）
        extra_params = defaults.get("extra_params") or {}
        if "endpoint_suffix" in defaults:
            extra_params = {**extra_params, "endpoint_suffix": defaults["endpoint_suffix"]}
        return LLMRequest(
            model_id=stage_config.model.model_id,
            messages=messages,
            temperature=defaults.get("temperature", 0),
            max_tokens=defaults.get("max_tokens"),
            response_format=defaults.get("response_format"),
            extra_params=extra_params,
        )

    def call_llm(
        self,
        stage: str,
        system_prompt: str,
        user_message: Optional[str] = None,
        messages: Optional[List[Dict[str, str]]] = None,
    ) -> str:
        """对外公开的 LLM 调用（非流式）

        两种使用方式：
        1. 简单模式：传 user_message，自动组装为 [system, user]
        2. 多轮模式：传 messages（不含 system），自动在前面加 system
        """
        return self._call_llm(stage, system_prompt, user_message, messages)

    def _call_llm(
        self,
        stage: str,
        system_prompt: str,
        user_message: Optional[str] = None,
        messages: Optional[List[Dict[str, str]]] = None,
    ) -> str:
        """
        调用 LLM

        Args:
            stage: 阶段名称
            system_prompt: 系统提示词
            user_message: 用户消息（简单场景）
            messages: 完整消息列表，不含 system（多轮对话场景）

        Returns:
            LLM 响应内容
        """
        stage_config = self._resolve_stage_config(stage)
        provider = stage_config.provider
        model = stage_config.model

        # 构建消息列表
        if messages:
            full_messages = [{"role": "system", "content": system_prompt}] + messages
        else:
            full_messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message or ""},
            ]

        log_msg = (
            "\n"
            "[LLM 调用] 非流式\n"
            f"[阶段] {stage}\n"
            f"[Provider] {provider.name} ({provider.type})\n"
            f"[模型] {model.model_id}\n"
            f"[消息数] {len(full_messages)}\n"
            "[System Prompt]\n"
            f"{system_prompt}\n"
        )
        for i, msg in enumerate(full_messages[1:], 1):
            log_msg += f"[{msg['role'].upper()} #{i}]\n{msg['content']}\n"

        logger.info(log_msg)

        request = self._build_request(stage_config, full_messages)
        adapter = self.provider_registry.get_adapter(provider)
        response = adapter.complete(request)
        result = response.content.strip()

        logger.info(f"\n[LLM 响应内容]\n{result}")

        return result

    def _call_llm_stream(
        self,
        stage: str,
        system_prompt: str,
        user_message: Optional[str] = None,
        messages: Optional[List[Dict[str, str]]] = None
    ) -> Generator[Tuple[str, str], None, None]:
        """
        流式调用 LLM（同步版本）

        Args:
            system_prompt: 系统提示词
            user_message: 用户消息（简单场景使用）
            messages: 完整消息列表（多轮对话场景使用，不含 system）

        Yields:
            Tuple[str, str]: (delta, full_content) - 增量内容和累积的完整内容
        """
        # 构建消息列表
        if messages:
            # 多轮对话模式：使用传入的消息列表
            full_messages = [{"role": "system", "content": system_prompt}] + messages
        else:
            # 简单模式：单条用户消息
            full_messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message or ""}
            ]

        # 打印提示词日志
        stage_config = self._resolve_stage_config(stage)
        provider = stage_config.provider
        model = stage_config.model

        log_msg = (
            "\n"
            "[LLM 调用] 流式\n"
            f"[阶段] {stage}\n"
            f"[Provider] {provider.name} ({provider.type})\n"
            f"[模型] {model.model_id}\n"
            f"[消息数] {len(full_messages)}\n"
            "[System Prompt]\n"
            f"{system_prompt}\n"
        )
        for i, msg in enumerate(full_messages[1:], 1):
            log_msg += f"[{msg['role'].upper()} #{i}]\n{msg['content']}\n"

        logger.info(log_msg)

        request = self._build_request(stage_config, full_messages)
        adapter = self.provider_registry.get_adapter(provider)

        full_content = ""
        for chunk in adapter.stream(request):
            full_content = chunk.full_content
            yield chunk.delta, chunk.full_content

        logger.info(f"\n[LLM 响应内容]\n{full_content}")

    async def _call_llm_stream_async(
        self,
        stage: str,
        system_prompt: str,
        user_message: str,
    ) -> AsyncGenerator[Tuple[str, str], None]:
        """
        流式调用 LLM（异步版本）

        使用队列在后台线程和协程之间传递流式数据，避免阻塞事件循环。

        Args:
            system_prompt: 系统提示词
            user_message: 用户消息

        Yields:
            Tuple[str, str]: (delta, full_content) - 增量内容和累积的完整内容
        """
        queue: asyncio.Queue[Tuple[str, str] | None | Exception] = asyncio.Queue()
        loop = asyncio.get_running_loop()

        def stream_in_thread():
            """在后台线程中执行流式调用"""
            try:
                for item in self._call_llm_stream(stage, system_prompt, user_message):
                    # 使用 call_soon_threadsafe 安全地放入队列
                    loop.call_soon_threadsafe(queue.put_nowait, item)
                # 发送结束信号
                loop.call_soon_threadsafe(queue.put_nowait, None)
            except Exception as e:
                loop.call_soon_threadsafe(queue.put_nowait, e)

        # 在后台线程中启动流式调用
        loop.run_in_executor(None, stream_in_thread)

        # 从队列中读取数据
        while True:
            item = await queue.get()
            if item is None:
                break
            if isinstance(item, Exception):
                raise item
            yield item

    # ==================== 第一步：需求分析 ====================

    def analyze_requirement(self, user_requirement: str, table_schemas: Optional[Dict[str, Dict[str, str]]] = None) -> str:
        """
        第一步：分析用户需求

        Args:
            user_requirement: 用户的数据处理需求描述
            table_schemas: 表结构信息

        Returns:
            需求分析结果（自然语言）
        """
        system_prompt = get_analysis_prompt_with_schema(table_schemas)

        try:
            result = self._call_llm("analyze", system_prompt, user_requirement)
            return result
        except Exception as e:
            raise RuntimeError(f"需求分析失败: {str(e)}") from e

    def analyze_requirement_stream(self, user_requirement: str, table_schemas: Optional[Dict[str, Dict[str, str]]] = None) -> Generator[Tuple[str, str], None, None]:
        """
        第一步：分析用户需求（流式输出，同步版本）

        Args:
            user_requirement: 用户的数据处理需求描述
            table_schemas: 表结构信息

        Yields:
            Tuple[str, str]: (delta, full_content) - 增量内容和累积的完整内容
        """
        system_prompt = get_analysis_prompt_with_schema(table_schemas)

        try:
            yield from self._call_llm_stream("analyze", system_prompt, user_requirement)
        except Exception as e:
            raise RuntimeError(f"需求分析失败: {str(e)}") from e

    async def analyze_requirement_stream_async(self, user_requirement: str, table_schemas: Optional[Dict[str, Dict[str, str]]] = None) -> AsyncGenerator[Tuple[str, str], None]:
        """
        第一步：分析用户需求（流式输出，异步版本）

        Args:
            user_requirement: 用户的数据处理需求描述
            table_schemas: 表结构信息

        Yields:
            Tuple[str, str]: (delta, full_content) - 增量内容和累积的完整内容
        """
        system_prompt = get_analysis_prompt_with_schema(table_schemas)

        try:
            async for item in self._call_llm_stream_async("analyze", system_prompt, user_requirement):
                yield item
        except Exception as e:
            raise RuntimeError(f"需求分析失败: {str(e)}") from e

    # ==================== 第二步：生成操作描述 ====================

    def generate_operations(
        self,
        user_requirement: str,
        analysis_result: str,
        table_schemas: Optional[Dict[str, Dict[str, str]]] = None,
        previous_errors: Optional[List[str]] = None,
        previous_json: Optional[str] = None,
    ) -> str:
        """
        第二步：根据需求分析生成操作描述

        Args:
            user_requirement: 原始用户需求
            analysis_result: 第一步的分析结果
            table_schemas: 表结构信息
            previous_errors: 之前验证失败的错误列表（用于重试时提供上下文）
            previous_json: 之前生成的 JSON（用于重试时提供上下文）

        Returns:
            JSON 格式的操作描述
        """
        system_prompt = get_generation_prompt_with_context(
            table_schemas, analysis_result
        )

        # 构建用户消息，包含原始需求
        user_message = f"原始需求：{user_requirement}\n\n请根据上面的需求分析结果，生成 JSON 格式的操作描述。"

        # 如果有之前的错误，添加到用户消息中
        if previous_errors and previous_json:
            for err in previous_errors:
                if err.startswith("LLM_INTENTIONAL_REFUSAL:"):
                    refusal_reason = err.split("LLM_INTENTIONAL_REFUSAL:")[1].strip()
                    raise ValueError(refusal_reason)
            user_message += "\n\n---\n\n"
            user_message += "⚠️ 之前生成的 JSON 验证失败，请修正以下错误：\n\n"
            user_message += f"之前的 JSON：\n```json\n{previous_json}\n```\n\n"
            user_message += "验证错误：\n"
            for error in previous_errors:
                user_message += f"- {error}\n"
            user_message += "\n请根据错误信息修正 JSON，确保所有字段名、表名、列名都正确。"

        try:
            result = self._call_llm("generate", system_prompt, user_message)
            return self._clean_json_response(result)
        except Exception as e:
            raise RuntimeError(f"生成操作描述失败: {str(e)}") from e

    def generate_operations_stream(
        self,
        user_requirement: str,
        analysis_result: str,
        table_schemas: Optional[Dict[str, Dict[str, str]]] = None,
        previous_errors: Optional[List[str]] = None,
        previous_json: Optional[str] = None,
    ) -> Generator[Tuple[str, str], None, None]:
        """
        第二步：根据需求分析生成操作描述（流式输出，同步版本）

        Args:
            user_requirement: 原始用户需求
            analysis_result: 第一步的分析结果
            table_schemas: 表结构信息
            previous_errors: 之前验证失败的错误列表（用于重试时提供上下文）
            previous_json: 之前生成的 JSON（用于重试时提供上下文）

        Yields:
            Tuple[str, str]: (delta, full_content) - 增量内容和累积的完整内容
            最后一次 yield 的 full_content 会经过 _clean_json_response 清理
        """
        system_prompt = get_generation_prompt_with_context(
            table_schemas, analysis_result
        )

        def build_initial_user_message(
            query: str,
            table_schemas: Dict[str, Dict[str, str]],
        ) -> str:
            """
            构建初始用户消息（包含表结构信息）

            支持两种 schema 格式：
            1. 简单格式（旧）: {file_id: {sheet_name: {col_letter: col_name}}}
            2. 增强格式（新）: {file_id: {sheet_name: [{name, type, samples}, ...]}}
            """
            schema_text = "## 当前Excel文件以及表结构信息\n\n"

            # 两层结构：文件 -> sheets
            for file_id, file_sheets in table_schemas.items():
                schema_text += f"### 文件: {file_id}\n\n"
                for sheet_name, fields in file_sheets.items():
                    schema_text += f"#### Sheet: {sheet_name}\n"

                    # 检测 schema 格式
                    if isinstance(fields, list):
                        # 增强格式：包含类型和样本
                        schema_text += "| 列名 | 类型 | 样本数据 |\n"
                        schema_text += "|------|------|----------|\n"
                        for col_info in fields:
                            name = col_info.get("name", "")
                            col_type = col_info.get("type", "text")
                            samples = col_info.get("samples", [])
                            # 格式化样本数据
                            if samples:
                                samples_str = ", ".join(
                                    f'"{s}"' if isinstance(s, str) else str(s)
                                    for s in samples[:3]
                                )
                            else:
                                samples_str = "(空)"
                            schema_text += f"| {name} | {col_type} | {samples_str} |\n"
                    else:
                        # 简单格式（兼容旧代码）
                        field_list = ", ".join(fields.values())
                        schema_text += f"- columns: {field_list}\n"

                    schema_text += "\n"

            schema_text += "## 需求描述\n\n"
            schema_text += query

            return schema_text

        def build_error_feedback_message(errors: List[str]) -> str:
            """构建错误反馈消息"""
            feedback = "⚠️ 你生成的 JSON 验证失败，请修正以下错误：\n\n"
            for error in errors:
                feedback += f"- {error}\n"
            feedback += "\n请根据错误信息修正 JSON，确保所有字段名、表名、列名都正确。只输出修正后的 JSON。"
            return feedback

        # 构建消息列表
        initial_message = build_initial_user_message(user_requirement, table_schemas or {})

        if previous_errors and previous_json:
            for err in previous_errors:
                if err.startswith("LLM_INTENTIONAL_REFUSAL:"):
                    refusal_reason = err.split("LLM_INTENTIONAL_REFUSAL:")[1].strip()
                    raise ValueError(refusal_reason)
            messages = [
                {"role": "user", "content": initial_message},
                {"role": "assistant", "content": previous_json},
                {"role": "user", "content": build_error_feedback_message(previous_errors)}
            ]
            try:
                for delta, full_content in self._call_llm_stream("generate", system_prompt, messages=messages):
                    yield delta, full_content
            except Exception as e:
                raise RuntimeError(f"生成操作描述失败: {str(e)}") from e
        else:
            # 首次生成：单条用户消息
            try:
                for delta, full_content in self._call_llm_stream("generate", system_prompt, user_message=initial_message):
                    yield delta, full_content
            except Exception as e:
                raise RuntimeError(f"生成操作描述失败: {str(e)}") from e

    async def generate_operations_stream_async(
        self,
        user_requirement: str,
        analysis_result: str,
        table_schemas: Optional[Dict[str, Dict[str, str]]] = None
    ) -> AsyncGenerator[Tuple[str, str], None]:
        """
        第二步：根据需求分析生成操作描述（流式输出，异步版本）

        Args:
            user_requirement: 原始用户需求
            analysis_result: 第一步的分析结果
            table_schemas: 表结构信息

        Yields:
            Tuple[str, str]: (delta, full_content) - 增量内容和累积的完整内容
            注意：调用方需要在最后对 full_content 调用 _clean_json_response
        """
        system_prompt = get_generation_prompt_with_context(
            table_schemas, analysis_result
        )

        # 构建用户消息，包含原始需求
        user_message = f"原始需求：{user_requirement}\n\n请根据上面的需求分析结果，生成 JSON 格式的操作描述。"

        try:
            async for item in self._call_llm_stream_async("generate", system_prompt, user_message):
                yield item
            # 注意：调用方需要在最后对 full_content 调用 _clean_json_response
        except Exception as e:
            raise RuntimeError(f"生成操作描述失败: {str(e)}") from e

    # ==================== 数据分析 ====================

    def analyze(self, prompt: str) -> str:
        """
        数据分析：直接接收提示词并返回分析结果

        Args:
            prompt: 预构建的分析提示词

        Returns:
            LLM 分析结果（自然语言）
        """
        try:
            result = self._call_llm("analyze", prompt, None)
            return result
        except Exception as e:
            raise RuntimeError(f"数据分析失败: {str(e)}") from e

    def analyze_stream(self, prompt: str) -> Generator[Tuple[str, str], None, None]:
        """
        数据分析（流式输出，同步版本）

        Args:
            prompt: 预构建的分析提示词

        Yields:
            Tuple[str, str]: (delta, full_content) - 增量内容和累积的完整内容
        """
        try:
            yield from self._call_llm_stream("analyze", prompt, None)
        except Exception as e:
            raise RuntimeError(f"数据分析失败: {str(e)}") from e

    async def analyze_stream_async(self, prompt: str) -> AsyncGenerator[Tuple[str, str], None]:
        """
        数据分析（流式输出，异步版本）

        Args:
            prompt: 预构建的分析提示词

        Yields:
            Tuple[str, str]: (delta, full_content) - 增量内容和累积的完整内容
        """
        try:
            async for item in self._call_llm_stream_async("analyze", prompt):
                yield item
        except Exception as e:
            raise RuntimeError(f"数据分析失败: {str(e)}") from e

    # ==================== 辅助方法 ====================

    def _clean_json_response(self, content: str) -> str:
        """清理 LLM 响应中可能存在的 markdown 标记"""
        content = content.strip()

        if content.startswith("```json"):
            content = content[7:]
        elif content.startswith("```"):
            content = content[3:]

        if content.endswith("```"):
            content = content[:-3]

        return content.strip()


def create_llm_client(stage_configs: Dict[str, LLMStageConfig]) -> LLMClient:
    """创建 LLM 客户端的工厂函数"""
    return LLMClient(stage_configs=stage_configs)
