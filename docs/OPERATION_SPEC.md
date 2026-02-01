# LLM Excel 数据处理系统 - 技术规范 V2

## 一、系统概述

### 1.1 核心目标

构建一个 **"LLM 生成操作描述，解析器执行计算并生成 Excel 公式"** 的数据处理系统。

### 1.2 核心原则

- **LLM 只负责生成结构化的操作描述**（JSON 格式）
- **公式表达式使用 JSON 对象**：避免字符串解析问题，结构清晰
- **所有结果必须 100% 可被 Excel 复现验证**
- **中间层定义清晰**：操作类型、函数、参数一目了然
- **函数与 Excel 一一对应**：无自定义逻辑，确保可复现

### 1.3 系统架构

```
┌─────────────────────────────────────────────────────────────┐
│                      用户输入需求                            │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│               第一步：LLM 需求分析 (analyze)                 │
│    - 理解用户意图                                           │
│    - 分析涉及的表和字段                                      │
│    - 给出清晰的操作步骤（Excel 公式形式）                     │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│            第二步：LLM 生成 JSON 操作描述 (generate)         │
│    - 基于分析结果生成结构化操作                               │
│    - 输出 operations 数组                                   │
│    - formula/expression 使用 JSON 表达式对象                 │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                   解析与执行 (execute)                       │
│    - JSON 格式校验 + 操作类型校验 + 函数白名单校验            │
│    - 执行计算 (Python 实现)                                  │
│    - 生成 Excel 公式 (公式模板映射)                          │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                      输出结果                                │
│           - 计算值 / 新增列数据                              │
│           - 对应的 Excel 公式                                │
│           - 输出文件下载链接                                  │
└─────────────────────────────────────────────────────────────┘
```

**处理流程（Pipeline）**：`load → analyze → generate → execute → complete`

详见 [SSE_SPEC.md](./SSE_SPEC.md) 了解完整的事件协议。

### 1.4 两步 LLM 流程说明

采用两步 LLM 流程的原因：

1. **提高准确性**：先让 LLM 用自然语言分析需求，再生成结构化 JSON，降低直接生成 JSON 的出错率
2. **更好的推理**：第一步的分析结果作为上下文传递给第二步，帮助 LLM 更准确地生成操作
3. **可追溯性**：分析结果通过 SSE 流式返回给前端，用户可以看到 LLM 的思考过程

> **注意**：当前实现是自动化流程，两步在一次请求中连续完成。如果用户对结果不满意，可以通过继续会话（传入 `thread_id`）来修正需求。

#### 第一步：需求分析 (analyze)

**输入**：

- 用户需求（自然语言）
- 表结构信息

**输出**：

- 需求理解说明
- 操作步骤（Excel 公式形式）
- 涉及的表和字段

**示例输出**：

```
根据需求分析：

1. 需要在"贴现发生额明细"表中新增一列"卖断"
2. 判断逻辑：检查当前行的"票据(包)号"和"子票区间"是否在"卖断发生额明细"表中存在
3. Excel 公式思路：
   =IF(COUNTIFS(卖断发生额明细!A:A, A2, 卖断发生额明细!B:B, B2) > 0, "已卖断", "未卖断")
4. 结果：匹配到则显示"已卖断"，否则显示"未卖断"
```

#### 第二步：生成操作描述 (generate)

**输入**：

- 用户需求
- 第一步的分析结果
- 表结构信息

**输出**：

- JSON 格式的 operations 数组

---

## 二、操作类型定义

### 2.1 操作类型总览

| 操作类型        | 说明         | 输入           | 输出       | Excel 版本     |
| --------------- | ------------ | -------------- | ---------- | -------------- |
| `aggregate`     | 整列聚合     | 一列或多列数据 | 单个值     | 所有版本       |
| `add_column`    | 新增计算列   | 每行的单元格   | 新的一列   | 所有版本       |
| `update_column` | 更新现有列   | 每行的单元格   | 更新后的列 | 所有版本       |
| `compute`       | 标量运算     | 已有的变量     | 单个值     | 所有版本       |
| `filter`        | 筛选行       | 表 + 条件      | 筛选后的表 | **Excel 365+** |
| `sort`          | 排序行       | 表 + 排序规则  | 排序后的表 | **Excel 365+** |
| `group_by`      | 分组聚合     | 表 + 分组列    | 聚合结果表 | **Excel 365+** |
| `take`          | 取前/后N行   | 表 + 行数      | 截取后的表 | **Excel 365+** |
| `create_sheet`  | 创建新 Sheet | 配置           | 新 Sheet   | 内部抽象       |

---

### 2.2 aggregate（整列聚合）

对整列数据做聚合运算，输出**单个值**。

#### 结构定义

```json
{
  "type": "aggregate",
  "function": "聚合函数名",
  "table": "表名",
  "column": "聚合列（部分函数需要）",
  "condition_column": "条件列（条件函数需要）",
  "condition": "条件值（条件函数需要）",
  "as": "结果变量名"
}
```

#### 支持的聚合函数

| 函数        | 必需参数                                   | Excel 对应                   | 说明               |
| ----------- | ------------------------------------------ | ---------------------------- | ------------------ |
| `SUM`       | table, column                              | `=SUM(A:A)`                  | 求和               |
| `COUNT`     | table, column                              | `=COUNT(A:A)`                | 计数（数值单元格） |
| `COUNTA`    | table, column                              | `=COUNTA(A:A)`               | 计数（非空单元格） |
| `AVERAGE`   | table, column                              | `=AVERAGE(A:A)`              | 平均值             |
| `MIN`       | table, column                              | `=MIN(A:A)`                  | 最小值             |
| `MAX`       | table, column                              | `=MAX(A:A)`                  | 最大值             |
| `MEDIAN`    | table, column                              | `=MEDIAN(A:A)`               | 中位数             |
| `SUMIF`     | table, column, condition_column, condition | `=SUMIF(B:B,"条件",A:A)`     | 条件求和           |
| `COUNTIF`   | table, condition_column, condition         | `=COUNTIF(B:B,"条件")`       | 条件计数           |
| `AVERAGEIF` | table, column, condition_column, condition | `=AVERAGEIF(B:B,"条件",A:A)` | 条件平均           |

#### 条件值格式

| 类型     | 示例       | 说明           |
| -------- | ---------- | -------------- |
| 精确匹配 | `"已完成"` | 字符串相等     |
| 精确匹配 | `100`      | 数值相等       |
| 大于     | `">0"`     | 大于指定值     |
| 小于     | `"<100"`   | 小于指定值     |
| 大于等于 | `">=0"`    | 大于等于指定值 |
| 小于等于 | `"<=100"`  | 小于等于指定值 |
| 不等于   | `"<>0"`    | 不等于指定值   |

#### 示例

```json
// SUM - 求和
{
  "type": "aggregate",
  "function": "SUM",
  "table": "orders",
  "column": "amount",
  "as": "total"
}
// Excel: =SUM(订单表!C:C)

// SUMIF - 条件求和
{
  "type": "aggregate",
  "function": "SUMIF",
  "table": "orders",
  "column": "amount",
  "condition_column": "status",
  "condition": "已完成",
  "as": "completed_total"
}
// Excel: =SUMIF(订单表!B:B, "已完成", 订单表!C:C)

// COUNTIF - 条件计数
{
  "type": "aggregate",
  "function": "COUNTIF",
  "table": "orders",
  "condition_column": "status",
  "condition": "已完成",
  "as": "completed_count"
}
// Excel: =COUNTIF(订单表!B:B, "已完成")

// 数值条件
{
  "type": "aggregate",
  "function": "SUMIF",
  "table": "orders",
  "column": "amount",
  "condition_column": "amount",
  "condition": ">1000",
  "as": "large_order_total"
}
// Excel: =SUMIF(订单表!C:C, ">1000", 订单表!C:C)
```

---

### 2.3 add_column（新增计算列）

为表的**每一行**计算一个新值，形成**新的一列**。

#### 结构定义

```json
{
  "type": "add_column",
  "table": "表名",
  "name": "新列名",
  "formula": { 表达式对象 }
}
```

**重要：`formula` 是 JSON 对象，不是字符串！**

#### 表达式对象格式

##### 1. 字面量（常量值）

```json
{"value": 100}
{"value": "已完成"}
{"value": 0.9}
```

##### 2. 当前行列引用

引用当前行某列的值：

```json
{"col": "price"}
{"col": "amount"}
{"col": "票据(包)号"}
```

##### 3. 跨表列引用

引用另一张表的整列数据（用于 COUNTIFS、VLOOKUP 等）：

```json
{"ref": "卖断发生额明细.票据(包)号"}
{"ref": "customers.id"}
```

##### 4. 函数调用

```json
{
  "func": "函数名",
  "args": [参数1, 参数2, ...]
}
```

每个参数也是表达式对象（可嵌套）。

##### 5. 二元运算

```json
{
  "op": "运算符",
  "left": { 左操作数 },
  "right": { 右操作数 }
}
```

支持的运算符：

| 运算符 | 说明     | Excel |
| ------ | -------- | ----- |
| `+`    | 加法     | `+`   |
| `-`    | 减法     | `-`   |
| `*`    | 乘法     | `*`   |
| `/`    | 除法     | `/`   |
| `>`    | 大于     | `>`   |
| `<`    | 小于     | `<`   |
| `>=`   | 大于等于 | `>=`  |
| `<=`   | 小于等于 | `<=`  |
| `=`    | 等于     | `=`   |
| `<>`   | 不等于   | `<>`  |
| `&`    | 文本拼接 | `&`   |

#### 行级函数

| 函数         | 参数                               | Excel 对应                        | 说明                     |
| ------------ | ---------------------------------- | --------------------------------- | ------------------------ |
| `IF`         | 条件, 真值, 假值                   | `=IF(A2>100,"高","低")`           | 条件判断                 |
| `AND`        | 条件1, 条件2, ...                  | `=AND(A2>0,B2>0)`                 | 逻辑与                   |
| `OR`         | 条件1, 条件2, ...                  | `=OR(A2>0,B2>0)`                  | 逻辑或                   |
| `NOT`        | 条件                               | `=NOT(A2>0)`                      | 逻辑非                   |
| `ISBLANK`    | 值                                 | `=ISBLANK(A2)`                    | 判断空值                 |
| `ISNA`       | 值                                 | `=ISNA(A2)`                       | 判断#N/A                 |
| `ISNUMBER`   | 值                                 | `=ISNUMBER(A2)`                   | 判断数值                 |
| `ISERROR`    | 值                                 | `=ISERROR(A2)`                    | 判断错误                 |
| `COUNTIFS`   | 范围1, 条件1, 范围2, 条件2, ...    | `=COUNTIFS(A:A,B2,C:C,D2)`        | 多条件计数               |
| `VLOOKUP`    | 查找值, 查找范围, 列索引, 精确匹配 | `=VLOOKUP(A2,客户表!A:C,2,FALSE)` | 跨表查找                 |
| `IFERROR`    | 表达式, 错误值                     | `=IFERROR(A2/B2,0)`               | 错误处理                 |
| `ROUND`      | 数值, 小数位                       | `=ROUND(A2,2)`                    | 四舍五入                 |
| `ABS`        | 数值                               | `=ABS(A2)`                        | 绝对值                   |
| `LEFT`       | 文本, 字符数                       | `=LEFT(A2,3)`                     | 左截取                   |
| `RIGHT`      | 文本, 字符数                       | `=RIGHT(A2,3)`                    | 右截取                   |
| `MID`        | 文本, 起始位, 字符数               | `=MID(A2,2,3)`                    | 中间截取                 |
| `FIND`       | 查找文本, 源文本, [起始位置]       | `=FIND(",",A2)`                   | 查找位置（区分大小写）   |
| `SEARCH`     | 查找文本, 源文本, [起始位置]       | `=SEARCH(",",A2)`                 | 查找位置（不区分大小写） |
| `SUBSTITUTE` | 文本, 旧文本, 新文本, [第N次]      | `=SUBSTITUTE(A2,"€","")`          | 替换文本                 |
| `LEN`        | 文本                               | `=LEN(A2)`                        | 文本长度                 |
| `TRIM`       | 文本                               | `=TRIM(A2)`                       | 去除空格                 |
| `UPPER`      | 文本                               | `=UPPER(A2)`                      | 转大写                   |
| `LOWER`      | 文本                               | `=LOWER(A2)`                      | 转小写                   |
| `PROPER`     | 文本                               | `=PROPER(A2)`                     | 首字母大写               |
| `TEXT`       | 数值, 格式                         | `=TEXT(A2,"0.00")`                | 数值格式化               |
| `VALUE`      | 文本                               | `=VALUE(A2)`                      | 文本转数值               |

#### 示例

```json
// 简单算术：price * 0.9
{
  "type": "add_column",
  "table": "orders",
  "name": "折扣价",
  "formula": {
    "op": "*",
    "left": {"col": "price"},
    "right": {"value": 0.9}
  }
}
// Excel 公式模板: =C{row}*0.9

// 条件判断：IF(amount > 1000, "高", "低")
{
  "type": "add_column",
  "table": "orders",
  "name": "等级",
  "formula": {
    "func": "IF",
    "args": [
      {
        "op": ">",
        "left": {"col": "amount"},
        "right": {"value": 1000}
      },
      {"value": "高"},
      {"value": "低"}
    ]
  }
}
// Excel 公式模板: =IF(D{row}>1000,"高","低")

// 多条件：IF(AND(amount > 500, status = "已完成"), "是", "否")
{
  "type": "add_column",
  "table": "orders",
  "name": "优质订单",
  "formula": {
    "func": "IF",
    "args": [
      {
        "func": "AND",
        "args": [
          {
            "op": ">",
            "left": {"col": "amount"},
            "right": {"value": 500}
          },
          {
            "op": "=",
            "left": {"col": "status"},
            "right": {"value": "已完成"}
          }
        ]
      },
      {"value": "是"},
      {"value": "否"}
    ]
  }
}
// Excel 公式模板: =IF(AND(D{row}>500,B{row}="已完成"),"是","否")

// COUNTIFS 跨表匹配：检查票据是否已卖断
{
  "type": "add_column",
  "table": "贴现发生额明细",
  "name": "卖断",
  "formula": {
    "func": "IF",
    "args": [
      {
        "op": ">",
        "left": {
          "func": "COUNTIFS",
          "args": [
            {"ref": "卖断发生额明细.票据(包)号"},
            {"col": "票据(包)号"},
            {"ref": "卖断发生额明细.子票区间"},
            {"col": "子票区间"}
          ]
        },
        "right": {"value": 0}
      },
      {"value": "已卖断"},
      {"value": "未卖断"}
    ]
  }
}
// Excel 公式模板: =IF(COUNTIFS(卖断表!A:A,A{row},卖断表!B:B,B{row})>0,"已卖断","未卖断")

// 跨表查找
{
  "type": "add_column",
  "table": "orders",
  "name": "客户名称",
  "formula": {
    "func": "VLOOKUP",
    "args": [
      {"col": "customer_id"},
      {"ref": "customers.id"},
      {"value": 2},
      {"value": false}
    ]
  }
}
// Excel 公式模板: =VLOOKUP(A{row},客户表!A:C,2,FALSE)

// 错误处理
{
  "type": "add_column",
  "table": "orders",
  "name": "单价",
  "formula": {
    "func": "IFERROR",
    "args": [
      {
        "op": "/",
        "left": {"col": "amount"},
        "right": {"col": "quantity"}
      },
      {"value": 0}
    ]
  }
}
// Excel 公式模板: =IFERROR(D{row}/E{row},0)

// 文本拼接：customer_name & "-" & product_name
{
  "type": "add_column",
  "table": "orders",
  "name": "完整描述",
  "formula": {
    "op": "&",
    "left": {
      "op": "&",
      "left": {"col": "customer_name"},
      "right": {"value": "-"}
    },
    "right": {"col": "product_name"}
  }
}
// Excel 公式模板: =A{row}&"-"&B{row}

// 字符串提取：从 Name 列（如 "Braund, Mr. Owen"）提取称谓（如 "Mr"）
{
  "type": "add_column",
  "file_id": "xxx-xxx",
  "table": "train",
  "name": "Title",
  "formula": {
    "func": "MID",
    "args": [
      {"col": "Name"},
      {"op": "+",
       "left": {"func": "FIND", "args": [{"value": ", "}, {"col": "Name"}]},
       "right": {"value": 2}
      },
      {"op": "-",
       "left": {"func": "FIND", "args": [{"value": "."}, {"col": "Name"}]},
       "right": {"op": "+",
                 "left": {"func": "FIND", "args": [{"value": ", "}, {"col": "Name"}]},
                 "right": {"value": 1}
       }
      }
    ]
  }
}
// Excel 公式模板: =MID(D{row}, FIND(", ", D{row})+2, FIND(".", D{row})-FIND(", ", D{row})-1)

// 空值填充：用平均值填充 Age 列的空值
// 使用 update_column 更新现有列
{
  "type": "aggregate",
  "function": "AVERAGE",
  "file_id": "xxx-xxx",
  "table": "train",
  "column": "Age",
  "as": "avg_age"
}
{
  "type": "update_column",
  "file_id": "xxx-xxx",
  "table": "train",
  "column": "Age",  // 要更新的列名
  "formula": {
    "func": "IF",
    "args": [
      {"func": "ISBLANK", "args": [{"col": "Age"}]},
      {"var": "avg_age"},
      {"col": "Age"}
    ]
  }
}
// Excel 公式模板: =IF(ISBLANK(F{row}), $M$1, F{row})
// 其中 $M$1 存放平均值
```

---

### 2.4 update_column（更新现有列）

更新表中**已存在的列**，用于空值填充、数据修正等场景。

#### 结构定义

```json
{
  "type": "update_column",
  "file_id": "文件ID",
  "table": "表名",
  "column": "要更新的列名",
  "formula": { 表达式对象 }
}
```

**与 add_column 的区别**：

| 特性     | add_column     | update_column   |
| -------- | -------------- | --------------- |
| 目标列   | 必须不存在     | 必须已存在      |
| 用途     | 新增计算列     | 修改现有列      |
| 典型场景 | 添加"折扣价"列 | 填充 Age 列空值 |

#### 示例

```json
// 空值填充：用平均值填充 Age 列的空值
{
  "type": "update_column",
  "file_id": "xxx-xxx",
  "table": "train",
  "column": "Age",
  "formula": {
    "func": "IF",
    "args": [
      {"func": "ISBLANK", "args": [{"col": "Age"}]},
      {"var": "avg_age"},
      {"col": "Age"}
    ]
  }
}
// Excel 公式: =IF(ISBLANK(F2), $M$1, F2)

// 数据修正：将负数改为 0
{
  "type": "update_column",
  "file_id": "xxx-xxx",
  "table": "orders",
  "column": "amount",
  "formula": {
    "func": "IF",
    "args": [
      {"op": "<", "left": {"col": "amount"}, "right": {"value": 0}},
      {"value": 0},
      {"col": "amount"}
    ]
  }
}
// Excel 公式: =IF(D2<0, 0, D2)
```

---

### 2.5 compute（标量运算）

对**已有变量**做运算，输出**单个值**。用于组合多个聚合结果。

#### 结构定义

```json
{
  "type": "compute",
  "expression": { 表达式对象 },
  "as": "结果变量名"
}
```

**重要：`expression` 是 JSON 对象，不是字符串！**

#### expression 语法规则

使用与 `add_column` 相同的表达式对象格式：

- **变量引用**：`{"var": "变量名"}` - 引用前面操作通过 `as` 定义的变量
- **字面量**：`{"value": 100}` - 数字或字符串常量
- **二元运算**：`{"op": "+", "left": {...}, "right": {...}}`
- **函数调用**：`{"func": "ROUND", "args": [...]}`

可用函数：`ROUND`, `ABS`, `MAX`, `MIN`

#### 示例

```json
// 简单运算：order_total - refund_total
{
  "type": "compute",
  "expression": {
    "op": "-",
    "left": {"var": "order_total"},
    "right": {"var": "refund_total"}
  },
  "as": "net_income"
}

// 四舍五入：ROUND(net_income, 2)
{
  "type": "compute",
  "expression": {
    "func": "ROUND",
    "args": [
      {"var": "net_income"},
      {"value": 2}
    ]
  },
  "as": "result"
}

// 百分比计算：completed_count / total_count * 100
{
  "type": "compute",
  "expression": {
    "op": "*",
    "left": {
      "op": "/",
      "left": {"var": "completed_count"},
      "right": {"var": "total_count"}
    },
    "right": {"value": 100}
  },
  "as": "completion_rate"
}

// 复合运算：ROUND(ABS(income - expense) / income * 100, 2)
{
  "type": "compute",
  "expression": {
    "func": "ROUND",
    "args": [
      {
        "op": "*",
        "left": {
          "op": "/",
          "left": {
            "func": "ABS",
            "args": [
              {
                "op": "-",
                "left": {"var": "income"},
                "right": {"var": "expense"}
              }
            ]
          },
          "right": {"var": "income"}
        },
        "right": {"value": 100}
      },
      {"value": 2}
    ]
  },
  "as": "variance_rate"
}
```

---

### 2.6 filter（筛选行）⚠️ Excel 365+

按条件筛选行，结果输出到新 Sheet 或原地替换。对应 Excel 365 的 `FILTER` 函数。

#### 结构定义

```json
{
  "type": "filter",
  "file_id": "文件ID",
  "table": "源表名",
  "conditions": [{ "column": "列名", "op": "运算符", "value": "值" }],
  "logic": "AND | OR",
  "output": {
    "type": "new_sheet | in_place",
    "name": "新Sheet名（new_sheet时必需）"
  }
}
```

#### 字段说明

| 字段                  | 类型   | 必需 | 说明                                                |
| --------------------- | ------ | ---- | --------------------------------------------------- |
| `file_id`             | string | ✅   | 源文件 ID                                           |
| `table`               | string | ✅   | 源 Sheet 名称                                       |
| `conditions`          | array  | ✅   | 筛选条件数组                                        |
| `conditions[].column` | string | ✅   | 条件列名                                            |
| `conditions[].op`     | string | ✅   | 运算符：`=`, `<>`, `>`, `<`, `>=`, `<=`, `contains` |
| `conditions[].value`  | any    | ✅   | 比较值                                              |
| `logic`               | string | ❌   | 多条件逻辑，默认 `"AND"`                            |
| `output`              | object | ✅   | 输出目标                                            |
| `output.type`         | string | ✅   | `"new_sheet"` 或 `"in_place"`                       |
| `output.name`         | string | ❌   | 新 Sheet 名称（type 为 new_sheet 时必需）           |

#### 示例

```json
// 筛选生还的女性乘客
{
  "type": "filter",
  "file_id": "xxx-xxx",
  "table": "train",
  "conditions": [
    { "column": "Sex", "op": "=", "value": "female" },
    { "column": "Survived", "op": "=", "value": 1 }
  ],
  "logic": "AND",
  "output": {
    "type": "new_sheet",
    "name": "生还女性"
  }
}
// Excel: =FILTER(train!A:L, (train!E:E="female") * (train!B:B=1))
```

---

### 2.7 sort（排序行）⚠️ Excel 365+

按一列或多列排序。对应 Excel 365 的 `SORT` 函数。

#### 结构定义

```json
{
  "type": "sort",
  "file_id": "文件ID",
  "table": "表名",
  "by": [{ "column": "列名", "order": "asc | desc" }],
  "output": {
    "type": "in_place | new_sheet",
    "name": "新Sheet名（可选）"
  }
}
```

#### 字段说明

| 字段          | 类型   | 必需 | 说明                                     |
| ------------- | ------ | ---- | ---------------------------------------- |
| `file_id`     | string | ✅   | 文件 ID                                  |
| `table`       | string | ✅   | Sheet 名称                               |
| `by`          | array  | ✅   | 排序规则数组（支持多列排序）             |
| `by[].column` | string | ✅   | 排序列名                                 |
| `by[].order`  | string | ❌   | `"asc"`（升序，默认）或 `"desc"`（降序） |
| `output`      | object | ❌   | 输出目标，默认 `{"type": "in_place"}`    |

#### 示例

```json
// 按年龄降序排序
{
  "type": "sort",
  "file_id": "xxx-xxx",
  "table": "生还女性",
  "by": [{ "column": "Age", "order": "desc" }],
  "output": { "type": "in_place" }
}
// Excel: =SORT(生还女性!A:L, 6, -1)
// 第2个参数：列索引（Age 是第6列）
// 第3个参数：1=升序，-1=降序
```

---

### 2.8 group_by（分组聚合）⚠️ Excel 365+

按分组列聚合计算，生成汇总表。对应 Excel 365 的 `GROUPBY` 函数。

> ⚠️ `GROUPBY` 是 2023年9月才加入的函数，需要最新版 Excel 365。

#### 结构定义

```json
{
  "type": "group_by",
  "file_id": "文件ID",
  "table": "源表名",
  "group_columns": ["分组列1", "分组列2"],
  "aggregations": [
    {
      "column": "聚合列",
      "function": "聚合函数",
      "as": "结果列名"
    }
  ],
  "output": {
    "type": "new_sheet",
    "name": "新Sheet名"
  }
}
```

#### 字段说明

| 字段                      | 类型   | 必需 | 说明                                              |
| ------------------------- | ------ | ---- | ------------------------------------------------- |
| `file_id`                 | string | ✅   | 文件 ID                                           |
| `table`                   | string | ✅   | 源 Sheet 名称                                     |
| `group_columns`           | array  | ✅   | 分组列名数组                                      |
| `aggregations`            | array  | ✅   | 聚合计算数组                                      |
| `aggregations[].column`   | string | ✅   | 要聚合的列                                        |
| `aggregations[].function` | string | ✅   | 聚合函数：`SUM`, `COUNT`, `AVERAGE`, `MIN`, `MAX` |
| `aggregations[].as`       | string | ✅   | 结果列名                                          |
| `output`                  | object | ✅   | 输出目标（必须是 new_sheet）                      |

#### 示例

```json
// 按船舱等级计算平均票价
{
  "type": "group_by",
  "file_id": "xxx-xxx",
  "table": "train",
  "group_columns": ["Pclass"],
  "aggregations": [
    { "column": "Fare", "function": "AVERAGE", "as": "Average_Fare" }
  ],
  "output": {
    "type": "new_sheet",
    "name": "船舱统计"
  }
}
// Excel: =GROUPBY(train!C:C, train!J:J, AVERAGE)
```

---

### 2.9 create_sheet（创建新 Sheet）

创建新的 Sheet。这是**内部抽象操作**，Excel 中无对应函数。

通常由 `filter`/`sort`/`group_by` 的 output 隐式触发，很少直接使用。

#### 结构定义

```json
{
  "type": "create_sheet",
  "file_id": "文件ID",
  "name": "新Sheet名",
  "source": {
    "type": "empty | copy | reference",
    "table": "源表名（copy/reference时需要）"
  },
  "columns": ["列名1", "列名2"]
}
```

#### 字段说明

| 字段           | 类型   | 必需 | 说明                                                           |
| -------------- | ------ | ---- | -------------------------------------------------------------- |
| `file_id`      | string | ✅   | 目标文件 ID                                                    |
| `name`         | string | ✅   | 新 Sheet 名称                                                  |
| `source`       | object | ❌   | 数据来源，默认 `{"type": "empty"}`                             |
| `source.type`  | string | ✅   | `"empty"`（空表）、`"copy"`（复制）、`"reference"`（引用结构） |
| `source.table` | string | ❌   | 源表名（copy/reference 时必需）                                |
| `columns`      | array  | ❌   | 列定义（empty 时可用于预定义列头）                             |

#### source.type 说明

| 类型        | 说明                 | Excel 对应        |
| ----------- | -------------------- | ----------------- |
| `empty`     | 创建空表，可指定列头 | 手动创建工作表    |
| `copy`      | 复制现有表的全部数据 | 右键 → 移动或复制 |
| `reference` | 创建空表但继承列结构 | 无                |

#### 示例

```json
// 创建空表
{
  "type": "create_sheet",
  "file_id": "xxx-xxx",
  "name": "统计结果",
  "source": {"type": "empty"},
  "columns": ["类别", "数量", "占比"]
}

// 复制现有表
{
  "type": "create_sheet",
  "file_id": "xxx-xxx",
  "name": "train_backup",
  "source": {
    "type": "copy",
    "table": "train"
  }
}
```

---

### 2.10 take（取前/后 N 行）⚠️ Excel 365+

从表的开头或末尾提取指定数量的行。对应 Excel 365 的 `TAKE` 函数。

常用于配合 `group_by` + `sort` 实现 Top N 统计。

#### 结构定义

```json
{
  "type": "take",
  "file_id": "文件ID",
  "table": "表名",
  "rows": 10,
  "output": {
    "type": "in_place | new_sheet",
    "name": "新Sheet名（可选）"
  }
}
```

#### 字段说明

| 字段      | 类型   | 必需 | 说明                                  |
| --------- | ------ | ---- | ------------------------------------- |
| `file_id` | string | ✅   | 文件 ID                               |
| `table`   | string | ✅   | Sheet 名称                            |
| `rows`    | int    | ✅   | 取行数量（正数取前N行，负数取后N行）  |
| `output`  | object | ❌   | 输出目标，默认 `{"type": "in_place"}` |

#### rows 参数说明

| 值    | 说明             | Excel 对应        |
| ----- | ---------------- | ----------------- |
| `10`  | 从开头取前 10 行 | `=TAKE(A:Z, 10)`  |
| `-10` | 从末尾取后 10 行 | `=TAKE(A:Z, -10)` |

#### 示例

```json
// 取前 10 行
{
  "type": "take",
  "file_id": "xxx-xxx",
  "table": "国家统计",
  "rows": 10,
  "output": {"type": "in_place"}
}
// Excel: =TAKE(国家统计!A:B, 10)

// 取后 5 行，输出到新 Sheet
{
  "type": "take",
  "file_id": "xxx-xxx",
  "table": "销售数据",
  "rows": -5,
  "output": {
    "type": "new_sheet",
    "name": "最近5条"
  }
}
// Excel: =TAKE(销售数据!A:Z, -5)

// 典型用法：Top N 统计（group_by + sort + take）
// 需求：统计每个国家的内容数量，取前10名
[
  {
    "type": "group_by",
    "file_id": "xxx",
    "table": "netflix_titles",
    "group_columns": ["country"],
    "aggregations": [{"column": "show_id", "function": "COUNT", "as": "数量"}],
    "output": {"type": "new_sheet", "name": "国家统计"}
  },
  {
    "type": "sort",
    "file_id": "xxx",
    "table": "国家统计",
    "by": [{"column": "数量", "order": "desc"}],
    "output": {"type": "in_place"}
  },
  {
    "type": "take",
    "file_id": "xxx",
    "table": "国家统计",
    "rows": 10,
    "output": {"type": "in_place"}
  }
]
// 等效 Excel 公式：=TAKE(SORT(GROUPBY(netflix!F:F, netflix!A:A, COUNT), 2, -1), 10)
```

---

## 三、JSON 输出格式

### 3.1 完整结构

```json
{
  "operations": [
    { "type": "aggregate", ... },
    { "type": "aggregate", ... },
    { "type": "compute", ... },
    { "type": "add_column", ... }
  ]
}
```

### 3.2 执行顺序

operations 数组中的操作**按顺序执行**：

1. 前面的 `aggregate` 定义的变量，可以被后面的 `compute` 引用
2. `add_column` 操作独立执行，不依赖变量

### 3.3 完整示例

**需求**：

1. 计算已完成订单的净收入（订单金额 - 退款金额），保留 2 位小数
2. 给订单表新增"折扣价"和"等级"两列

**LLM 输出**：

```json
{
  "operations": [
    {
      "type": "aggregate",
      "function": "SUMIF",
      "table": "orders",
      "column": "amount",
      "condition_column": "status",
      "condition": "已完成",
      "as": "order_total"
    },
    {
      "type": "aggregate",
      "function": "SUM",
      "table": "refunds",
      "column": "amount",
      "as": "refund_total"
    },
    {
      "type": "compute",
      "expression": {
        "op": "-",
        "left": { "var": "order_total" },
        "right": { "var": "refund_total" }
      },
      "as": "net_income"
    },
    {
      "type": "compute",
      "expression": {
        "func": "ROUND",
        "args": [{ "var": "net_income" }, { "value": 2 }]
      },
      "as": "result"
    },
    {
      "type": "add_column",
      "table": "orders",
      "name": "折扣价",
      "formula": {
        "op": "*",
        "left": { "col": "price" },
        "right": { "value": 0.9 }
      }
    },
    {
      "type": "add_column",
      "table": "orders",
      "name": "等级",
      "formula": {
        "func": "IF",
        "args": [
          {
            "op": ">",
            "left": { "col": "amount" },
            "right": { "value": 1000 }
          },
          { "value": "高" },
          { "value": "低" }
        ]
      }
    }
  ]
}
```

---

## 四、解析器规范

### 4.1 职责

```
JSON 操作描述
     ↓
┌─────────────────────────────────────────┐
│              解析器                      │
├─────────────────────────────────────────┤
│ 1. JSON 格式校验                         │
│    - 是否为有效 JSON                     │
│    - 是否包含 operations 数组            │
│                                         │
│ 2. 操作校验                              │
│    - type 是否为 aggregate/add_column/compute │
│    - 必需字段是否存在                     │
│    - function 是否在白名单中              │
│                                         │
│ 3. 执行计算                              │
│    - 按顺序执行每个操作                   │
│    - 维护变量上下文                       │
│    - 处理新增列                          │
│                                         │
│ 4. 生成 Excel 公式                       │
│    - 根据操作类型生成对应公式             │
│    - 处理列名到单元格引用的映射           │
└─────────────────────────────────────────┘
     ↓
输出：计算结果 + Excel 公式
```

### 4.2 校验规则

#### 操作类型校验

```python
VALID_TYPES = {"aggregate", "add_column", "compute"}
```

#### aggregate 必需字段

| 函数                                  | 必需字段                                                       |
| ------------------------------------- | -------------------------------------------------------------- |
| SUM, COUNT, COUNTA, AVERAGE, MIN, MAX | type, function, table, column, as                              |
| SUMIF, AVERAGEIF                      | type, function, table, column, condition_column, condition, as |
| COUNTIF                               | type, function, table, condition_column, condition, as         |

#### add_column 必需字段

```
type, table, name, formula
```

#### compute 必需字段

```
type, expression, as
```

### 4.3 函数白名单

```python
# 聚合函数（用于 aggregate）
AGGREGATE_FUNCTIONS = {
    "SUM", "COUNT", "COUNTA", "AVERAGE", "MIN", "MAX", "MEDIAN",
    "SUMIF", "COUNTIF", "AVERAGEIF"
}

# 行级函数（用于 add_column 的 formula）
ROW_FUNCTIONS = {
    # 逻辑
    "IF", "AND", "OR", "NOT",
    # 空值判断
    "ISBLANK", "ISNA", "ISNUMBER", "ISERROR",
    # 查找与匹配
    "VLOOKUP", "COUNTIFS",
    # 错误处理
    "IFERROR",
    # 数值
    "ROUND", "ABS",
    # 文本
    "LEFT", "RIGHT", "MID", "LEN", "TRIM", "UPPER", "LOWER", "PROPER",
    "CONCAT", "TEXT", "VALUE", "SUBSTITUTE",
    # 文本查找
    "FIND", "SEARCH"
}

# 标量函数（用于 compute 的 expression）
SCALAR_FUNCTIONS = {
    "ROUND", "ABS", "MAX", "MIN"
}
```

---

## 五、Excel 公式生成规则

### 5.1 列名到单元格引用映射

解析器需要维护每个表的列名与 Excel 列号的映射：

```python
# 示例：订单表
column_mapping = {
    "orders": {
        "order_id": "A",
        "status": "B",
        "amount": "C",
        "price": "D",
        "customer_id": "E"
    },
    "customers": {
        "id": "A",
        "name": "B",
        "level": "C"
    }
}
```

### 5.2 aggregate 公式生成

| 函数      | 公式模板                                                     |
| --------- | ------------------------------------------------------------ |
| SUM       | `=SUM(表名!列:列)`                                           |
| COUNT     | `=COUNT(表名!列:列)`                                         |
| AVERAGE   | `=AVERAGE(表名!列:列)`                                       |
| MIN       | `=MIN(表名!列:列)`                                           |
| MAX       | `=MAX(表名!列:列)`                                           |
| SUMIF     | `=SUMIF(表名!条件列:条件列, "条件", 表名!求和列:求和列)`     |
| COUNTIF   | `=COUNTIF(表名!条件列:条件列, "条件")`                       |
| AVERAGEIF | `=AVERAGEIF(表名!条件列:条件列, "条件", 表名!平均列:平均列)` |

### 5.3 add_column 公式生成

add_column 为表的**每一行**生成公式。解析器输出**公式模板**，用 `{row}` 表示行号占位符：

```
formula: "price * 0.9"
公式模板: =D{row}*0.9

实际应用时：
  第2行: =D2*0.9
  第3行: =D3*0.9
  第4行: =D4*0.9
  ... (下拉填充到所有数据行)
```

规则：

1. 列名 → 对应列号 + `{row}` 占位符（如 `price` → `D{row}`）
2. 比较运算符 `==` → `=`，`!=` → `<>`
3. 字符串用双引号
4. 第 1 行通常是表头，数据从第 2 行开始

### 5.4 compute 公式生成

compute 的结果通常放在汇总区域，引用其他计算结果的单元格：

```
假设：order_total 在 B1，refund_total 在 B2
expression: "order_total - refund_total"
公式: =B1-B2
```

---

## 六、系统提示词

系统采用两步 LLM 流程，对应两个提示词。

### 6.1 第一步：需求分析提示词

```text
# 角色
你是一个 Excel 数据处理专家。

## 任务
分析用户的数据处理需求，给出清晰的操作步骤（Excel 公式形式）。

## 注意事项
1. 用户需求中可能会存在简称，公式中使用完整的表名，不要使用简称
2. 使用尽量简洁少的步骤实现
3. 明确指出涉及的表和字段
4. 给出对应的 Excel 公式思路

## 当前表结构信息
（系统自动注入表结构）
```

**示例输出**：

```
根据需求分析：

1. 需要在"贴现发生额明细"表中新增一列"卖断"
2. 判断逻辑：检查当前行的"票据(包)号"和"子票区间"是否在"卖断发生额明细"表中存在
3. Excel 公式思路：
   =IF(COUNTIFS(卖断发生额明细!A:A, A2, 卖断发生额明细!B:B, B2) > 0, "已卖断", "未卖断")
4. 结果：匹配到则显示"已卖断"，否则显示"未卖断"
```

### 6.2 第二步：生成操作描述提示词

```text
你是一个数据处理助手。

## 任务
根据需求分析结果，生成 JSON 格式的操作描述。

## 输出格式

{
  "operations": [
    { 操作1 },
    { 操作2 }
  ]
}

## 操作类型

### 1. aggregate - 整列聚合

{
  "type": "aggregate",
  "function": "SUM | COUNT | AVERAGE | MIN | MAX | SUMIF | COUNTIF",
  "table": "表名",
  "column": "聚合列",
  "condition_column": "条件列（SUMIF/COUNTIF需要）",
  "condition": "条件值",
  "as": "结果变量名"
}

### 2. add_column - 新增计算列

**重要：formula 是 JSON 对象，不是字符串！**

{
  "type": "add_column",
  "table": "表名",
  "name": "新列名",
  "formula": { 表达式对象 }
}

### 3. compute - 标量运算

{
  "type": "compute",
  "expression": { 表达式对象 },
  "as": "结果变量名"
}

## 表达式对象格式

### 1. 字面量 - 常量值
{"value": 100}
{"value": "已完成"}

### 2. 列引用 - 当前行的列值
{"col": "列名"}

### 3. 跨表列引用 - 另一张表的整列数据
{"ref": "表名.列名"}

### 4. 变量引用 - 引用前面定义的变量（用于 compute）
{"var": "变量名"}

### 5. 函数调用
{
  "func": "函数名",
  "args": [参数1, 参数2, ...]
}

可用函数：IF, AND, OR, NOT, COUNTIFS, VLOOKUP, IFERROR, ROUND, ABS, LEFT, RIGHT, MID, LEN, TRIM, UPPER, LOWER, TEXT, VALUE

### 6. 二元运算
{
  "op": "运算符",
  "left": { 左操作数 },
  "right": { 右操作数 }
}

可用运算符：+, -, *, /, >, <, >=, <=, =, <>, &

## 完整示例

### 示例：COUNTIFS 跨表匹配

需求：检查贴现表中的票据是否在卖断表中存在

{
  "operations": [
    {
      "type": "add_column",
      "table": "贴现发生额明细",
      "name": "卖断",
      "formula": {
        "func": "IF",
        "args": [
          {
            "op": ">",
            "left": {
              "func": "COUNTIFS",
              "args": [
                {"ref": "卖断发生额明细.票据(包)号"},
                {"col": "票据(包)号"},
                {"ref": "卖断发生额明细.子票区间"},
                {"col": "子票区间"}
              ]
            },
            "right": {"value": 0}
          },
          {"value": "已卖断"},
          {"value": "未卖断"}
        ]
      }
    }
  ]
}

## 输出要求

- 只输出 JSON，不要 markdown 代码块
- formula 和 expression 必须是 JSON 对象，不是字符串
- 如果无法处理，输出：{"error": "UNSUPPORTED", "reason": "原因"}

## 需求分析结果
（系统自动注入第一步的分析结果）
```

---

## 七、模块清单

| 模块           | 文件                 | 说明                             |
| -------------- | -------------------- | -------------------------------- |
| 数据模型       | `models.py`          | Table/Column/Cell 类型定义       |
| JSON 解析器    | `parser.py`          | 解析 JSON、校验格式、校验白名单  |
| 函数库         | `functions.py`       | 聚合函数、行级函数、标量函数实现 |
| 执行引擎       | `executor.py`        | 按顺序执行操作、JSON 表达式求值  |
| Excel 公式生成 | `excel_generator.py` | JSON 表达式 → Excel 公式映射     |
| LLM 客户端     | `llm_client.py`      | 调用 LLM API（两步流程）         |
| 系统提示词     | `prompt.py`          | 需求分析提示词 + 操作生成提示词  |
| 主入口         | `main.py`            | 应用主入口、两步流程控制         |

---

## 八、开发顺序建议

```
1. models.py          # 基础数据模型
   ↓
2. parser.py          # JSON 解析 + 校验
   ↓
3. functions.py       # 函数实现（聚合、行级、标量）
   ↓
4. executor.py        # 执行引擎 + JSON 表达式求值器
   ↓
5. excel_generator.py # Excel 公式生成
   ↓
6. prompt.py          # 两步提示词
   ↓
7. llm_client.py      # LLM 客户端（两步调用）
   ↓
8. main.py            # 集成 + 两步流程控制
```

---

## 九、函数速查表

### 聚合函数（aggregate）

| 函数      | 参数                                       | Excel        | 说明         |
| --------- | ------------------------------------------ | ------------ | ------------ |
| SUM       | table, column                              | =SUM()       | 求和         |
| COUNT     | table, column                              | =COUNT()     | 计数（数值） |
| COUNTA    | table, column                              | =COUNTA()    | 计数（非空） |
| AVERAGE   | table, column                              | =AVERAGE()   | 平均值       |
| MIN       | table, column                              | =MIN()       | 最小值       |
| MAX       | table, column                              | =MAX()       | 最大值       |
| MEDIAN    | table, column                              | =MEDIAN()    | 中位数       |
| SUMIF     | table, column, condition_column, condition | =SUMIF()     | 条件求和     |
| COUNTIF   | table, condition_column, condition         | =COUNTIF()   | 条件计数     |
| AVERAGEIF | table, column, condition_column, condition | =AVERAGEIF() | 条件平均     |

### 行级函数（add_column formula）

| 函数       | 参数                               | Excel         | 说明                     |
| ---------- | ---------------------------------- | ------------- | ------------------------ |
| IF         | 条件, 真值, 假值                   | =IF()         | 条件判断                 |
| AND        | 条件1, 条件2, ...                  | =AND()        | 逻辑与                   |
| OR         | 条件1, 条件2, ...                  | =OR()         | 逻辑或                   |
| NOT        | 条件                               | =NOT()        | 逻辑非                   |
| ISBLANK    | 值                                 | =ISBLANK()    | 判断空值                 |
| ISNA       | 值                                 | =ISNA()       | 判断#N/A                 |
| ISNUMBER   | 值                                 | =ISNUMBER()   | 判断数值                 |
| ISERROR    | 值                                 | =ISERROR()    | 判断错误                 |
| COUNTIFS   | 范围1, 条件1, 范围2, 条件2, ...    | =COUNTIFS()   | 多条件计数               |
| VLOOKUP    | 查找值, 查找范围, 列索引, 精确匹配 | =VLOOKUP()    | 跨表查找                 |
| IFERROR    | 表达式, 错误值                     | =IFERROR()    | 错误处理                 |
| ROUND      | 数值, 位数                         | =ROUND()      | 四舍五入                 |
| ABS        | 数值                               | =ABS()        | 绝对值                   |
| LEFT       | 文本, 字符数                       | =LEFT()       | 左截取                   |
| RIGHT      | 文本, 字符数                       | =RIGHT()      | 右截取                   |
| MID        | 文本, 起始位, 字符数               | =MID()        | 中截取                   |
| FIND       | 查找文本, 源文本, [起始位置]       | =FIND()       | 查找位置（区分大小写）   |
| SEARCH     | 查找文本, 源文本, [起始位置]       | =SEARCH()     | 查找位置（不区分大小写） |
| SUBSTITUTE | 文本, 旧文本, 新文本, [第N次]      | =SUBSTITUTE() | 替换文本                 |
| LEN        | 文本                               | =LEN()        | 长度                     |
| TRIM       | 文本                               | =TRIM()       | 去空格                   |
| UPPER      | 文本                               | =UPPER()      | 转大写                   |
| LOWER      | 文本                               | =LOWER()      | 转小写                   |
| PROPER     | 文本                               | =PROPER()     | 首字母大写               |
| TEXT       | 数值, 格式                         | =TEXT()       | 格式化                   |
| VALUE      | 文本                               | =VALUE()      | 转数值                   |

**注意**：文本拼接使用 `&` 运算符，如 `{"op": "&", "left": {...}, "right": {...}}`

### 标量函数（compute expression）

| 函数  | 语法            | 说明     |
| ----- | --------------- | -------- |
| ROUND | ROUND(值, 位数) | 四舍五入 |
| ABS   | ABS(值)         | 绝对值   |
| MAX   | MAX(值 1, 值 2) | 较大值   |
| MIN   | MIN(值 1, 值 2) | 较小值   |

### 动态数组函数（Excel 365+）

| 函数    | 用途         | Excel 版本           | 对应操作 |
| ------- | ------------ | -------------------- | -------- |
| FILTER  | 按条件筛选行 | Excel 365+           | filter   |
| SORT    | 按列排序     | Excel 365+           | sort     |
| SORTBY  | 按指定列排序 | Excel 365+           | sort     |
| GROUPBY | 分组聚合     | Excel 365+ (2023.09) | group_by |
| TAKE    | 取前/后 N 行 | Excel 365+           | take     |
| UNIQUE  | 去重         | Excel 365+           | 未实现   |

---

## 十、能力总览

### 基础能力（所有 Excel 版本）

| 能力           | 支持 | 实现方式                           |
| -------------- | ---- | ---------------------------------- |
| 整列聚合       | ✅   | aggregate 操作                     |
| 条件聚合       | ✅   | SUMIF/COUNTIF/AVERAGEIF            |
| 新增计算列     | ✅   | add_column 操作                    |
| 更新现有列     | ✅   | update_column 操作                 |
| 标量运算       | ✅   | compute 操作                       |
| 条件判断       | ✅   | IF/AND/OR/NOT 函数                 |
| 空值判断       | ✅   | ISBLANK/ISNA/ISNUMBER/ISERROR 函数 |
| 空值填充       | ✅   | update_column + ISBLANK + IF       |
| 跨表查找       | ✅   | VLOOKUP 函数                       |
| 跨表多条件匹配 | ✅   | COUNTIFS 函数                      |
| 文本处理       | ✅   | LEFT/RIGHT/MID 等 + & 运算符       |
| 错误处理       | ✅   | IFERROR 函数                       |

### 高级能力（Excel 365+ 专属）

| 能力         | 支持 | 实现方式                       | Excel 函数 |
| ------------ | ---- | ------------------------------ | ---------- |
| 多条件筛选   | ✅   | filter 操作                    | FILTER()   |
| 排序         | ✅   | sort 操作                      | SORT()     |
| 分组聚合     | ✅   | group_by 操作                  | GROUPBY()  |
| 取前/后 N 行 | ✅   | take 操作                      | TAKE()     |
| 创建新 Sheet | ✅   | create_sheet 操作（隐式/显式） | 无         |

> ⚠️ **版本提醒**：filter、sort、group_by、take 操作生成的 Excel 公式需要 Excel 365 或 Excel 2021 及以上版本。其中 GROUPBY 函数需要 2023年9月更新版本的 Excel 365。

### 不支持的能力

| 能力       | 支持 | 说明                      |
| ---------- | ---- | ------------------------- |
| 自由 JOIN  | ❌   | 不支持（用 VLOOKUP 替代） |
| 自定义函数 | ❌   | 不支持                    |
| 删除行/列  | ❌   | 用 filter 筛选替代        |
| 透视表     | ❌   | 用 group_by 替代          |
