"""生成操作阶段"""

import json
import random
from typing import Any, Generator, TYPE_CHECKING

from ..types import ProcessStage, ProcessEvent, ProcessConfig
from .base import Stage
from .analyze import StageError

if TYPE_CHECKING:
    from app.engine.models import FileCollection
    from app.engine.llm_client import LLMClient


class GenerateStage(Stage):
    """
    生成操作阶段

    调用 LLM 生成 JSON 操作，基于前序的分析结果。

    输入:
        - tables: 表集合（用于获取 schema）
        - query: 用户查询
        - context["analyze"]: 分析结果
        - context["validation_errors"]: 验证失败的错误列表（重试时）
        - context["previous_json"]: 之前生成的 JSON（重试时）

    输出:
        {"operations": {...}, "operations_json": "..."}
    """

    stage = ProcessStage.GENERATE

    def __init__(self, llm_client: "LLMClient"):
        self.llm_client = llm_client

    def run(
        self,
        tables: "FileCollection",
        query: str,
        config: ProcessConfig,
        context: dict,
    ) -> Generator[ProcessEvent, None, Any]:
        """执行操作生成"""
        # 生成此阶段的唯一 ID
        stage_id = self._generate_stage_id()

        yield self._event_start(stage_id)

        # 使用增强的 schema（包含类型和样本数据）
        schemas = tables.get_schemas_with_samples(sample_count=3)
        analysis = context.get("analyze", {}).get("content", "")

        # 获取验证错误（如果是重试）
        validation_errors = context.get("validation_errors")
        previous_json = context.get("previous_json")

        try:
            # # 测试代码
            # if random.random() < 1:
            #     raise StageError(f"JSON 解析失败")
            if config.stream_llm:
                # 流式调用 - LLM 返回 (delta, full_content)
                operations_json = ""
                for delta, full_content in self.llm_client.generate_operations_stream(
                    query, analysis, schemas,
                    previous_errors=validation_errors,
                    previous_json=previous_json,
                ):
                    operations_json = full_content
                    yield self._event_stream(delta, stage_id)
                # 清理 JSON 响应（移除 markdown 标记）
                operations_json = self._clean_json_response(operations_json)
            else:
                # 非流式调用（内部已处理清理）
                operations_json = self.llm_client.generate_operations(
                    query, analysis, schemas,
                    previous_errors=validation_errors,
                    previous_json=previous_json,
                )

            # 解析 JSON
            try:
                operations = json.loads(operations_json)
            except json.JSONDecodeError as e:
                raise StageError(f"JSON 解析失败: {e}") from e

            output = {
                "operations": operations,
                "operations_json": operations_json,
            }
            yield self._event_done({"operations": operations}, stage_id)
            return output

        except StageError:
            raise
        except Exception as e:
            error_msg = f"生成操作失败: {e}"
            yield self._event_error(error_msg, stage_id)
            raise StageError(error_msg) from e

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
