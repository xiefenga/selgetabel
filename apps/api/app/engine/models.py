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
    file_id: str  # 文件 ID
    table: str    # sheet 名称
    column: Optional[str] = None
    condition_column: Optional[str] = None
    condition: Optional[Union[str, int, float]] = None
    as_var: str = ""
    description: Optional[str] = None  # LLM 生成的自然语言描述

    def __post_init__(self):
        # 验证函数名
        valid_functions = {
            "SUM", "COUNT", "COUNTA", "AVERAGE", "MIN", "MAX", "MEDIAN",
            "SUMIF", "COUNTIF", "AVERAGEIF"
        }
        if self.function not in valid_functions:
            raise ValueError(f"不支持的聚合函数: {self.function}")


@dataclass
class AddColumnOperation:
    """新增计算列操作"""

    file_id: str  # 文件 ID
    table: str    # sheet 名称
    name: str
    formula: Union[str, Dict[str, Any]]  # 支持字符串（旧格式）或 JSON 对象（新格式）
    description: Optional[str] = None  # LLM 生成的自然语言描述


@dataclass
class UpdateColumnOperation:
    """更新现有列操作"""

    file_id: str  # 文件 ID
    table: str    # sheet 名称
    column: str   # 要更新的列名
    formula: Union[str, Dict[str, Any]]  # 计算公式
    description: Optional[str] = None  # LLM 生成的自然语言描述


@dataclass
class ComputeOperation:
    """标量运算操作"""

    expression: Union[str, Dict[str, Any]]  # 支持字符串或 JSON 对象
    as_var: str = ""
    description: Optional[str] = None  # LLM 生成的自然语言描述


# ==================== 新增操作类型（Excel 365+）====================


@dataclass
class FilterCondition:
    """筛选条件"""
    column: str
    op: str  # =, <>, >, <, >=, <=, contains
    value: Any


@dataclass
class OutputTarget:
    """输出目标"""
    type: str  # "new_sheet" 或 "in_place" 或 "replace"
    name: Optional[str] = None  # 新 Sheet 名称


@dataclass
class FilterOperation:
    """
    筛选操作（Excel 365+ FILTER 函数）

    按条件筛选行，结果可输出到新 Sheet 或原地替换
    """
    file_id: str
    table: str
    conditions: List[Dict[str, Any]]  # [{"column": "Sex", "op": "=", "value": "female"}, ...]
    output: Dict[str, Any]  # {"type": "new_sheet", "name": "结果表"}
    logic: str = "AND"  # "AND" 或 "OR"
    description: Optional[str] = None

    def __post_init__(self):
        if self.logic not in {"AND", "OR"}:
            raise ValueError(f"logic 必须是 'AND' 或 'OR'，收到: {self.logic}")


@dataclass
class SortRule:
    """排序规则"""
    column: str
    order: str = "asc"  # "asc" 或 "desc"


@dataclass
class SortOperation:
    """
    排序操作（Excel 365+ SORT 函数）

    按一列或多列排序，支持升序/降序
    """
    file_id: str
    table: str
    by: List[Dict[str, Any]]  # [{"column": "Age", "order": "desc"}, ...]
    output: Optional[Dict[str, Any]] = None  # 默认 in_place
    description: Optional[str] = None

    def __post_init__(self):
        if self.output is None:
            self.output = {"type": "in_place"}
        for rule in self.by:
            if rule.get("order", "asc") not in {"asc", "desc"}:
                raise ValueError(f"order 必须是 'asc' 或 'desc'")


@dataclass
class GroupByAggregation:
    """分组聚合定义"""
    column: str
    function: str  # SUM, COUNT, AVERAGE, MIN, MAX
    as_name: str


@dataclass
class GroupByOperation:
    """
    分组聚合操作（Excel 365+ GROUPBY 函数）

    按分组列聚合计算，生成汇总表
    """
    file_id: str
    table: str
    group_columns: List[str]  # 分组列
    aggregations: List[Dict[str, Any]]  # [{"column": "Fare", "function": "AVERAGE", "as": "Average_Fare"}, ...]
    output: Dict[str, Any]  # {"type": "new_sheet", "name": "统计表"}
    description: Optional[str] = None

    def __post_init__(self):
        valid_functions = {"SUM", "COUNT", "AVERAGE", "MIN", "MAX", "MEDIAN"}
        for agg in self.aggregations:
            func = agg.get("function", "").upper()
            if func not in valid_functions:
                raise ValueError(f"不支持的聚合函数: {func}")


@dataclass
class CreateSheetOperation:
    """
    创建新 Sheet 操作（内部抽象，无 Excel 函数对应）

    用于显式创建新 Sheet，通常由 filter/sort/group_by 隐式触发
    """
    file_id: str
    name: str  # 新 Sheet 名称
    source: Optional[Dict[str, Any]] = None  # {"type": "empty"} 或 {"type": "copy", "table": "源表"}
    columns: Optional[List[str]] = None  # 列定义（empty 时使用）
    description: Optional[str] = None

    def __post_init__(self):
        if self.source is None:
            self.source = {"type": "empty"}
        source_type = self.source.get("type", "empty")
        if source_type not in {"empty", "copy", "reference"}:
            raise ValueError(f"source.type 必须是 'empty', 'copy' 或 'reference'")


@dataclass
class TakeOperation:
    """
    取前/后 N 行操作（Excel 365+ TAKE 函数）

    从表的开头或末尾提取指定数量的行。
    - rows > 0: 从开头取 N 行
    - rows < 0: 从末尾取 N 行
    """
    file_id: str
    table: str
    rows: int  # 正数取前N行，负数取后N行
    output: Optional[Dict[str, Any]] = None  # {"type": "new_sheet", "name": "..."} 或 {"type": "in_place"}
    description: Optional[str] = None

    def __post_init__(self):
        if self.output is None:
            self.output = {"type": "in_place"}
        if self.rows == 0:
            raise ValueError("rows 不能为 0")


# 操作类型联合
Operation = Union[
    AggregateOperation,
    AddColumnOperation,
    UpdateColumnOperation,
    ComputeOperation,
    FilterOperation,
    SortOperation,
    GroupByOperation,
    CreateSheetOperation,
    TakeOperation
]


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

    # 新增的列数据（三层结构：file_id -> sheet_name -> column_name -> values）
    new_columns: Dict[str, Dict[str, Dict[str, List[Any]]]] = field(default_factory=dict)

    # 更新的列数据（三层结构：file_id -> sheet_name -> column_name -> values）
    updated_columns: Dict[str, Dict[str, Dict[str, List[Any]]]] = field(default_factory=dict)

    # 新创建的 Sheet（三层结构：file_id -> sheet_name -> DataFrame 数据）
    new_sheets: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    # 每个操作的结果
    operation_results: List[OperationResult] = field(default_factory=list)

    # Excel 公式列表
    excel_formulas: List[str] = field(default_factory=list)

    # 错误信息
    errors: List[str] = field(default_factory=list)

    def add_variable(self, name: str, value: Any):
        """添加变量"""
        self.variables[name] = value

    def add_column(self, file_id: str, sheet_name: str, column_name: str, values: List[Any]):
        """添加新列（三层结构）"""
        if file_id not in self.new_columns:
            self.new_columns[file_id] = {}
        if sheet_name not in self.new_columns[file_id]:
            self.new_columns[file_id][sheet_name] = {}
        self.new_columns[file_id][sheet_name][column_name] = values

    def add_updated_column(self, file_id: str, sheet_name: str, column_name: str, values: List[Any]):
        """添加更新列（三层结构）"""
        if file_id not in self.updated_columns:
            self.updated_columns[file_id] = {}
        if sheet_name not in self.updated_columns[file_id]:
            self.updated_columns[file_id][sheet_name] = {}
        self.updated_columns[file_id][sheet_name][column_name] = values

    def add_new_sheet(self, file_id: str, sheet_name: str, data: pd.DataFrame):
        """添加新创建的 Sheet"""
        if file_id not in self.new_sheets:
            self.new_sheets[file_id] = {}
        self.new_sheets[file_id][sheet_name] = data

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
        """
        添加新列

        Args:
            column_name: 列名
            values: 列数据

        Raises:
            ValueError: 如果列名已存在或数据长度不匹配
        """
        if column_name in self._columns:
            raise ValueError(
                f"列 '{column_name}' 已存在，请使用 update_column 更新现有列"
            )
        if len(values) != len(self._data):
            raise ValueError(
                f"新列数据长度 ({len(values)}) 与表行数 ({len(self._data)}) 不匹配"
            )
        self._data[column_name] = values
        self._columns.append(column_name)

    def update_column(self, column_name: str, values: List[Any]):
        """
        更新现有列

        Args:
            column_name: 列名
            values: 列数据

        Raises:
            ValueError: 如果列名不存在或数据长度不匹配
        """
        if column_name not in self._columns:
            raise ValueError(
                f"列 '{column_name}' 不存在，请使用 add_column 添加新列"
            )
        if len(values) != len(self._data):
            raise ValueError(
                f"新列数据长度 ({len(values)}) 与表行数 ({len(self._data)}) 不匹配"
            )
        self._data[column_name] = values

    def __repr__(self):
        return f"Table(name='{self.name}', columns={self._columns}, rows={len(self._data)})"

    def __len__(self):
        return len(self._data)


# ==================== Excel 文件结构 ====================


class ExcelFile:
    """Excel 文件 - 封装一个 Excel 文件及其包含的所有 sheets"""

    def __init__(self, file_id: str, filename: str):
        """
        初始化 Excel 文件

        Args:
            file_id: 文件 ID（UUID 字符串）
            filename: 原始文件名（如 "orders.xlsx"）
        """
        self.file_id = file_id
        self.filename = filename
        self._sheets: Dict[str, Table] = {}

    def add_sheet(self, sheet: Table):
        """添加一个 sheet"""
        self._sheets[sheet.name] = sheet

    def get_sheet(self, sheet_name: str) -> Table:
        """获取指定 sheet"""
        if sheet_name not in self._sheets:
            raise ValueError(f"Sheet '{sheet_name}' 不存在于文件 {self.filename}")
        return self._sheets[sheet_name]

    def has_sheet(self, sheet_name: str) -> bool:
        """检查 sheet 是否存在"""
        return sheet_name in self._sheets

    def get_sheet_names(self) -> List[str]:
        """获取所有 sheet 名称"""
        return list(self._sheets.keys())

    def get_schema(self) -> Dict[str, Dict[str, str]]:
        """
        获取本文件所有 sheet 的结构

        Returns:
            {"sheet_name": {"A": "列名1", "B": "列名2", ...}, ...}
        """
        schema = {}
        for sheet_name, table in self._sheets.items():
            columns = table.get_columns()
            schema[sheet_name] = {
                column_index_to_letter(i): col_name
                for i, col_name in enumerate(columns)
            }
        return schema

    def __repr__(self):
        return f"ExcelFile(file_id='{self.file_id}', filename='{self.filename}', sheets={list(self._sheets.keys())})"

    def __len__(self):
        """返回 sheet 数量"""
        return len(self._sheets)


# ==================== 文件集合 ====================


class FileCollection:
    """文件集合 - 管理多个 ExcelFile（两层结构：文件 → sheet）"""

    def __init__(self):
        self._files: Dict[str, ExcelFile] = {}

    def add_file(self, excel_file: ExcelFile):
        """添加一个 Excel 文件"""
        self._files[excel_file.file_id] = excel_file

    def get_file(self, file_id: str) -> ExcelFile:
        """获取指定文件"""
        if file_id not in self._files:
            raise ValueError(f"文件不存在: {file_id}")
        return self._files[file_id]

    def has_file(self, file_id: str) -> bool:
        """检查文件是否存在"""
        return file_id in self._files

    def get_table(self, file_id: str, sheet_name: str) -> Table:
        """
        获取指定表（两层访问）

        Args:
            file_id: 文件 ID
            sheet_name: sheet 名称

        Returns:
            Table 对象
        """
        return self.get_file(file_id).get_sheet(sheet_name)

    def get_file_ids(self) -> List[str]:
        """获取所有文件 ID"""
        return list(self._files.keys())

    def get_schemas(self) -> Dict[str, Dict[str, Dict[str, str]]]:
        """
        获取所有表的结构信息（两层）

        Returns:
            {
                "file_id_1": {
                    "sheet1": {"A": "列1", "B": "列2"},
                    "sheet2": {...}
                },
                "file_id_2": {...}
            }
        """
        schemas = {}
        for file_id, excel_file in self._files.items():
            schemas[file_id] = excel_file.get_schema()
        return schemas

    def get_schemas_with_samples(self, sample_count: int = 3) -> Dict[str, Dict[str, List[Dict[str, Any]]]]:
        """
        获取增强的表结构信息（包含类型和样本数据）

        Args:
            sample_count: 每列采样的数据条数

        Returns:
            {
                "file_id_1": {
                    "sheet1": [
                        {"name": "列1", "type": "number", "samples": [100, 200, 300]},
                        {"name": "列2", "type": "text", "samples": ["a", "b", "c"]},
                        ...
                    ],
                    "sheet2": [...]
                },
                "file_id_2": {...}
            }

        类型映射：
            - int64, float64 -> "number"
            - object (主要是数值) -> "number"
            - object (主要是文本) -> "text"
            - object (混合) -> "mixed"
            - datetime64 -> "date"
            - bool -> "boolean"
        """
        import math

        def detect_column_type(series: pd.Series) -> str:
            """检测列的实际类型"""
            dtype = str(series.dtype).lower()

            # 数值类型
            if "int" in dtype or "float" in dtype:
                return "number"

            # 日期时间类型
            if "datetime" in dtype or "date" in dtype:
                return "date"

            # 布尔类型
            if "bool" in dtype:
                return "boolean"

            # object 类型需要进一步分析
            if dtype == "object":
                non_null = series.dropna()
                if len(non_null) == 0:
                    return "text"

                # 统计各类型的数量
                numeric_count = 0
                str_count = 0
                date_count = 0

                for v in non_null.head(100):  # 只检查前 100 个值
                    if isinstance(v, bool):
                        continue
                    elif isinstance(v, (int, float)):
                        if not (isinstance(v, float) and math.isnan(v)):
                            numeric_count += 1
                    elif isinstance(v, str):
                        str_count += 1
                    elif hasattr(v, 'year'):  # datetime-like
                        date_count += 1

                total = numeric_count + str_count + date_count
                if total == 0:
                    return "text"

                # 判断主要类型
                if date_count / total > 0.5:
                    return "date"
                if numeric_count / total > 0.8:
                    return "number"
                if str_count / total > 0.8:
                    return "text"
                if numeric_count > 0 and str_count > 0:
                    return "mixed"  # 混合类型，提醒 LLM 注意

            return "text"

        def get_samples(series: pd.Series, count: int) -> List[Any]:
            """获取列的样本数据（非空值）"""
            non_null = series.dropna()
            if len(non_null) == 0:
                return []

            # 取前 count 个非空值
            samples = []
            for v in non_null.head(count):
                # 转换为可 JSON 序列化的格式
                if isinstance(v, (int, float)):
                    if isinstance(v, float) and math.isnan(v):
                        continue
                    samples.append(v)
                elif hasattr(v, 'isoformat'):  # datetime
                    samples.append(v.isoformat()[:10])  # 只取日期部分
                else:
                    samples.append(str(v)[:50])  # 限制字符串长度

            return samples

        schemas = {}
        for file_id, excel_file in self._files.items():
            schemas[file_id] = {}
            for sheet_name in excel_file.get_sheet_names():
                table = excel_file.get_sheet(sheet_name)
                df = table.get_data()

                columns_info = []
                for col_name in table.get_columns():
                    series = df[col_name]
                    col_type = detect_column_type(series)
                    samples = get_samples(series, sample_count)

                    columns_info.append({
                        "name": col_name,
                        "type": col_type,
                        "samples": samples
                    })

                schemas[file_id][sheet_name] = columns_info

        return schemas

    def get_column_mapping(self) -> Dict[str, Dict[str, Dict[str, str]]]:
        """
        获取列名到 Excel 列标识的映射（两层）

        Returns:
            {
                "file_id_1": {
                    "sheet1": {"列名1": "A", "列名2": "B", ...},
                    "sheet2": {...}
                },
                ...
            }
        """
        mapping = {}
        for file_id, excel_file in self._files.items():
            mapping[file_id] = {}
            for sheet_name in excel_file.get_sheet_names():
                table = excel_file.get_sheet(sheet_name)
                columns = table.get_columns()
                mapping[file_id][sheet_name] = {
                    col_name: column_index_to_letter(i)
                    for i, col_name in enumerate(columns)
                }
        return mapping

    def __repr__(self):
        file_info = {
            file_id: f"{file.filename}({len(file)} sheets)"
            for file_id, file in self._files.items()
        }
        return f"FileCollection(files={file_info})"

    def __iter__(self):
        """迭代所有文件"""
        return iter(self._files.values())

    def export_to_excel(self, output_path: str):
        """
        导出所有文件的所有 sheet 到一个 Excel 文件

        每个 sheet 使用 "文件名_sheet名" 作为导出的 sheet 名

        Args:
            output_path: 输出文件路径
        """
        with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
            for file_id, excel_file in self._files.items():
                for sheet_name in excel_file.get_sheet_names():
                    table = excel_file.get_sheet(sheet_name)
                    # 使用 "文件名_sheet名" 作为导出的 sheet 名
                    # 去掉文件扩展名
                    filename_stem = excel_file.filename.rsplit('.', 1)[0]
                    export_sheet_name = f"{filename_stem}_{sheet_name}"[:31]
                    table.get_data().to_excel(writer, sheet_name=export_sheet_name, index=False)

    def export_to_bytes(self) -> bytes:
        """
        导出所有文件的所有 sheet 到 Excel 字节流

        Returns:
            Excel 文件的字节内容
        """
        import io

        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            for file_id, excel_file in self._files.items():
                for sheet_name in excel_file.get_sheet_names():
                    table = excel_file.get_sheet(sheet_name)
                    filename_stem = excel_file.filename.rsplit('.', 1)[0]
                    export_sheet_name = f"{filename_stem}_{sheet_name}"[:31]
                    table.get_data().to_excel(writer, sheet_name=export_sheet_name, index=False)

        return output.getvalue()

    def export_file_to_bytes(self, file_id: str) -> bytes:
        """
        导出单个文件的所有 sheet 到 Excel 字节流

        Args:
            file_id: 文件 ID

        Returns:
            Excel 文件的字节内容

        Raises:
            ValueError: 如果文件不存在
        """
        import io

        if file_id not in self._files:
            raise ValueError(f"文件不存在: {file_id}")

        excel_file = self._files[file_id]
        output = io.BytesIO()

        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            for sheet_name in excel_file.get_sheet_names():
                table = excel_file.get_sheet(sheet_name)
                # 直接使用 sheet 名称（不加文件名前缀）
                table.get_data().to_excel(writer, sheet_name=sheet_name[:31], index=False)

        return output.getvalue()

    def get_file_info(self, file_id: str) -> Dict[str, Any]:
        """
        获取文件信息

        Args:
            file_id: 文件 ID

        Returns:
            {"file_id": str, "filename": str, "sheet_count": int}
        """
        if file_id not in self._files:
            raise ValueError(f"文件不存在: {file_id}")

        excel_file = self._files[file_id]
        return {
            "file_id": file_id,
            "filename": excel_file.filename,
            "sheet_count": len(excel_file),
        }

    def apply_new_columns(
        self,
        new_columns: Dict[str, Dict[str, Dict[str, List[Any]]]]
    ):
        """
        将新增列应用到表中

        Args:
            new_columns: 新增列数据 {
                file_id: {
                    sheet_name: {
                        column_name: [值列表]
                    }
                }
            }
        """
        for file_id, sheets in new_columns.items():
            if file_id in self._files:
                excel_file = self._files[file_id]
                for sheet_name, columns in sheets.items():
                    if excel_file.has_sheet(sheet_name):
                        table = excel_file.get_sheet(sheet_name)
                        for col_name, values in columns.items():
                            # 如果列已存在则更新，否则添加
                            # （处理 executor 已经应用过的情况）
                            if col_name in table.get_columns():
                                table.update_column(col_name, values)
                            else:
                                table.add_column(col_name, values)

    def apply_updated_columns(
        self,
        updated_columns: Dict[str, Dict[str, Dict[str, List[Any]]]]
    ):
        """
        将更新列应用到表中

        Args:
            updated_columns: 更新列数据 {
                file_id: {
                    sheet_name: {
                        column_name: [值列表]
                    }
                }
            }
        """
        for file_id, sheets in updated_columns.items():
            if file_id in self._files:
                excel_file = self._files[file_id]
                for sheet_name, columns in sheets.items():
                    if excel_file.has_sheet(sheet_name):
                        table = excel_file.get_sheet(sheet_name)
                        for col_name, values in columns.items():
                            table.update_column(col_name, values)

    def apply_new_sheets(
        self,
        new_sheets: Dict[str, Dict[str, pd.DataFrame]]
    ):
        """
        将新创建的 Sheet 应用到文件集合中

        Args:
            new_sheets: 新 Sheet 数据 {
                file_id: {
                    sheet_name: DataFrame
                }
            }
        """
        for file_id, sheets in new_sheets.items():
            if file_id in self._files:
                excel_file = self._files[file_id]
                for sheet_name, df in sheets.items():
                    # 如果 Sheet 已存在，先删除再添加（用于 in_place 替换）
                    if excel_file.has_sheet(sheet_name):
                        # 直接更新内部字典
                        excel_file._sheets[sheet_name] = Table(name=sheet_name, data=df)
                    else:
                        # 创建新 Table 并添加
                        table = Table(name=sheet_name, data=df)
                        excel_file.add_sheet(table)

    def apply_changes(
        self,
        new_columns: Dict[str, Dict[str, Dict[str, List[Any]]]] = None,
        updated_columns: Dict[str, Dict[str, Dict[str, List[Any]]]] = None,
        new_sheets: Dict[str, Dict[str, pd.DataFrame]] = None
    ):
        """
        统一应用新增列、更新列和新 Sheet

        Args:
            new_columns: 新增列数据
            updated_columns: 更新列数据
            new_sheets: 新创建的 Sheet 数据
        """
        # 先应用新 Sheet（这样后续操作可以引用新表）
        if new_sheets:
            self.apply_new_sheets(new_sheets)
        if new_columns:
            self.apply_new_columns(new_columns)
        if updated_columns:
            self.apply_updated_columns(updated_columns)
