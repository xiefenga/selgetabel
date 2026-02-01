# 文件-Sheet 两层结构改造总结

## 改造目标

将系统从**扁平表结构**改造为**文件-Sheet 两层结构**，支持：

- 多个 Excel 文件
- 每个文件包含多个 sheets
- 避免表名冲突

## 数据结构变化

### 改造前（扁平结构）

```python
TableCollection = {
    "订单": Table(...),
    "客户": Table(...),
    "产品": Table(...),
}
```

**问题**：不同文件的同名 sheet 会冲突

### 改造后（两层结构）

```python
FileCollection = {
    "file_id_1": ExcelFile(
        file_id="file_id_1",
        filename="orders.xlsx",
        sheets={
            "订单": Table(...),
            "客户": Table(...),
        }
    ),
    "file_id_2": ExcelFile(
        file_id="file_id_2",
        filename="analysis.xlsx",
        sheets={
            "订单": Table(...),  # 不会冲突
            "统计": Table(...),
        }
    )
}
```

## 核心类变化

### 1. 新增 `ExcelFile` 类

```python
class ExcelFile:
    """代表一个 Excel 文件及其包含的所有 sheets"""

    def __init__(self, file_id: str, filename: str):
        self.file_id = file_id
        self.filename = filename
        self._sheets: Dict[str, Table] = {}

    def add_sheet(self, sheet: Table)
    def get_sheet(self, sheet_name: str) -> Table
    def get_sheet_names(self) -> List[str]
```

### 2. `TableCollection` → `FileCollection`

```python
class FileCollection:
    """管理多个 ExcelFile（两层结构）"""

    def __init__(self):
        self._files: Dict[str, ExcelFile] = {}

    def add_file(self, excel_file: ExcelFile)
    def get_file(self, file_id: str) -> ExcelFile
    def get_table(self, file_id: str, sheet_name: str) -> Table
    def get_file_ids(self) -> List[str]
```

### 3. 操作定义更新

**添加 `file_id` 字段**：

```python
@dataclass
class AggregateOperation:
    function: str
    file_id: str  # 新增
    table: str    # 现在表示 sheet_name
    column: Optional[str] = None
    ...

@dataclass
class AddColumnOperation:
    file_id: str  # 新增
    table: str    # 现在表示 sheet_name
    name: str
    formula: Union[str, Dict[str, Any]]
```

## 引用方式变化

### 跨表引用

**改造前**（两段式）：

```json
{ "ref": "订单.金额" }
```

**改造后**（三段式）：

```json
{ "ref": "file_id_123.订单.金额" }
```

### VLOOKUP

**改造前**：

```json
{
  "func": "VLOOKUP",
  "args": [查找值, "订单", "键列", "值列"]
}
```

**改造后**：

```json
{
  "func": "VLOOKUP",
  "args": [查找值, "file_id_123.订单", "键列", "值列"]
}
```

### 操作定义

**改造前**：

```json
{
  "type": "aggregate",
  "function": "SUM",
  "table": "订单",
  "column": "金额",
  "as": "总额"
}
```

**改造后**：

```json
{
  "type": "aggregate",
  "function": "SUM",
  "file_id": "abc-123",
  "table": "订单",
  "column": "金额",
  "as": "总额"
}
```

## 已完成的文件改造

### ✅ 核心模型层

| 文件        | 改动内容                                                                                                                                   |
| ----------- | ------------------------------------------------------------------------------------------------------------------------------------------ |
| `models.py` | • 新增 `ExcelFile` 类<br>• `TableCollection` → `FileCollection`<br>• 操作类添加 `file_id` 字段<br>• `ExecutionResult.new_columns` 改为三层 |

### ✅ 解析和执行层

| 文件              | 改动内容                                                                                                                                   |
| ----------------- | ------------------------------------------------------------------------------------------------------------------------------------------ |
| `excel_parser.py` | • `load_tables_from_minio_paths` 参数和返回值改为 `FileCollection`<br>• 解析逻辑改为创建 `ExcelFile` 对象                                  |
| `executor.py`     | • `FormulaEvaluator` 支持三段式引用<br>• `Executor` 使用 `file_id + sheet_name` 获取表<br>• `_eval_vlookup` 支持 "file_id.sheet_name" 格式 |
| `parser.py`       | • `_parse_aggregate/add_column` 添加 `file_id` 字段验证<br>• `validate_operations` 改为验证 `file_sheets` 映射                             |

### ✅ 公式生成层

| 文件                 | 改动内容                                                                                                                                                                   |
| -------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `excel_generator.py` | • `generate_formula` 添加 `file_id, sheet_name` 参数<br>• `_find_column_letter` 使用三层映射<br>• `_generate_ref` 支持三段式引用<br>• `generate_formulas` 输出包含文件信息 |

### ✅ 步骤和服务层

| 文件                | 改动内容                                                                                         |
| ------------------- | ------------------------------------------------------------------------------------------------ |
| `load_files.py`     | • 返回 `FileCollection`                                                                          |
| `execute.py`        | • 构建 `file_sheets` 映射用于验证<br>• 处理三层 `new_columns` 结构                               |
| `services/excel.py` | • `load_tables_from_files` 返回 `FileCollection`<br>• 传递 `(file_id, file_path, filename)` 元组 |
| `context.py`        | • `tables` 属性类型改为 `FileCollection`<br>• `schemas` 返回类型改为三层                         |

### ✅ CLI 工具

| 文件     | 改动内容                                                                                                                      |
| -------- | ----------------------------------------------------------------------------------------------------------------------------- |
| `cli.py` | • `load_excel_files` 返回 `FileCollection`<br>• `display_schemas` 显示两层结构<br>• `process_requirement_two_step` 适配新接口 |

## Schemas 结构变化

### 改造前

```json
{
  "订单": {
    "A": "订单ID",
    "B": "客户名",
    "C": "金额"
  },
  "客户": {
    "A": "客户ID",
    "B": "客户名"
  }
}
```

### 改造后

```json
{
  "file_id_1": {
    "订单": {
      "A": "订单ID",
      "B": "客户名",
      "C": "金额"
    },
    "客户": {
      "A": "客户ID",
      "B": "客户名"
    }
  },
  "file_id_2": {
    "统计": {
      "A": "日期",
      "B": "数量"
    }
  }
}
```

## 导出行为变化

### 改造前

- 每个表（sheet）单独导出
- Sheet 名称 = 表名

### 改造后

- 所有文件的所有 sheets 合并导出
- Sheet 名称 = `文件名_sheet名`（如 "orders*订单", "orders*客户"）

## ⚠️ 需要更新的部分

### 1. LLM 提示词（未完成）

需要更新 `app/core/llm_client.py` 或相关 prompt 文件，告知 LLM：

- 操作定义需要包含 `file_id` 字段
- 跨表引用格式为 `file_id.sheet_name.column_name`
- VLOOKUP 的表引用格式为 `file_id.sheet_name`

### 2. 文档更新（未完成）

- `OPERATION_SPEC.md` - 更新操作规范示例
- `README.md` - 更新使用说明
- API 文档 - 更新接口说明

### 3. 测试（未完成）

- 单元测试需要更新
- 集成测试需要更新
- 确保所有场景正常工作

## 兼容性说明

**此改造不向后兼容**：

- 旧的操作定义（没有 `file_id`）将无法解析
- 旧的引用格式（两段式）将报错
- 需要重新生成所有操作描述

## 测试建议

### 1. 单文件多 sheet 场景

```bash
# 测试单个文件包含多个 sheets
python cli.py data/multi_sheet.xlsx
```

### 2. 多文件场景

```bash
# 测试多个文件
python cli.py data/file1.xlsx data/file2.xlsx
```

### 3. 同名 sheet 场景

创建两个文件，都包含名为 "订单" 的 sheet，验证不会冲突。

### 4. 跨文件引用

测试在 file1 的列计算中引用 file2 的数据。

## 下一步工作

1. ✅ 完成核心代码改造
2. ⚠️ 更新 LLM 提示词
3. ⚠️ 更新操作规范文档
4. ⚠️ 更新测试用例
5. ⚠️ 测试所有场景
6. ⚠️ 更新前端显示（如果需要）

## 改造时间

2026-01-29

## 技术负责人

Claude (Sonnet 4.5)
