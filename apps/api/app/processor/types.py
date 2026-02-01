"""处理器类型定义"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from app.engine.models import FileCollection


class ProcessStage(str, Enum):
    """处理阶段"""

    ANALYZE = "analyze"  # LLM 需求分析
    GENERATE = "generate"  # LLM 生成操作
    VALIDATE = "validate"  # 验证操作
    EXECUTE = "execute"  # 执行操作


class EventType(str, Enum):
    """事件类型"""

    STAGE_START = "start"  # 阶段开始
    STAGE_STREAM = "stream"  # 流式增量（仅 stream_llm=True）
    STAGE_DONE = "done"  # 阶段完成
    STAGE_ERROR = "error"  # 阶段错误


@dataclass
class ProcessEvent:
    """
    处理事件 - 统一的中间过程输出格式

    不管是 Chat SSE 还是 Fixture 测试，都通过这个结构获取中间结果。

    Attributes:
        stage: 当前处理阶段
        event_type: 事件类型
        stage_id: 阶段实例的唯一标识（同一阶段重试时会生成新 id）
        output: 阶段输出（STAGE_DONE 时有值）
        delta: 流式增量（STAGE_STREAM 时有值）
        error: 错误信息（STAGE_ERROR 时有值）
    """

    stage: ProcessStage
    event_type: EventType
    stage_id: Optional[str] = None  # 阶段实例 ID（uuid）
    output: Optional[Any] = None
    delta: Optional[str] = None
    error: Optional[str] = None

    def to_dict(self) -> dict:
        """转换为字典"""
        result = {
            "stage": self.stage.value,
            "type": self.event_type.value,
        }
        if self.stage_id is not None:
            result["stage_id"] = self.stage_id
        if self.output is not None:
            result["output"] = self.output
        if self.delta is not None:
            result["delta"] = self.delta
        if self.error is not None:
            result["error"] = self.error
        return result

    def __repr__(self) -> str:
        parts = [f"stage={self.stage.value}", f"type={self.event_type.value}"]
        if self.stage_id is not None:
            parts.append(f"stage_id={self.stage_id[:8]}...")
        if self.output is not None:
            output_str = str(self.output)
            if len(output_str) > 50:
                output_str = output_str[:50] + "..."
            parts.append(f"output={output_str}")
        if self.delta is not None:
            parts.append(f"delta={self.delta[:20]}...")
        if self.error is not None:
            parts.append(f"error={self.error}")
        return f"ProcessEvent({', '.join(parts)})"


@dataclass
class ProcessConfig:
    """
    处理配置

    Attributes:
        stream_llm: LLM 调用是否使用流式模式
        max_validation_retries: 验证失败后最大重试次数（重新生成操作）
    """

    stream_llm: bool = False
    max_validation_retries: int = 2


@dataclass
class ProcessResult:
    """
    处理结果 - 最终输出

    Attributes:
        analysis: 需求分析结果（LLM 输出）
        operations: 生成的操作（JSON 结构）
        formulas: Excel 公式（格式化后的字符串）
        variables: 聚合变量结果
        new_columns: 新增列数据（预览，前 10 行）
        updated_columns: 更新列数据（预览，前 10 行）
        new_sheets: 新创建的 Sheet（预览信息）
        modified_tables: 修改后的表集合（用于导出）
        errors: 错误列表
    """

    # 各阶段输出
    analysis: Optional[str] = None
    operations: Optional[Dict] = None
    formulas: Optional[str] = None

    # 执行结果
    variables: Dict[str, Any] = field(default_factory=dict)
    new_columns: Dict[str, Dict[str, Dict[str, List]]] = field(default_factory=dict)
    updated_columns: Dict[str, Dict[str, Dict[str, List]]] = field(default_factory=dict)
    new_sheets: Dict[str, Dict[str, Dict]] = field(default_factory=dict)
    modified_tables: Optional["FileCollection"] = None

    # 错误
    errors: List[str] = field(default_factory=list)

    def has_errors(self) -> bool:
        """是否有错误"""
        return len(self.errors) > 0

    def get_modified_file_ids(self) -> List[str]:
        """
        获取被修改的文件 ID 列表

        修改的定义：
        - 新增了列（new_columns）
        - 更新了列（updated_columns）
        - 新增了 Sheet（new_sheets）

        Returns:
            被修改的文件 ID 列表（去重）
        """
        modified_ids = set()

        # 收集所有有变动的 file_id
        for file_id in self.new_columns.keys():
            modified_ids.add(file_id)
        for file_id in self.updated_columns.keys():
            modified_ids.add(file_id)
        for file_id in self.new_sheets.keys():
            modified_ids.add(file_id)

        return list(modified_ids)

    def to_dict(self) -> dict:
        """转换为字典（用于序列化）"""
        return {
            "analysis": self.analysis,
            "operations": self.operations,
            "formulas": self.formulas,
            "variables": self.variables if self.variables else None,
            "new_columns": self.new_columns if self.new_columns else None,
            "updated_columns": self.updated_columns if self.updated_columns else None,
            "new_sheets": self.new_sheets if self.new_sheets else None,
            "errors": self.errors if self.errors else None,
        }

    def __repr__(self) -> str:
        parts = []
        if self.analysis:
            parts.append(f"analysis={len(self.analysis)} chars")
        if self.operations:
            parts.append(f"operations={len(self.operations.get('operations', []))} ops")
        if self.formulas:
            parts.append("formulas=yes")
        if self.errors:
            parts.append(f"errors={len(self.errors)}")
        return f"ProcessResult({', '.join(parts)})"
