# Fixtures 测试数据目录

本文档说明 `fixtures/` 目录的结构、用途及使用方法。

## 目录概述

`fixtures/` 目录存放 LLM Excel 系统的测试数据和用例定义，用于验证系统对 Excel 数据处理的准确性。

```
fixtures/
├── index.yaml                    # 场景索引和分组定义
├── 01-titanic/                   # 场景目录
│   ├── meta.yaml                 # 场景元数据和用例
│   └── datasets/                 # 数据文件
│       └── titanic.xlsx
├── 02-house-price/
│   ├── meta.yaml
│   └── datasets/
│       └── house_price.xlsx
└── ...
```

## 测试分组

测试用例按难度和功能分为三个部分：

### 第一部分：基础验证测试 (01-04)

**目标**：测试系统对各个领域数据的清洗、特征提取、基础统计及格式转换能力。

| 序号 | 场景               | 数据文件             | 测试重点                       |
| ---- | ------------------ | -------------------- | ------------------------------ |
| 01   | 泰坦尼克号生存预测 | titanic.xlsx         | 缺失值处理、文本提取、筛选排序 |
| 02   | 房价预测数据       | house_price.xlsx     | 数学计算、条件标签、统计概览   |
| 03   | Netflix 影视剧列表 | netflix.xlsx         | 日期处理、文本筛选、数据提取   |
| 04   | 超市销售数据       | superstore_data.xlsx | 分组汇总、百分比、日期计算     |

### 第二部分：进阶逻辑测试 (05-11)

**目标**：覆盖复杂嵌套逻辑、正则表达式提取、时序处理及统计学计算。

| 序号 | 场景             | 数据文件                  | 测试重点                             |
| ---- | ---------------- | ------------------------- | ------------------------------------ |
| 05   | FIFA 22 球员数据 | players_22.xlsx           | 复合逻辑、数据清洗(K/M转换)、BMI计算 |
| 06   | 精灵宝可梦数据   | pokemon.xlsx              | 多重排序、多列求和、文本长度         |
| 07   | 心脏病预测数据   | heart.xlsx                | 字典映射、分箱、多维分组             |
| 08   | 学生考试成绩     | students_performance.xlsx | 加权计算、及格判断、等级划分         |
| 09   | Kickstarter 众筹 | ks-projects.xlsx          | 状态二元化、达成率、周期计算         |
| 10   | 个人贷款资格     | loan.xlsx                 | 均值填充、偿债比率、单位转换         |
| 11   | IBM 员工流失     | IBM-HR.xlsx               | 多值映射、满意度计算、文本清洗       |

### 第三部分：多表/跨表关联测试 (12-14)

**目标**：测试 VLOOKUP/JOIN 逻辑、跨表计算及不同键名匹配。需严格依据表结构执行。

| 序号 | 场景               | 数据文件                                | 测试重点                     |
| ---- | ------------------ | --------------------------------------- | ---------------------------- |
| 12   | 巴西电商订单与客户 | olist_customers.xlsx, olist_orders.xlsx | 左连接、筛选关联、存在性检查 |
| 13   | 全球幸福指数报告   | 2015.xlsx, 2016.xlsx                    | 跨表差值、增长率、年度对比   |
| 14   | F1 一级方程式赛车  | drivers.xlsx, results.xlsx              | 基础关联、冠军查询、积分排名 |

## 文件格式说明

### index.yaml

场景索引文件，包含分组定义和场景列表。

```yaml
# 分组定义
groups:
  - id: "basic"
    name: "基础验证测试"
    description: "测试系统对各个领域数据的清洗..."
    scenarios: ["01-titanic", "02-house-price", ...]

# 场景列表
scenarios:
  - id: "01-titanic"
    name: "泰坦尼克号生存预测"
    group: "basic"
    path: "01-titanic"
    tags: ["缺失值", "文本提取", "筛选", "分组"]
```

### meta.yaml

场景元数据文件，定义数据集和测试用例。

```yaml
id: "01-titanic"
name: "泰坦尼克号生存预测"
description: "泰坦尼克号乘客数据，用于测试缺失值处理、文本提取等场景"

datasets:
  - file: "titanic.xlsx"
    description: "乘客信息表"

cases:
  - id: "missing-value"
    name: "缺失值处理"
    prompt: |
      检查表格中的 Age 列，如果发现空值，请用现有数据的平均年龄进行填充。
      结果写入原表，不要删除任何行。
    tags: ["缺失值", "填充"]
```

### 多表场景的 schema 字段

对于多表场景 (12-14)，meta.yaml 还包含表结构说明：

```yaml
datasets:
  - file: "olist_customers.xlsx"
    description: "客户信息表"
  - file: "olist_orders.xlsx"
    description: "订单信息表"

schema:
  - sheet: "Sheet1 (olist_customers)"
    columns: ["order_id", "customer_id", "order_status"]
  - sheet: "Sheet2 (olist_customers)"
    columns: ["customer_id", "customer_city", "customer_state"]
```

## 使用方法

### Python 读取示例

```python
import yaml
from pathlib import Path

FIXTURES_DIR = Path("fixtures")

def load_index():
    """加载场景索引"""
    return yaml.safe_load((FIXTURES_DIR / "index.yaml").read_text())

def load_scenario(scenario_id: str):
    """加载单个场景的元数据"""
    index = load_index()
    scenario = next(s for s in index["scenarios"] if s["id"] == scenario_id)
    meta_path = FIXTURES_DIR / scenario["path"] / "meta.yaml"
    return yaml.safe_load(meta_path.read_text())

def iter_cases_by_group(group_id: str):
    """遍历某个分组的所有用例"""
    index = load_index()
    group = next(g for g in index["groups"] if g["id"] == group_id)

    for scenario_id in group["scenarios"]:
        meta = load_scenario(scenario_id)
        for case in meta["cases"]:
            yield {
                "scenario_id": scenario_id,
                "scenario_name": meta["name"],
                "case_id": case["id"],
                "case_name": case["name"],
                "prompt": case["prompt"],
                "datasets": meta["datasets"],
            }

# 示例：遍历基础测试的所有用例
for case in iter_cases_by_group("basic"):
    print(f"{case['scenario_name']} - {case['case_name']}")
```

### 运行特定分组的测试

```python
def run_group_tests(group_id: str):
    """运行某个分组的所有测试"""
    for case in iter_cases_by_group(group_id):
        print(f"\n{'='*60}")
        print(f"场景: {case['scenario_name']}")
        print(f"用例: {case['case_name']}")
        print(f"{'='*60}")

        # 1. 加载数据集
        datasets = load_datasets(case["scenario_id"], case["datasets"])

        # 2. 发送 prompt 到 LLM Excel API
        result = call_llm_excel_api(datasets, case["prompt"])

        # 3. 验证结果
        validate_result(result)

# 运行基础测试
run_group_tests("basic")

# 运行进阶测试
run_group_tests("advanced")

# 运行跨表测试
run_group_tests("multi-table")
```

## 目录命名规范

| 规范       | 说明                                          |
| ---------- | --------------------------------------------- |
| 编号格式   | 两位数字 + 短横线 + 英文名称，如 `01-titanic` |
| 数据目录   | 统一使用 `datasets/` 子目录存放 Excel 文件    |
| 元数据文件 | 统一命名为 `meta.yaml`                        |
| 文件名     | 使用小写字母和下划线，如 `house_price.xlsx`   |

## 扩展指南

### 添加新场景

1. 在 `fixtures/` 下创建新目录（遵循命名规范）
2. 添加 `datasets/` 子目录并放入 Excel 文件
3. 创建 `meta.yaml` 文件定义元数据和用例
4. 在 `index.yaml` 中注册场景

### 添加新分组

在 `index.yaml` 的 `groups` 部分添加：

```yaml
groups:
  # ... 现有分组 ...

  - id: "new-group"
    name: "新分组名称"
    description: |
      分组描述...
    scenarios:
      - "15-new-scenario"
      - "16-another-scenario"
```

## 注意事项

1. **数据文件格式**：仅支持 `.xlsx` 格式
2. **编码问题**：目录和文件名避免使用中文，防止跨平台编码问题
3. **用例依赖**：部分用例依赖前序用例的结果（如 `09-kickstarter` 的类别成功率依赖状态二元化），在 tags 中标记为 `依赖前序`
4. **表结构说明**：多表场景必须在 `schema` 字段中明确列结构
