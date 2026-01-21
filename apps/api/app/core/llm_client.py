"""LLM 客户端模块 - 负责与 OpenAI API 交互，支持两步流程"""

import os
from typing import Optional, Dict, List
from openai import OpenAI
from app.core.prompt import (
    get_analysis_prompt_with_schema,
    get_generation_prompt_with_context,
)
from app.core.parser import parse_and_validate


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

        self.enable_thinking = os.getenv(
            "OPENAI_ENABLE_THINKING", "false"
        ).lower() == "true"

    def _call_llm(self, system_prompt: str, user_message: str) -> str:
        """
        调用 LLM

        Args:
            system_prompt: 系统提示词
            user_message: 用户消息

        Returns:
            LLM 响应内容
        """

        print(system_prompt)
        request_params = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ],
            "temperature": 0,
            "max_tokens": 4000,
            "stream": False,
        }

        if not self.enable_thinking:
            request_params["extra_body"] = {"enable_thinking": False}

        response = self.client.chat.completions.create(**request_params)
        return response.choices[0].message.content.strip()

    # ==================== 第一步：需求分析 ====================

    def analyze_requirement(
        self,
        user_requirement: str,
        table_schemas: Optional[Dict[str, Dict[str, str]]] = None
    ) -> str:
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

    # ==================== 第二步：生成操作描述 ====================

    def generate_operations(
        self,
        user_requirement: str,
        analysis_result: str,
        table_schemas: Optional[Dict[str, Dict[str, str]]] = None
    ) -> str:
        """
        第二步：根据需求分析生成操作描述

        Args:
            user_requirement: 原始用户需求
            analysis_result: 第一步的分析结果
            table_schemas: 表结构信息

        Returns:
            JSON 格式的操作描述
        """
        system_prompt = get_generation_prompt_with_context(
            table_schemas, analysis_result
        )

        # 构建用户消息，包含原始需求
        user_message = f"原始需求：{user_requirement}\n\n请根据上面的需求分析结果，生成 JSON 格式的操作描述。"

        try:
            result = self._call_llm(system_prompt, user_message)
            return self._clean_json_response(result)
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
