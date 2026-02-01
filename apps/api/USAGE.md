# LLM Excel 使用指南

## 快速开始

### 1️⃣ 安装依赖

```bash
uv pip install -e .
```

### 2️⃣ 配置 API Key

```bash
# 复制配置模板
cp env.example .env

# 编辑 .env 文件
# OPENAI_API_KEY=your_api_key_here
```

### 3️⃣ 创建示例数据

```bash
python create_sample_data.py
```

### 4️⃣ 开始使用

```bash
# 最简单：加载一个 Excel 文件
python main.py data/orders.xlsx
```

---

## 三种运行模式

### 模式 1：Excel 模式（推荐）⭐

**用途**：解析实际的 Excel 文件，基于真实数据结构生成代码

**命令**：

```bash
# 单个文件
python main.py data/orders.xlsx

# 多个文件（多表关联）
python main.py data/orders.xlsx data/customers.xlsx data/refunds.xlsx

# 包含多个 Sheet 的文件
python main.py data/multi_sheet.xlsx
```

**工作流程**：

1. 系统自动解析 Excel 文件
2. 提取表结构（表名、字段名）
3. 显示所有表的字段信息
4. 进入交互模式，等待用户输入需求
5. 基于真实表结构生成代码

**示例会话**：

```
📊 已加载的表:
表名: orders
字段: order_id, customer_id, amount, status, date

📋 请描述数据处理需求：
> 计算已完成订单的总金额

✅ 生成的代码：
result = SUMIF(orders.amount, orders.status, "已完成")

📋 请描述数据处理需求：
> 计算已完成订单的净收入（减去退款）

✅ 生成的代码：
order_total = SUMIF(orders.amount, orders.status, "已完成")
refund_total = SUM(refunds.amount)
result = order_total - refund_total
```

**特殊命令**：

- 输入 `schema` - 查看所有表结构
- 输入 `quit` 或 `exit` - 退出系统

---

### 模式 2：演示模式

**用途**：查看系统功能演示，不需要准备 Excel 文件

**命令**：

```bash
python main.py --demo
# 或直接
python main.py
```

**特点**：

- 运行 3 个预设示例
- 展示不同复杂度的需求
- 适合快速了解系统能力

---

### 模式 3：交互模式

**用途**：纯交互式代码生成，不需要 Excel 文件（需手动指定表结构）

**命令**：

```bash
python main.py --interactive
```

**特点**：

- 无需加载 Excel 文件
- 需要在需求描述中说明表结构
- 适合快速验证想法

---

## 典型使用场景

### 场景 1：单表聚合分析

**Excel 文件**：`orders.xlsx`

| order_id | customer_id | amount | status | date       |
| -------- | ----------- | ------ | ------ | ---------- |
| 1        | 101         | 1500   | 已完成 | 2024-01-01 |
| 2        | 102         | 2300   | 已完成 | 2024-01-02 |
| 3        | 101         | 890    | 已取消 | 2024-01-03 |

**需求示例**：

1. "计算已完成订单的总金额"
2. "统计已完成订单的数量"
3. "计算已完成订单的平均金额"
4. "找出已完成订单中的最大金额"

**生成的代码**：

```python
# 需求 1
result = SUMIF(orders.amount, orders.status, "已完成")

# 需求 2
result = COUNTIF(orders.status, "已完成")

# 需求 3
result = AVERAGEIF(orders.amount, orders.status, "已完成")

# 需求 4
completed_amounts = IFERROR(
    SUMIF(orders.amount, orders.status, "已完成"),
    0
)
result = MAX(completed_amounts)
```

---

### 场景 2：多表关联查询

**Excel 文件**：`orders.xlsx` + `customers.xlsx`

**orders.xlsx**：

| order_id | customer_id | amount | status |
| -------- | ----------- | ------ | ------ |
| 1        | 101         | 1500   | 已完成 |
| 2        | 102         | 2300   | 已完成 |

**customers.xlsx**：

| id  | name | level | region |
| --- | ---- | ----- | ------ |
| 101 | 张三 | VIP   | 北京   |
| 102 | 李四 | 普通  | 上海   |

**需求示例**：

1. "计算 VIP 客户的已完成订单总金额"
2. "统计北京地区客户的已完成订单数量"

**运行命令**：

```bash
python main.py data/orders.xlsx data/customers.xlsx
```

**生成的代码**：

```python
# 需求 1
customer_level = VLOOKUP(orders.customer_id, customers, "id", "level")
is_vip = customer_level == "VIP"
is_completed = orders.status == "已完成"
condition = AND(is_vip, is_completed)
result = SUMIF(orders.amount, condition, True)

# 需求 2
customer_region = VLOOKUP(orders.customer_id, customers, "id", "region")
is_beijing = customer_region == "北京"
is_completed = orders.status == "已完成"
condition = AND(is_beijing, is_completed)
result = COUNTIF(condition, True)
```

---

### 场景 3：复杂计算（带运算符）

**需求**：计算已完成订单的净收入（订单金额减去退款金额），结果四舍五入到 2 位小数

**Excel 文件**：`orders.xlsx` + `refunds.xlsx`

**运行命令**：

```bash
python main.py data/orders.xlsx data/refunds.xlsx
```

**生成的代码**：

```python
order_total = SUMIF(orders.amount, orders.status, "已完成")
refund_total = SUM(refunds.amount)
net = order_total - refund_total
result = ROUND(net, 2)
```

---

## 多 Sheet 文件处理

如果 Excel 文件包含多个 Sheet，系统会自动解析所有 Sheet，每个 Sheet 作为一个独立的表。

**示例文件**：`multi_sheet.xlsx`

- Sheet 1: "订单"
- Sheet 2: "客户"

**运行命令**：

```bash
python main.py data/multi_sheet.xlsx
```

**系统输出**：

```
📄 文件: multi_sheet.xlsx
   包含 2 个 sheet:
   - 订单: 10 行 x 5 列
   - 客户: 5 行 x 4 列
   ✅ 解析成功

📊 已加载的表:
表名: 订单
字段: order_id, customer_id, amount, status, date

表名: 客户
字段: id, name, level, region
```

**使用表名**：

在需求中直接使用 Sheet 名称作为表名：

```
📋 请描述数据处理需求：
> 计算"订单"表中已完成订单的总金额

✅ 生成的代码：
result = SUMIF(订单.amount, 订单.status, "已完成")
```

---

## 提示与技巧

### ✅ 好的需求描述

1. **明确具体**：
   - ✅ "计算已完成订单的总金额"
   - ❌ "算一下订单"

2. **指明表和字段**（如果不明显）：
   - ✅ "计算 orders 表中 status='已完成' 的 amount 总和"
   - ✅ "统计客户表中 VIP 客户的数量"

3. **逐步拆解复杂需求**：
   - ✅ 先："计算已完成订单总金额"
   - ✅ 再："计算退款总金额"
   - ✅ 最后："计算净收入（订单金额减退款金额）"

### 🎯 系统能做什么

- ✅ 聚合计算（求和、计数、平均、最大、最小）
- ✅ 条件筛选（等于、大于、小于）
- ✅ 算术运算（加减乘除）
- ✅ 逻辑判断（AND、OR、IF）
- ✅ 多表查找（VLOOKUP）
- ✅ 数值修正（四舍五入、绝对值）
- ✅ 错误处理（IFERROR）

### ⚠️ 系统不能做什么

- ❌ 自定义函数或 Python 代码
- ❌ 循环、条件语句（if/for/while）
- ❌ 复杂的多对多 JOIN
- ❌ 数据修改（只能读取和计算）
- ❌ 超出白名单的函数

---

## 常见问题

### Q1: 如何查看已加载的表和字段？

在 Excel 模式下，输入 `schema` 即可查看。

### Q2: 支持哪些 Excel 文件格式？

支持 `.xlsx`、`.xls`、`.xlsm` 格式。

### Q3: 表名和字段名有什么要求？

- 自动使用文件名（不含扩展名）或 Sheet 名称作为表名
- 字段名来自 Excel 的第一行（表头）
- 会自动清理空格和标准化

### Q4: 如何处理多个文件？

直接在命令行指定多个文件路径：

```bash
python main.py file1.xlsx file2.xlsx file3.xlsx
```

### Q5: 生成的代码如何使用？

目前生成的是受限的 Python 代码，后续会增加：

- 代码执行功能（返回实际结果）
- Excel 公式生成（可直接复制到 Excel）
- 结果验证（Python vs Excel）

---

## 下一步

现在系统已经可以：

1. ✅ 解析 Excel 文件
2. ✅ 理解表结构
3. ✅ 基于需求生成代码

**即将支持**（开发中）：

- 🚧 代码执行（在实际数据上运行）
- 🚧 结果验证
- 🚧 Excel 公式生成

**需要帮助？**

查看 [OPERATION_SPEC.md](../../docs/OPERATION_SPEC.md) 了解完整技术规范。
