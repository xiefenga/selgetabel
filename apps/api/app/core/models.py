"""数据模型 - 定义系统中的基础数据类型"""

from typing import Union, List, Dict, Any, Optional
from dataclasses import dataclass, field
import pandas as pd


# ==================== 辅助函数 ====================


def column_index_to_letter(index: int) -> str:
    """
    将列索引转换为 Excel 列标识

    Args:
        index: 列索引（从 0 开始）

    Returns:
        Excel 列标识（A, B, ..., Z, AA, AB, ...）
    """
    result = ""
    index += 1
    while index > 0:
        index -= 1
        result = chr(65 + (index % 26)) + result
        index //= 26
    return result


# ==================== Excel 错误类型 ====================


class ExcelError(Exception):
    """Excel 错误值"""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)

    def __repr__(self):
        return self.code

    def __str__(self):
        return self.code

    def __eq__(self, other):
        if isinstance(other, ExcelError):
            return self.code == other.code
        return False

    def __hash__(self):
        return hash(self.code)


# 预定义 Excel 错误
NA = ExcelError("#N/A")
DIV0 = ExcelError("#DIV/0!")
VALUE = ExcelError("#VALUE!")
REF = ExcelError("#REF!")


# ==================== 基础类型定义 ====================

Number = Union[int, float]
Text = str
Cell = Union[Number, Text, None, ExcelError]
Range = List[Cell]


# ==================== 操作定义 ====================


@dataclass
class AggregateOperation:
    """整列聚合操作"""

    function: str
    table: str
    column: Optional[str] = None
    condition_column: Optional[str] = None
    condition: Optional[Union[str, int, float]] = None
    as_var: str = ""

    def __post_init__(self):
        # 验证函数名
        valid_functions = {
            "SUM", "COUNT", "COUNTA", "AVERAGE", "MIN", "MAX",
            "SUMIF", "COUNTIF", "AVERAGEIF"
        }
        if self.function not in valid_functions:
            raise ValueError(f"不支持的聚合函数: {self.function}")


@dataclass
class AddColumnOperation:
    """新增计算列操作"""

    table: str
    name: str
    formula: Union[str, Dict[str, Any]]  # 支持字符串（旧格式）或 JSON 对象（新格式）


@dataclass
class ComputeOperation:
    """标量运算操作"""

    expression: Union[str, Dict[str, Any]]  # 支持字符串或 JSON 对象
    as_var: str = ""


# 操作类型联合
Operation = Union[AggregateOperation, AddColumnOperation, ComputeOperation]


@dataclass
class OperationResult:
    """操作执行结果"""

    operation: Operation
    value: Any = None
    excel_formula: str = ""
    error: Optional[str] = None


@dataclass
class ExecutionResult:
    """执行结果汇总"""

    # 变量上下文（存储中间计算结果）
    variables: Dict[str, Any] = field(default_factory=dict)

    # 新增的列数据
    new_columns: Dict[str, Dict[str, List[Any]]] = field(default_factory=dict)

    # 每个操作的结果
    operation_results: List[OperationResult] = field(default_factory=list)

    # Excel 公式列表
    excel_formulas: List[str] = field(default_factory=list)

    # 错误信息
    errors: List[str] = field(default_factory=list)

    def add_variable(self, name: str, value: Any):
        """添加变量"""
        self.variables[name] = value

    def add_column(self, table: str, column_name: str, values: List[Any]):
        """添加新列"""
        if table not in self.new_columns:
            self.new_columns[table] = {}
        self.new_columns[table][column_name] = values

    def add_formula(self, formula: str):
        """添加 Excel 公式"""
        self.excel_formulas.append(formula)

    def add_error(self, error: str):
        """添加错误"""
        self.errors.append(error)

    def has_errors(self) -> bool:
        """是否有错误"""
        return len(self.errors) > 0


# ==================== 表数据结构 ====================


class Table:
    """表数据结构 - 封装 pandas DataFrame"""

    def __init__(self, name: str, data: pd.DataFrame):
        self.name = name
        self._data = data
        self._columns = list(data.columns)

    def __getattr__(self, column_name: str) -> Range:
        """通过属性访问列数据"""
        if column_name.startswith('_'):
            raise AttributeError(
                f"'{type(self).__name__}' object has no attribute '{column_name}'"
            )

        if column_name in self._data.columns:
            return self._data[column_name].tolist()

        raise AttributeError(f"表 '{self.name}' 没有字段 '{column_name}'")

    def get_column(self, column_name: str) -> Range:
        """获取列数据"""
        if column_name not in self._data.columns:
            raise ValueError(f"表 '{self.name}' 没有字段 '{column_name}'")
        return self._data[column_name].tolist()

    def get_columns(self) -> List[str]:
        """获取所有列名"""
        return self._columns.copy()

    def get_column_index(self, column_name: str) -> int:
        """获取列索引"""
        if column_name not in self._columns:
            raise ValueError(f"表 '{self.name}' 没有字段 '{column_name}'")
        return self._columns.index(column_name)

    def get_column_letter(self, column_name: str) -> str:
        """获取列的 Excel 列标识"""
        index = self.get_column_index(column_name)
        return column_index_to_letter(index)

    def get_data(self) -> pd.DataFrame:
        """获取原始 DataFrame"""
        return self._data.copy()

    def row_count(self) -> int:
        """获取行数"""
        return len(self._data)

    def add_column(self, column_name: str, values: List[Any]):
        """添加新列"""
        if len(values) != len(self._data):
            raise ValueError(
                f"新列数据长度 ({len(values)}) 与表行数 ({len(self._data)}) 不匹配"
            )
        self._data[column_name] = values
        self._columns.append(column_name)

    def __repr__(self):
        return f"Table(name='{self.name}', columns={self._columns}, rows={len(self._data)})"

    def __len__(self):
        return len(self._data)


# ==================== 表集合 ====================


class TableCollection:
    """表集合 - 管理多个表"""

    def __init__(self):
        self._tables: Dict[str, Table] = {}

    def add_table(self, table: Table):
        """添加一个表"""
        self._tables[table.name] = table

    def get_table(self, name: str) -> Table:
        """获取指定名称的表"""
        if name not in self._tables:
            raise ValueError(f"表 '{name}' 不存在")
        return self._tables[name]

    def has_table(self, name: str) -> bool:
        """检查表是否存在"""
        return name in self._tables

    def __getattr__(self, table_name: str) -> Table:
        """通过属性访问表"""
        if table_name.startswith('_'):
            raise AttributeError(
                f"'{type(self).__name__}' object has no attribute '{table_name}'"
            )

        if table_name in self._tables:
            return self._tables[table_name]

        raise AttributeError(f"表 '{table_name}' 不存在")

    def get_table_names(self) -> List[str]:
        """获取所有表名"""
        return list(self._tables.keys())

    def get_schemas(self) -> Dict[str, Dict[str, str]]:
        """获取所有表的结构信息"""
        schemas = {}
        for name, table in self._tables.items():
            columns = table.get_columns()
            schemas[name] = {
                column_index_to_letter(i): col_name
                for i, col_name in enumerate(columns)
            }
        return schemas

    def get_column_mapping(self) -> Dict[str, Dict[str, str]]:
        """
        获取列名到 Excel 列标识的映射

        Returns:
            {"表名": {"列名": "A", ...}, ...}
        """
        mapping = {}
        for name, table in self._tables.items():
            columns = table.get_columns()
            mapping[name] = {
                col_name: column_index_to_letter(i)
                for i, col_name in enumerate(columns)
            }
        return mapping

    def __repr__(self):
        return f"TableCollection(tables={list(self._tables.keys())})"

    def __iter__(self):
        return iter(self._tables.values())

    def export_to_excel(self, output_path: str, tables_to_export: List[str] = None):
        """
        导出表到 Excel 文件

        Args:
            output_path: 输出文件路径
            tables_to_export: 要导出的表名列表，None 表示导出所有表
        """
        if tables_to_export is None:
            tables_to_export = self.get_table_names()

        with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
            for table_name in tables_to_export:
                if table_name in self._tables:
                    table = self._tables[table_name]
                    # 截取 sheet 名称（Excel 限制 31 字符）
                    sheet_name = table_name[:31] if len(table_name) > 31 else table_name
                    table.get_data().to_excel(writer, sheet_name=sheet_name, index=False)

    def apply_new_columns(self, new_columns: Dict[str, Dict[str, List[Any]]]):
        """
        将新增列应用到表中

        Args:
            new_columns: 新增列数据 {表名: {列名: [值列表]}}
        """
        for table_name, columns in new_columns.items():
            if table_name in self._tables:
                table = self._tables[table_name]
                for col_name, values in columns.items():
                    table.add_column(col_name, values)
