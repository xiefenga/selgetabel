"""需求分析阶段"""

from typing import Any, Generator, TYPE_CHECKING

from ..types import ProcessStage, ProcessEvent, ProcessConfig
from .base import Stage

if TYPE_CHECKING:
    from app.engine.models import FileCollection
    from app.engine.llm_client import LLMClient


class StageError(Exception):
    """阶段执行错误"""

    pass


class AnalyzeStage(Stage):
    """
    需求分析阶段

    调用 LLM 分析用户需求，输出分析结果。

    输入:
        - tables: 表集合（用于获取 schema）
        - query: 用户查询

    输出:
        {"content": "分析结果文本"}
    """

    stage = ProcessStage.ANALYZE

    def __init__(self, llm_client: "LLMClient"):
        self.llm_client = llm_client

    def run(
        self,
        tables: "FileCollection",
        query: str,
        config: ProcessConfig,
        context: dict,
    ) -> Generator[ProcessEvent, None, Any]:
        """执行需求分析"""
        # 生成此阶段的唯一 ID
        stage_id = self._generate_stage_id()

        yield self._event_start(stage_id)

        # 使用增强的 schema（包含类型和样本数据）
        schemas = tables.get_schemas_with_samples(sample_count=3)

        try:
            if config.stream_llm:
                # 流式调用 - LLM 返回 (delta, full_content)
                analysis = ""
                for delta, full_content in self.llm_client.analyze_requirement_stream(
                    query, schemas
                ):
                    analysis = full_content
                    yield self._event_stream(delta, stage_id)
            else:
                # 非流式调用
                analysis = self.llm_client.analyze_requirement(query, schemas)

            output = {"content": analysis}
            yield self._event_done(output, stage_id)
            return output

        except Exception as e:
            error_msg = f"分析失败: {e}"
            yield self._event_error(error_msg, stage_id)
            raise StageError(error_msg) from e
