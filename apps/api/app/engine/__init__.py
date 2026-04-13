"""Excel 处理引擎 - Layer 3 Core 核心函数模块

包含 Excel LLM 系统的核心处理逻辑：
- parser: JSON 操作解析器
- executor: 操作执行引擎（ExcelExecutor 类）
- excel_generator: Excel 公式生成器
- excel_parser: Excel 文件解析器
- functions: Excel 函数实现
- models: 数据模型定义
- step_tracker: 步骤追踪器（仍由 turn_repository 使用）
"""

from app.engine.models import (
    ExcelError,
    NA,
    DIV0,
    VALUE,
    REF,
    Table,
    ExcelFile,
    FileCollection,
    AggregateOperation,
    AddColumnOperation,
    ComputeOperation,
    Operation,
    OperationResult,
    ExecutionResult,
)
from app.engine.parser import parse_operations, parse_and_validate
from app.engine.executor import ExcelExecutor
from app.engine.excel_parser import ExcelParser
from app.engine.step_tracker import StepTracker

__all__ = [
    # Models
    "ExcelError",
    "NA",
    "DIV0",
    "VALUE",
    "REF",
    "Table",
    "ExcelFile",
    "FileCollection",
    "AggregateOperation",
    "AddColumnOperation",
    "ComputeOperation",
    "Operation",
    "OperationResult",
    "ExecutionResult",
    # Parser（仍由 turn_repository 解析 steps JSON 使用）
    "parse_operations",
    "parse_and_validate",
    # Executor
    "ExcelExecutor",
    # Excel Parser
    "ExcelParser",
    # Step Tracker
    "StepTracker",
]
