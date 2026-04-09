# Engine 层架构设计文档

本文档详细说明 `app/engine/` 模块中核心类的职责、关系和工作流程。

> **模块位置**：`apps/api/app/engine/`
>
> Engine 层是系统的核心原子操作层（Layer 3），提供数据模型、LLM 客户端、解析器、执行器等基础能力。

---

## 🏗️ 整体架构

系统采用**两层文件-Sheet 结构**，核心类协作流程如下：

```
┌──────────────┐
│ ExcelParser  │ ──解析→ ExcelFile ──管理→ Table (sheet数据)
└──────┬───────┘              ↓
       │                 FileCollection
       │                      ↓
       │              ┌───────────────┐
       └──────────→   │   Executor    │ ──执行→ Operations
                      └───────────────┘
                             ↓
                      ExecutionResult
```

---

## 📦 核心类详解

### 1. **Table** - Sheet 数据容器

**职责**：封装单个 Excel sheet 的数据（基于 pandas DataFrame）

**属性**：

- `name: str` - Sheet 名称
- `_data: pd.DataFrame` - 数据内容
- `_columns: List[str]` - 列名列表

**核心方法**：

```python
def get_column(self, column_name: str) -> Range
    """获取列数据（返回列表）"""

def get_columns(self) -> List[str]
    """获取所有列名"""

def get_column_letter(self, column_name: str) -> str
    """获取列的 Excel 列标（A, B, C...）"""

def add_column(self, column_name: str, values: List[Any])
    """添加新列"""

def row_count(self) -> int
    """获取行数"""
```

**设计要点**：

- 不知道自己属于哪个文件（单一职责）
- 提供列级访问和 Excel 列标转换
- 支持动态添加列（执行 add_column 操作时）

---

### 2. **ExcelFile** - 文件容器

**职责**：代表一个 Excel 文件及其包含的所有 sheets

**属性**：

- `file_id: str` - 文件 UUID
- `filename: str` - 原始文件名（如 "orders.xlsx"）
- `_sheets: Dict[str, Table]` - Sheets 字典（键=sheet名，值=Table对象）

**核心方法**：

```python
def add_sheet(self, sheet: Table)
    """添加 sheet"""

def get_sheet(self, sheet_name: str) -> Table
    """获取指定 sheet"""

def has_sheet(self, sheet_name: str) -> bool
    """检查 sheet 是否存在"""

def get_sheet_names(self) -> List[str]
    """获取所有 sheet 名称"""

def get_schema(self) -> Dict[str, Dict[str, str]]
    """获取本文件所有 sheet 的列结构"""
```

**设计要点**：

- 封装文件级元数据（file_id, filename）
- 管理文件内的所有 sheets
- 不同文件可以有同名 sheet（隔离命名空间）

**示例**：

```python
excel_file = ExcelFile(
    file_id="abc-123",
    filename="orders.xlsx"
)
excel_file.add_sheet(Table(name="订单", data=df1))
excel_file.add_sheet(Table(name="客户", data=df2))

# 访问
orders_table = excel_file.get_sheet("订单")
```

---

### 3. **FileCollection** - 文件集合管理器

**职责**：管理多个 ExcelFile，提供统一的访问接口

**属性**：

- `_files: Dict[str, ExcelFile]` - 文件字典（键=file_id，值=ExcelFile对象）

**核心方法**：

```python
def add_file(self, excel_file: ExcelFile)
    """添加文件"""

def get_file(self, file_id: str) -> ExcelFile
    """获取文件"""

def get_table(self, file_id: str, sheet_name: str) -> Table
    """两层访问：直接获取指定文件的指定 sheet"""

def get_file_ids(self) -> List[str]
    """获取所有文件 ID"""

def get_schemas(self) -> Dict[str, Dict[str, Dict[str, str]]]
    """获取所有表结构（三层：file_id → sheet_name → column_mapping）"""

def export_to_excel(self, output_path: str)
    """导出所有文件的所有 sheet 到一个 Excel"""

def apply_new_columns(self, new_columns: Dict[str, Dict[str, Dict[str, List[Any]]]])
    """应用执行结果中的新增列（三层结构）"""
```

**设计要点**：

- 提供 `get_table(file_id, sheet_name)` 便捷方法（两层访问）
- 支持导出时自动处理 sheet 名称冲突（`文件名_sheet名`）
- `get_schemas()` 返回三层结构，用于 LLM 理解数据

**schemas 结构示例**：

```python
{
    "abc-123": {
        "订单": {"A": "订单ID", "B": "金额", "C": "状态"},
        "客户": {"A": "客户ID", "B": "姓名"}
    },
    "def-456": {
        "统计": {"A": "日期", "B": "数量"}
    }
}
```

---

### 4. **ExcelParser** - Excel 解析器

**职责**：读取 Excel 文件（本地或 MinIO），转换为 FileCollection

**核心方法**：

```python
@staticmethod
def load_tables_from_minio_paths(
    file_records: List[tuple[str, str, str]]
) -> FileCollection
    """
    从 MinIO 加载多个文件

    Args:
        file_records: [(file_id, file_path, filename), ...]

    Returns:
        FileCollection 对象
    """

@staticmethod
def parse_file_all_sheets(
    file_path: Union[str, Path],
    file_id: str = None,
    sheet_names: List[str] = None
) -> FileCollection
    """解析本地文件的所有 sheet"""
```

**工作流程**：

```
1. 读取 Excel 文件（MinIO 或本地）
2. 使用 pandas 解析所有 sheets
3. 为每个 sheet 创建 Table 对象
4. 创建 ExcelFile 对象，添加所有 Table
5. 创建 FileCollection，添加 ExcelFile
6. 返回 FileCollection
```

**关键代码片段**：

```python
# 创建 ExcelFile
excel_file = ExcelFile(file_id=file_id, filename=filename)

# 解析所有 sheets
for sheet_name in sheet_names:
    df = pd.read_excel(excel_file_data, sheet_name=sheet_name)
    df = ExcelParser._clean_dataframe(df)
    table = Table(name=sheet_name, data=df)
    excel_file.add_sheet(table)

# 添加到集合
collection.add_file(excel_file)
```

---

### 5. **Executor** - 操作执行引擎

**职责**：执行操作列表（aggregate, add_column, compute），返回执行结果

**属性**：

- `tables: FileCollection` - 文件集合
- `variables: Dict[str, Any]` - 变量上下文（存储中间结果）

**核心方法**：

```python
def execute(self, operations: List[Operation]) -> ExecutionResult
    """执行操作列表"""

def _execute_aggregate(self, op: AggregateOperation) -> OperationResult
    """执行聚合操作"""

def _execute_add_column(self, op: AddColumnOperation) -> OperationResult
    """执行添加列操作"""

def _execute_compute(self, op: ComputeOperation) -> OperationResult
    """执行计算操作"""
```

**工作流程**：

```
1. 遍历 operations 列表
2. 根据操作类型调用对应的 _execute_* 方法
3. 使用 file_id + sheet_name 获取表：
   table = self.tables.get_table(op.file_id, op.table)
4. 执行计算/聚合
5. 收集结果（变量、新列、错误）
6. 返回 ExecutionResult
```

**关键改造点**：

- 表访问改为两层：`get_table(file_id, sheet_name)`
- `add_column` 操作会直接修改 Table 对象（调用 `table.add_column()`）
- 支持跨表引用（通过 FormulaEvaluator）

---

### 6. **FormulaEvaluator** - 公式求值器

**职责**：计算 JSON 格式的表达式（支持跨表引用）

**属性**：

- `row_context: Dict[str, Any]` - 当前行数据
- `tables: FileCollection` - 文件集合（用于跨表访问）
- `functions: Dict[str, callable]` - 可用函数

**核心方法**：

```python
def evaluate(self, expr: Union[Dict, Any]) -> Any
    """递归求值表达式"""

def _get_table_column(self, ref: str) -> List[Any]
    """
    获取跨表列引用（三段式）
    格式：file_id.sheet_name.column_name
    """

def _eval_vlookup(self, args: List) -> Any
    """
    执行 VLOOKUP
    表引用格式：file_id.sheet_name（两段式）
    """
```

**支持的表达式类型**：

```python
{"value": 100}                           # 字面量
{"col": "金额"}                          # 当前行列引用
{"ref": "file-001.订单.金额"}            # 跨表引用（三段式）
{"func": "IF", "args": [...]}            # 函数调用
{"op": "+", "left": {...}, "right": {...}}  # 二元运算
```

**跨表引用示例**：

```python
# 引用格式
ref = "abc-123.卖断发生额明细.票据号"

# 解析
file_id, sheet_name, col_name = ref.split(".")  # 三段式

# 获取数据
table = self.tables.get_table(file_id, sheet_name)
return table.get_column(col_name)
```

---

### 7. **操作类（Operation）** - 数据类

**AggregateOperation** - 聚合操作：

```python
@dataclass
class AggregateOperation:
    function: str       # SUM, COUNT, AVERAGE 等
    file_id: str        # 文件 ID ✨ 新增
    table: str          # Sheet 名称
    column: str         # 聚合列
    as_var: str         # 结果变量名
    # ... 可选字段（condition_column, condition）
```

**AddColumnOperation** - 添加列操作：

```python
@dataclass
class AddColumnOperation:
    file_id: str                           # 文件 ID ✨ 新增
    table: str                             # Sheet 名称
    name: str                              # 新列名
    formula: Union[str, Dict[str, Any]]    # JSON 格式公式
```

**ComputeOperation** - 计算操作：

```python
@dataclass
class ComputeOperation:
    expression: Union[str, Dict[str, Any]]  # JSON 格式表达式
    as_var: str                             # 结果变量名
```

**关键改造**：所有涉及表的操作都添加了 `file_id` 字段

---

### 8. **ExecutionResult** - 执行结果

**职责**：封装操作执行的所有结果

**属性**：

```python
@dataclass
class ExecutionResult:
    # 变量上下文（聚合结果）
    variables: Dict[str, Any]

    # 新增的列数据（三层：file_id → sheet_name → column_name → values）
    new_columns: Dict[str, Dict[str, Dict[str, List[Any]]]]

    # 每个操作的结果
    operation_results: List[OperationResult]

    # Excel 公式
    excel_formulas: List[str]

    # 错误信息
    errors: List[str]
```

**new_columns 结构示例**：

```python
{
    "abc-123": {          # file_id
        "订单": {          # sheet_name
            "折扣价": [90, 180, 270, ...],    # column_name: values
            "等级": ["高", "低", "高", ...]
        }
    }
}
```

---

## 🔄 完整工作流程

### 场景：处理 Excel 数据

```
1️⃣ 文件上传与解析
   ┌─────────────────┐
   │  用户上传文件    │ → File records 存入数据库
   └────────┬────────┘
            ↓
   ┌─────────────────┐
   │  ExcelParser    │ → 从 MinIO 读取文件
   │ .load_tables_   │ → 解析所有 sheets
   │  from_minio     │ → 创建 ExcelFile
   └────────┬────────┘
            ↓
   ┌─────────────────┐
   │ FileCollection  │ ← 两层结构，包含所有文件和 sheets
   └─────────────────┘

2️⃣ 操作生成与验证（GenerateValidateStage 复合阶段）
   ┌─────────────────────────────────────┐
   │  GenerateValidateStage              │
   │  ┌─────────────────┐                │
   │  │ LLM 生成操作    │ ←─────────────┐│
   │  └────────┬────────┘               ││
   │           ↓                        ││
   │  ┌─────────────────┐               ││
   │  │ OperationParser │ → 解析 JSON   ││
   │  │ .parse()        │ → 验证结构    ││
   │  └────────┬────────┘               ││
   │           │                        ││
   │           ↓ 验证失败？             ││
   │           │                        ││
   │           ├─→ 是 且 重试<max：重试 ─┘│
   │           │                        │
   │           └─→ 否 或 超限：继续     │
   └───────────┬─────────────────────────┘
               ↓
   List[Operation] (包含 file_id，已验证)

3️⃣ 执行操作
   ┌─────────────────┐
   │  Executor       │ ← 接收已验证的操作
   │  .execute()     │
   └────────┬────────┘
            │
            ├─→ aggregate: table = collection.get_table(file_id, sheet_name)
            │              执行聚合，返回单值
            │
            ├─→ add_column: table = collection.get_table(file_id, sheet_name)
            │               遍历每行，用 FormulaEvaluator 计算
            │               table.add_column(name, values)
            │
            └─→ compute: 计算标量表达式
            ↓
   ┌─────────────────┐
   │ ExecutionResult │ ← variables, new_columns, errors
   └─────────────────┘

4️⃣ 导出结果
   ┌─────────────────┐
   │ collection.     │
   │ apply_new_      │ → 将新列应用到 Table
   │ columns()       │
   └────────┬────────┘
            ↓
   ┌─────────────────┐
   │ collection.     │
   │ export_to_      │ → 导出到 Excel
   │ excel()         │
   └─────────────────┘
```

---

## 💡 关键设计决策

### 1. **为什么选择两层结构？**

**原因**：

- 避免表名冲突（不同文件可以有同名 sheet）
- 更符合用户心智模型（文件 → sheets）
- 支持跨文件数据处理

**替代方案**：

- 扁平结构 + 表名前缀（如 "file1\_订单"）❌ 不直观
- 完全扁平 ❌ 会冲突

### 2. **为什么 Table 不知道自己的 file_id？**

**原因**：

- 单一职责：Table 只负责数据存储
- ExcelFile 负责管理 sheets 和文件元数据
- 降低耦合

### 3. **为什么操作定义要包含 file_id？**

**原因**：

- 明确指定操作目标（哪个文件的哪个 sheet）
- 支持跨文件操作
- 便于验证（解析时检查 file_id 是否存在）

### 4. **为什么跨表引用是三段式？**

**原因**：

- 完整标识：file_id + sheet_name + column_name
- 支持跨文件引用
- 保持一致性（操作定义也是两层）

**格式对比**：

```python
# 两段式（旧）❌
{"ref": "订单.金额"}  # 不知道是哪个文件

# 三段式（新）✅
{"ref": "abc-123.订单.金额"}  # 明确标识
```

### 5. **为什么 VLOOKUP 的表引用是两段式？**

**原因**：

- VLOOKUP 需要的是表（file_id + sheet_name）
- 不需要列名（列名在后续参数中指定）

**示例**：

```python
{
  "func": "VLOOKUP",
  "args": [
    {"col": "客户ID"},              # 查找值
    {"value": "abc-123.客户"},      # 表引用（两段式）
    {"value": "ID"},                # 键列名
    {"value": "姓名"}               # 值列名
  ]
}
```

---

## 🎯 类职责总结表

| 类                   | 职责               | 核心数据                        | 主要方法                            |
| -------------------- | ------------------ | ------------------------------- | ----------------------------------- |
| **Table**            | 封装 sheet 数据    | `pd.DataFrame`                  | `get_column()`, `add_column()`      |
| **ExcelFile**        | 管理文件的 sheets  | `Dict[str, Table]`              | `get_sheet()`, `add_sheet()`        |
| **FileCollection**   | 管理多个文件       | `Dict[str, ExcelFile]`          | `get_table()`, `get_schemas()`      |
| **ExcelParser**      | 解析 Excel 文件    | 无状态（静态）                  | `load_tables_from_minio_paths()`    |
| **Executor**         | 执行操作           | `FileCollection`, `variables`   | `execute()`, `_execute_*()`         |
| **FormulaEvaluator** | 计算表达式         | `FileCollection`, `row_context` | `evaluate()`, `_get_table_column()` |
| **Operation**        | 操作定义（数据类） | 操作参数                        | 无（纯数据）                        |
| **ExecutionResult**  | 执行结果（数据类） | 结果数据                        | 辅助方法（add\_\*）                 |

### 分析模块（新增）

| 类                      | 职责                       | 核心数据                       | 主要方法                                |
| ----------------------- | -------------------------- | ------------------------------ | ------------------------------------- |
| **DataProfiler**        | 数据画像提取               | TableProfile, MultiTableProfile | `profile_table()`, `profile_tables()` |
| **QualityChecker**      | 数据质量检测               | QualityReport                  | `check_quality()`, `check_nulls()`    |
| **RelationshipDetector**| 表关系识别                 | Relationship                   | `detect_relationships()`              |
| **AnalysisFunctions**   | 专项分析函数               | 统计分析                       | `pearson_correlation()`, `trend_analysis()` |
| **AnalysisStage**       | 数据分析阶段（Pipeline）   | FileCollection, query          | `run()`, `_handle_l2_scenario()` 等   |

---

---

### 9. **OutputGenerator** - 输出生成器

**职责**：将执行结果转换为用户友好的三种输出格式

**核心函数**：

```python
def generate_strategy(operations: List, tables: FileCollection) -> str
    """生成思路解读：让用户理解系统'准备怎么操作'"""

def generate_manual_steps(operations: List, tables: FileCollection) -> str
    """生成快捷复现：用户手动操作 Excel 的步骤指南"""
```

**输出格式**：

| 输出       | 目的             | 内容                           |
| ---------- | ---------------- | ------------------------------ |
| 思路解读   | 验证思路是否正确 | 步骤概要 + 操作方法            |
| 快捷复现   | 手动复现         | 具体操作步骤（区分 365/非365） |
| Excel 公式 | 精确复现         | 公式模板（已有）               |

**设计要点**：

- **分工合作**：LLM 的 `description` 说明"做什么"，系统解析技术细节说明"怎么做"
- **版本适配**：高级操作（filter, sort, group_by, take, pivot）提供两种复现方式
  - 非 365：菜单操作步骤（优先展示）
  - 365：公式方式

详见 [OUTPUT_GENERATION.md](./OUTPUT_GENERATION.md)

---

## 📚 扩展阅读

- **操作规范**：详见 `docs/OPERATION_SPEC.md`
- **处理器设计**：详见 `docs/PROCESSOR_DESIGN.md`
- **输出生成**：详见 `docs/OUTPUT_GENERATION.md`
- **使用示例**：详见 `apps/api/cli.py`

---

## 🔧 开发建议

### 添加新功能时

1. **新操作类型**：
   - 在 `engine/models.py` 添加新的 `@dataclass`
   - 在 `engine/parser.py` 添加解析逻辑
   - 在 `engine/executor.py` 添加执行逻辑

2. **新表达式类型**：
   - 在 `engine/executor.py` 的 `FormulaEvaluator.evaluate()` 添加处理分支
   - 在 `engine/excel_generator.py` 添加公式生成逻辑

3. **新函数**：
   - 在 `engine/functions.py` 实现函数
   - 在 `engine/parser.py` 添加到白名单
   - 在 `engine/excel_generator.py` 添加公式模板

### 调试建议

1. **查看 schemas**：

   ```python
   schemas = collection.get_schemas()
   print(json.dumps(schemas, indent=2, ensure_ascii=False))
   ```

2. **检查 Table 内容**：

   ```python
   table = collection.get_table(file_id, sheet_name)
   print(f"Rows: {table.row_count()}")
   print(f"Columns: {table.get_columns()}")
   ```

3. **跟踪执行过程**：
   ```python
   result = executor.execute(operations)
   print(f"Variables: {result.variables}")
   print(f"New columns: {result.new_columns}")
   print(f"Errors: {result.errors}")
   ```

---

## 🔢 数据类型处理

本节说明系统如何处理 Excel 数据在不同层级的类型转换和兼容性问题。

### 三层类型映射

数据在系统中经历三层类型转换：

```
Excel 文件 → pandas DataFrame → 系统执行
```

| Excel 数据       | pandas dtype     | 系统类型  | 说明                                   |
| ---------------- | ---------------- | --------- | -------------------------------------- |
| 纯整数（无空值） | `int64`          | `number`  |                                        |
| 纯整数（有空值） | `float64`        | `number`  | NaN 是 float，导致类型变化             |
| 小数             | `float64`        | `number`  |                                        |
| 纯文本           | `object`         | `text`    |                                        |
| 混合内容         | `object`         | `mixed`   | **问题根源**：同列包含 str、int、float |
| 日期             | `datetime64[ns]` | `date`    |                                        |
| 布尔             | `bool`           | `boolean` |                                        |

### 增强 Schema 格式

`FileCollection.get_schemas_with_samples()` 返回包含类型和样本的增强结构：

```python
{
    "file_id": {
        "sheet_name": [
            {"name": "列名", "type": "number", "samples": [100, 200, 300]},
            {"name": "wage", "type": "mixed", "samples": ["€150K", "€200K"]},
            ...
        ]
    }
}
```

**类型检测逻辑**（针对 `object` 类型列）：

```python
# 采样前 100 个非空值
if 数值占比 > 80%:
    return "number"
elif 文本占比 > 80%:
    return "text"
elif 数值和文本都有:
    return "mixed"  # 提醒 LLM 注意混合类型
```

### 执行器类型安全处理

#### 1. 比较运算符 (`>`, `<`, `>=`, `<=`)

**问题**：`"100" > 50` 会抛出 `TypeError`

**解决方案**：

```python
def safe_compare(a, b, compare_func):
    # 1. 尝试将两边都转为数值
    a_num = try_convert_to_number(a)
    b_num = try_convert_to_number(b)

    if 两边都是数值:
        return compare_func(a_num, b_num)

    # 2. 模拟 Excel 行为：数值 < 文本
    if a 是数值 and b 是文本:
        return True if op == "<" else False

    # 3. 无法比较时返回 False（不报错）
    return False
```

#### 2. filter 操作

**问题**：`df[col] > value` 在混合类型列上报错

**解决方案**：

```python
if value 是数值:
    # 将列转换为数值后比较
    col_numeric = pd.to_numeric(df[col], errors="coerce")
    conditions.append(col_numeric > value)
else:
    # 字符串比较
    conditions.append(df[col].astype(str) > str(value))
```

#### 3. sort 操作

**问题**：混合类型列无法直接排序

**解决方案**：

```python
if df[col].dtype == "object":
    # 尝试转换为数值
    numeric_col = pd.to_numeric(df[col], errors="coerce")
    if 超过 50% 能转为数值:
        # 使用数值排序（非数值放最后）
        df["_sort_col"] = numeric_col.fillna(float("inf"))
    else:
        # 回退到字符串排序
        df[col] = df[col].astype(str)
```

### 错误传播机制

当表达式计算中出现错误时，错误会被传播而不是抛出异常：

```python
def _eval_binary_op(self, op, left_expr, right_expr):
    left = self.evaluate(left_expr)
    right = self.evaluate(right_expr)

    # 错误传播：如果任一操作数是 ExcelError，直接返回
    if isinstance(left, ExcelError):
        return left
    if isinstance(right, ExcelError):
        return right

    # ... 继续计算
```

**示例**：

```
height_cm = None
→ height_cm / 100 = ExcelError("#VALUE!")
→ ExcelError * ExcelError = ExcelError("#VALUE!")  # 传播，不报错
```

### LLM 看到的 Schema 格式

```markdown
#### Sheet: players_22

| 列名       | 类型   | 样本数据                        |
| ---------- | ------ | ------------------------------- |
| sofifa_id  | number | 158023, 188545, 190871          |
| short_name | text   | "L. Messi", "Cristiano Ronaldo" |
| wage_eur   | mixed  | "€320K", "€270K", null          |
| height_cm  | number | 170, 187, 175                   |
| dob        | date   | 1987-06-24, 1985-02-05          |
```

这样 LLM 可以：

- 看到 `wage_eur` 是 `mixed` 类型，知道需要用 SUBSTITUTE 清理
- 看到 `height_cm` 是 `number` 类型，可直接运算
- 看到 `dob` 是 `date` 类型，避免对其做算术运算

---

## 📝 更新日志

### 2026-01-30 改进

#### 1. 性能优化

- **预先缓存列数据**：`_execute_add_column` 中预先获取所有列数据，避免每行重复调用 `get_column()`
- **复用 FormulaEvaluator**：不再每行创建新实例，通过 `set_row_context()` 更新上下文

#### 2. 新增空值处理函数

添加以下函数支持空值判断：

| 函数       | 说明                            | Excel 对应    |
| ---------- | ------------------------------- | ------------- |
| `ISBLANK`  | 判断空值（None、NaN、空字符串） | `=ISBLANK()`  |
| `ISNA`     | 判断 #N/A 或 NaN                | `=ISNA()`     |
| `ISNUMBER` | 判断有效数值                    | `=ISNUMBER()` |
| `ISERROR`  | 判断错误值                      | `=ISERROR()`  |

#### 3. 修复聚合函数

- `AVERAGE`、`SUM`、`COUNT` 等函数现在正确排除 NaN 值
- 添加辅助函数 `_is_valid_number()` 和 `_is_blank()` 统一处理

#### 4. 显式支持 `var` 表达式类型

```python
# 之前：通过 hack 把变量放入 row_context
evaluator.row_context = self.variables.copy()

# 现在：显式支持
{"var": "avg_age"}  # 直接引用变量
```

#### 5. 新增 update_column 操作

添加 `update_column` 操作类型，用于更新现有列（如空值填充）：

```json
{
  "type": "update_column",
  "file_id": "xxx-xxx",
  "table": "train",
  "column": "Age",  // 要更新的列名
  "formula": {...}
}
```

| 操作            | 目标列     | 用途       |
| --------------- | ---------- | ---------- |
| `add_column`    | 必须不存在 | 新增计算列 |
| `update_column` | 必须已存在 | 修改现有列 |

#### 6. 添加表达式验证器

新增 `ExpressionValidator` 类，在解析阶段递归校验函数白名单：

```python
validator = ExpressionValidator(ROW_FUNCTIONS)
errors = validator.validate(formula)
```

#### 7. 改进错误处理

- 行级错误详细报告：`"部分行计算失败: 行 5: xxx; 行 12: yyy (共 10 个错误)"`
- 移除 `compute` 中的 `eval` 兼容代码，强制要求 JSON 格式

#### 8. 数据一致性改进

- `Executor` 不再直接修改 `Table`
- 新列数据统一通过 `ExecutionResult.new_columns` 返回
- 由调用方（Processor）统一调用 `apply_new_columns()` 应用修改

#### 9. 新增文本查找函数

添加以下函数支持文本位置查找：

| 函数     | 说明                         | Excel 对应  |
| -------- | ---------------------------- | ----------- |
| `FIND`   | 查找文本位置（区分大小写）   | `=FIND()`   |
| `SEARCH` | 查找文本位置（不区分大小写） | `=SEARCH()` |

**用途示例**：从 `"Braund, Mr. Owen"` 提取称谓 `"Mr"`

```json
{
  "func": "MID",
  "args": [
    { "col": "Name" },
    {
      "op": "+",
      "left": {
        "func": "FIND",
        "args": [{ "value": ", " }, { "col": "Name" }]
      },
      "right": { "value": 2 }
    },
    {
      "op": "-",
      "left": { "func": "FIND", "args": [{ "value": "." }, { "col": "Name" }] },
      "right": {
        "op": "+",
        "left": {
          "func": "FIND",
          "args": [{ "value": ", " }, { "col": "Name" }]
        },
        "right": { "value": 1 }
      }
    }
  ]
}
```

---

## 📊 数据分析模块（2026-04 新增）

### 10. **DataProfiler** - 数据画像提取器

**职责**：从 Table 提取结构化的统计特征

**核心方法**：

```python
def profile_table(self, table: Table, sample_count: int = 100) -> TableProfile
    """提取单表的画像"""

def profile_tables(self, tables: FileCollection, for_llm: bool = True) -> MultiTableProfile
    """提取多表画像，识别表关系"""

def format_multi_profile_for_llm(self, profile: MultiTableProfile) -> str
    """格式化多表画像为 LLM 友好文本"""
```

**画像内容**：

| 字段 | 说明 |
| ---- | ---- |
| `row_count`, `column_count` | 基本信息 |
| `columns[].type` | 列类型（number/text/date/boolean） |
| `columns[].min/max/mean/median/std` | 数值列统计 |
| `columns[].null_ratio` | 空值比例 |
| `columns[].top_values` | 高频值（文本列） |

---

### 11. **QualityChecker** - 数据质量检测器

**职责**：检测空值、重复、异常值、格式一致性

**核心方法**：

```python
def check_quality(self, table: Table) -> QualityReport
    """完整质量检测"""

def check_nulls(self, table: Table) -> Dict[str, float]
    """检测空值比例"""

def check_duplicates(self, table: Table) -> Dict
    """检测重复行"""

def check_anomalies(self, table: Table, column: str) -> List[Any]
    """检测数值列异常值（3σ原则）"""
```

---

### 12. **AnalysisFunctions** - 专项分析函数

**职责**：支持 L3 专项分析场景

**核心函数**：

| 函数 | 功能 |
| ---- | ---- |
| `pearson_correlation(x, y)` | 皮尔逊相关系数 |
| `correlation_analysis(df, col_a, col_b)` | 两列相关性分析 |
| `group_comparison(df, group_by, metrics)` | 分组对比 |
| `trend_analysis(df, date_col, value_col)` | 趋势分析 |
| `distribution_stats(df, column)` | 分布统计 |

---

### 13. **AnalysisStage** - 数据分析阶段

**职责**：协调数据分析流程（Pipeline Stage）

**支持的场景**：

| 场景 | 说明 |
| ---- | ---- |
| `l1_basic` | 基本概况 |
| `l1_quality` | 数据质量检测 |
| `l2_open` | 开放分析 |
| `l2_dimension` | 指定维度分析 |
| `l2_multi_table` | 多表联合 |
| `l3_correlation` | 相关性分析 |
| `l3_comparison` | 对比分析 |
| `l3_trend` | 趋势分析 |
| `l3_distribution` | 分布描述 |
| `l4_causation` | 原因归因 |
| `l4_relation_discovery` | 关系发现 |

---

**文档版本**：2026-04-09
**模块路径**：`apps/api/app/engine/`
