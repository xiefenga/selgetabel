"""LLM 客户端模块 - 负责与 OpenAI API 交互，支持两步流程"""

import logging
import os
import asyncio
from typing import Optional, Dict, List, Generator, Tuple, AsyncGenerator
from openai import OpenAI
from app.engine.prompt import (
    get_analysis_prompt_with_schema,
    get_generation_prompt_with_context,
)
from app.engine.parser import parse_and_validate

logging.basicConfig(level=logging.INFO)

logger = logging.getLogger("llm_client")

logger.setLevel(logging.INFO)

class LLMClient:
    """LLM 客户端类，支持两步流程生成操作描述"""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None
    ):
        """
        初始化 LLM 客户端

        Args:
            api_key: OpenAI API Key
            base_url: OpenAI API Base URL
            model: 模型名称
        """
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.base_url = base_url or os.getenv("OPENAI_BASE_URL")
        self.model = model or os.getenv("OPENAI_MODEL")

        if not self.api_key:
            raise ValueError("未设置 OPENAI_API_KEY 环境变量")

        client_kwargs = {"api_key": self.api_key}
        if self.base_url:
            client_kwargs["base_url"] = self.base_url

        self.client = OpenAI(**client_kwargs)

    def _call_llm(self, system_prompt: str, user_message: str) -> str:
        """
        调用 LLM

        Args:
            system_prompt: 系统提示词
            user_message: 用户消息

        Returns:
            LLM 响应内容
        """

        log_msg = (
            "\n"
            "[LLM 调用] 非流式\n"
            f"[模型] {self.model}\n"
            "[System Prompt]\n"
            f"{system_prompt}\n"
            "[User Message]\n"
            f"{user_message}\n"
        )

        logger.info(log_msg)

        messages = [
            { "role": "system", "content": system_prompt },
            { "role": "user", "content": user_message }
        ]

        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=0,
            extra_body={
                "enable_thinking": False
            }
        )
        result = response.choices[0].message.content.strip()

        logger.info(f"\n[LLM 响应内容]\n{result}")

        return result

    def _call_llm_stream(
        self,
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
                {"role": "user", "content": user_message}
            ]

        # 打印提示词日志
        log_msg = (
            "\n"
            "[LLM 调用] 流式\n"
            f"[模型] {self.model}\n"
            f"[消息数] {len(full_messages)}\n"
            "[System Prompt]\n"
            f"{system_prompt}\n"
        )
        for i, msg in enumerate(full_messages[1:], 1):
            log_msg += f"[{msg['role'].upper()} #{i}]\n{msg['content']}\n"

        logger.info(log_msg)

        response = self.client.chat.completions.create(
            model=self.model,
            messages=full_messages,
            temperature=0,
            stream=True,
            extra_body={
                "enable_thinking": False
            }
        )

        full_content = ""
        for chunk in response:
            if chunk.choices and chunk.choices[0].delta.content:
                delta = chunk.choices[0].delta.content
                full_content += delta
                yield delta, full_content

        logger.info(f"\n[LLM 响应内容]\n{full_content}")

    async def _call_llm_stream_async(self, system_prompt: str, user_message: str) -> AsyncGenerator[Tuple[str, str], None]:
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
                for item in self._call_llm_stream(system_prompt, user_message):
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
            result = self._call_llm(system_prompt, user_requirement)
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
            yield from self._call_llm_stream(system_prompt, user_requirement)
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
            async for item in self._call_llm_stream_async(system_prompt, user_requirement):
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
            user_message += "\n\n---\n\n"
            user_message += "⚠️ 之前生成的 JSON 验证失败，请修正以下错误：\n\n"
            user_message += f"之前的 JSON：\n```json\n{previous_json}\n```\n\n"
            user_message += "验证错误：\n"
            for error in previous_errors:
                user_message += f"- {error}\n"
            user_message += "\n请根据错误信息修正 JSON，确保所有字段名、表名、列名都正确。"

        try:
            result = self._call_llm(system_prompt, user_message)
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
            # 重试场景：使用多轮对话形式
            messages = [
                {"role": "user", "content": initial_message},
                {"role": "assistant", "content": previous_json},
                {"role": "user", "content": build_error_feedback_message(previous_errors)}
            ]
            try:
                for delta, full_content in self._call_llm_stream(system_prompt, messages=messages):
                    yield delta, full_content
            except Exception as e:
                raise RuntimeError(f"生成操作描述失败: {str(e)}") from e
        else:
            # 首次生成：单条用户消息
            try:
                for delta, full_content in self._call_llm_stream(system_prompt, user_message=initial_message):
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
            async for item in self._call_llm_stream_async(system_prompt, user_message):
                yield item
            # 注意：调用方需要在最后对 full_content 调用 _clean_json_response
        except Exception as e:
            raise RuntimeError(f"生成操作描述失败: {str(e)}") from e

    # ==================== 完整两步流程 ====================

    def process_requirement(
        self,
        user_requirement: str,
        table_schemas: Optional[Dict[str, Dict[str, str]]] = None,
        available_tables: Optional[List[str]] = None
    ) -> Dict:
        """
        完整的两步处理流程

        Args:
            user_requirement: 用户需求
            table_schemas: 表结构信息
            available_tables: 可用的表名列表

        Returns:
            {
                "analysis": str,           # 需求分析结果
                "json_str": str,           # 生成的 JSON
                "operations": List[Operation],  # 解析后的操作列表
                "errors": List[str]        # 错误列表
            }
        """
        result = {
            "analysis": None,
            "json_str": None,
            "operations": [],
            "errors": []
        }

        # 第一步：需求分析
        try:
            analysis = self.analyze_requirement(user_requirement, table_schemas)
            result["analysis"] = analysis
        except Exception as e:
            result["errors"].append(f"需求分析失败: {str(e)}")
            return result

        # 第二步：生成操作描述
        try:
            json_str = self.generate_operations(
                user_requirement, analysis, table_schemas
            )
            result["json_str"] = json_str
        except Exception as e:
            result["errors"].append(f"生成操作失败: {str(e)}")
            return result

        # 第三步：解析和验证
        if available_tables is None and table_schemas:
            available_tables = list(table_schemas.keys())

        operations, parse_errors = parse_and_validate(
            json_str, available_tables or []
        )

        result["operations"] = operations
        result["errors"].extend(parse_errors)

        return result

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


def create_llm_client() -> LLMClient:
    """创建 LLM 客户端的工厂函数"""
    return LLMClient()
