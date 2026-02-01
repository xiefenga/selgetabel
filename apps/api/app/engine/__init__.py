"""Excel 处理引擎 - Layer 3 Core 核心函数模块

包含 LLM Excel 系统的核心处理逻辑：
- llm_client: LLM 客户端（analyze, generate）
- parser: JSON 操作解析器
- executor: 操作执行引擎
- excel_generator: Excel 公式生成器
- excel_parser: Excel 文件解析器
- functions: Excel 函数实现
- prompt: LLM 提示词
- models: 数据模型定义
- step_tracker: 步骤追踪器
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
from app.engine.executor import execute_operations
from app.engine.excel_generator import generate_formulas, format_formula_output
from app.engine.excel_parser import ExcelParser
from app.engine.llm_client import LLMClient, create_llm_client
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
    # Parser
    "parse_operations",
    "parse_and_validate",
    # Executor
    "execute_operations",
    # Excel Generator
    "generate_formulas",
    "format_formula_output",
    # Excel Parser
    "ExcelParser",
    # LLM Client
    "LLMClient",
    "create_llm_client",
    # Step Tracker
    "StepTracker",
]
