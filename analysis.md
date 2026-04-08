# 数据分析功能实现方案

## 一、功能概述

数据分析功能允许用户上传 Excel 文件后，用自然语言提出分析需求，系统智能识别分析意图，提取数据特征，生成文字洞察报告。

### 1.1 支持的分析场景

经过完整分析，用户可能的分析场景分为以下层次：

| 层次 | 场景 | 用户问法 | 系统行为 |
|------|------|----------|----------|
| **L1: 信息提取** | 基本概况 | "这份数据大概是什么？" | 直接输出行列数、列名 |
| **L1: 信息提取** | 数据质量 | "这份数据有什么问题吗？" | 检测空值、重复、异常，输出报告 |
| **L2: 通用分析** | 开放分析 | "分析一下这份数据" | 全画像 + LLM 全面洞察 |
| **L2: 通用分析** | 指定维度 | "各地区的销售情况怎么样？" | 按维度聚合 + LLM 解读 |
| **L2: 通用分析** | 多表联合 | 跨表关联洞察 | 表关系识别 + 综合分析 |
| **L3: 专项分析** | 相关性 | "销售额和销量有什么关系？" | CORREL 函数 + LLM 解读 |
| **L3: 专项分析** | 对比分析 | "华东地区和华南地区有什么差异？" | 分组对比 + LLM 解读 |
| **L3: 专项分析** | 趋势分析 | "销售额有什么变化趋势？" | 时间序列分析 + LLM 解读 |
| **L3: 专项分析** | 分布描述 | "各产品的销售分布怎么样？" | 分布统计 + LLM 解读 |
| **L4: 智能推断** | 原因归因 | "为什么 C 地区的销售额最高？" | 分析结果 + LLM 推断原因 |
| **L4: 智能推断** | 关系发现 | "这些列之间有什么关系？" | 系统发现 + LLM 解读 |

**对话续写类**（所有层次均支持）：
- 追问/续写："刚才说的华东地区，具体是哪些数据？"

### 1.2 设计原则

- **小文件全量，大文件采样**：小于 2000 行全量读取，超过则分层采样
- **数据画像可控**：系统提取结构化统计特征，LLM 只读画像不读原始数据
- **流式返回**：分析结果实时流式推送
- **多轮对话支持**：支持追问，复用现有上下文系统
- **场景分层实现**：L1/L2 先行，L3/L4 渐进增强

---

## 二、分析场景详解

### L1: 信息提取类

系统直接从数据提取信息，无需 LLM 深度分析。

#### 1. 基本概况

**用户问法**：
- "这份数据大概是什么？"
- "有多少行数据？"
- "有哪些列？"
- "这个表是关于什么的？"

**系统行为**：
```
DataProfiler 提取基本信息 → 直接返回
```

**输出示例**：
```
这份数据包含 3250 行订单记录，涵盖以下维度：
- 基本信息：订单ID、日期、地区
- 商品信息：产品ID、产品名称
- 财务信息：销售额、销量、单价
- 客户信息：客户ID（可通过关联表获取客户名称）
```

#### 2. 数据质量分析

**用户问法**：
- "这份数据有什么问题吗？"
- "有没有缺失值？"
- "有没有异常值？"
- "数据质量怎么样？"

**系统行为**：
```
DataProfiler 质量检测 → 质量报告 → LLM 总结
```

**检测项**：
| 检测项 | 说明 |
|--------|------|
| 空值比例 | 每列的空值占比 |
| 重复率 | 完全重复的行占比 |
| 格式一致性 | 日期、金额等格式是否统一 |
| 异常值 | 数值列的离群点（超过 3σ） |
| 类型推断 | 检测列的实际类型与声明类型是否一致 |

**输出示例**：
```
数据质量报告：
1. 空值问题：
   - "地区"列有 2% 空值
   - "销售额"列有 5 条为 0 的记录（需确认是否异常）
2. 重复数据：
   - 发现 15 条完全重复的订单
3. 格式问题：
   - "日期"列存在 3 种不同格式混用
```

---

### L2: 通用分析类

系统提取数据画像，LLM 基于画像生成洞察。

#### 3. 开放分析

**用户问法**：
- "分析一下这份数据"
- "帮我看看这份数据有什么特点"
- "对这份数据进行全面分析"

**系统行为**：
```
DataProfiler 提取全画像 → LLM 基于画像全面分析 → 流式输出
```

#### 4. 指定维度分析

**用户问法**：
- "各地区的销售情况怎么样？"
- "按产品分组统计一下"
- "分析一下不同客户等级的购买力"

**系统行为**：
```
识别用户指定的维度 → group_by 聚合 → LLM 解读聚合结果
```

#### 5. 多表联合分析

**用户问法**：
- "结合客户信息表分析订单"
- "这三个表之间有什么关系？"
- "产品维度的销售分析（含产品名称）"

**系统行为**：
```
RelationshipDetector 识别表关系 → 多表关联 → 联合画像 → LLM 综合分析
```

---

### L3: 专项分析类

需要专门分析函数支持。

#### 6. 相关性分析

**用户问法**：
- "销售额和销量有什么关系？"
- "这两个列相关性高吗？"
- "分析 A 列和 B 列的关系"

**系统行为**：
```
CORREL/COV AR 函数计算 → LLM 解读相关性强度和方向
```

**输出示例**：
```
销售额与销量呈现强正相关（r=0.92）：
- 相关系数接近 1，说明销售额很大程度上由销量决定
- 这符合业务预期：卖得越多，销售额越高
```

#### 7. 对比分析

**用户问法**：
- "华东地区和华南地区有什么差异？"
- "VIP 客户和普通客户谁购买力更强？"
- "对比一下各产品的表现"

**系统行为**：
```
分组聚合 → 计算对比指标 → LLM 解读差异
```

#### 8. 趋势分析

**用户问法**：
- "销售额有什么变化趋势？"
- "最近几个月的走势如何？"
- "分析一下数据的周期性"

**系统行为**：
```
识别日期列 → 时间维度聚合 → 趋势计算 → LLM 解读
```

#### 9. 分布描述

**用户问法**：
- "各产品的销售分布怎么样？"
- "订单金额主要分布在哪个区间？"
- "地区维度的占比如何？"

**系统行为**：
```
分布统计（占比、直方图区间）→ LLM 解读分布特征
```

---

### L4: 智能推断类

需要 LLM 基于数据进行推断和归因。

#### 10. 原因归因

**用户问法**：
- "为什么 C 地区的销售额最高？"
- "为什么 VIP 客户占比这么高？"
- "分析销售额最高的原因"

**系统行为**：
```
多维度下钻分析 → 找出关键因素 → LLM 推断原因
```

#### 11. 关系发现

**用户问法**：
- "这些列之间有什么关系？"
- "有没有我不知道的关联？"
- "帮我发现数据中的隐藏规律"

**系统行为**：
```
全列两两相关性扫描 → 发现强相关对 → LLM 解读业务含义
```

---

## 三、实现层次

### L1 实现（系统直接提取）

| 场景 | 核心模块 | 说明 |
|------|----------|------|
| 基本概况 | DataProfiler | 直接提取行列数、列名 |
| 数据质量 | DataProfiler + QualityChecker | 检测空值、重复、异常 |

**无需新增分析函数**，复用 DataProfiler 即可。

### L2 实现（画像 + LLM）

| 场景 | 核心模块 | 说明 |
|------|----------|------|
| 开放分析 | DataProfiler + AnalysisStage | 全画像 + LLM |
| 指定维度 | DataProfiler + group_by + LLM | 按维度聚合 + LLM |
| 多表联合 | DataProfiler + RelationshipDetector | 关系识别 + 联合画像 |

**新增模块**：
- `DataProfiler`
- `AnalysisStage`
- `RelationshipDetector`

### L3 实现（专项函数 + LLM）

| 场景 | 核心模块 | 说明 |
|------|----------|------|
| 相关性 | `CORREL`, `COV AR` 函数 | 相关性计算 |
| 对比分析 | group_by + 统计对比 | 分组对比 |
| 趋势分析 | 时间序列函数 | 趋势计算 |
| 分布描述 | 分布统计函数 | 占比/直方图 |

**新增模块**：`analysis_functions.py`

### L4 实现（LLM 智能推断）

| 场景 | 核心模块 | 说明 |
|------|----------|------|
| 原因归因 | DataProfiler + 多维度下钻 | 分析 + 推断 |
| 关系发现 | 全列相关性扫描 | 发现 + 解读 |

**实现策略**：
- L3 函数计算中间结果
- LLM 基于结果做推断
- 少量数据采样供 LLM 深度分析

---

## 四、整体架构

```
                    ┌─────────────────────────────────────┐
                    │           用户请求层               │
                    │  各种分析问法...                   │
                    └────────────────┬──────────────────┘
                                     │
                    ┌────────────────▼──────────────────┐
                    │      IntentClassifier              │
                    │      → ANALYSIS intent           │
                    │      → 子意图识别（11种场景）      │
                    └────────────────┬──────────────────┘
                                     │
        ┌─────────────────────────────┼─────────────────────────────┐
        │                             │                             │
        ▼                             ▼                             ▼
┌───────────────┐           ┌───────────────┐           ┌───────────────┐
│  L1: 信息提取 │           │  L2: 通用分析 │           │  L3: 专项分析 │
│               │           │               │           │               │
│ DataProfiler  │           │ DataProfiler  │           │ DataProfiler  │
│ QualityChecker│           │ Relationship  │           │ ──────────── │
│               │           │ Detector      │           │ analysis_funcs│
│ 直接返回       │           │ LLM 画像解读 │           │ 专项函数+LLM │
└───────────────┘           └───────────────┘           └───────────────┘
        │                             │                             │
        └─────────────────────────────┼─────────────────────────────┘
                                     ▼
                    ┌─────────────────────────────────────┐
                    │      L4: 智能推断（可选）           │
                    │      多维度下钻 + 全列扫描 + LLM    │
                    └─────────────────────────────────────┘
                                     │
                    ┌────────────────▼──────────────────┐
                    │         SSE 流式返回                │
                    └─────────────────────────────────┘
```

---

## 五、核心模块设计

### 5.1 DataProfiler（数据画像提取器）

**文件**：`apps/api/app/engine/data_profiler.py`（新建）

**职责**：从 Table 提取结构化的统计特征

```python
class DataProfiler:
    """数据画像提取器"""

    def profile_table(self, table: Table, sample_count: int = 100) -> TableProfile:
        """提取单表的画像"""

    def profile_tables(self, tables: FileCollection) -> MultiTableProfile:
        """提取多表画像，识别表关系"""

    def check_quality(self, table: Table) -> QualityReport:
        """数据质量检测"""

    def sample_data(self, table: Table, max_rows: int) -> Table:
        """数据采样（分层采样）"""
```

### 5.2 AnalysisStage（分析阶段）

**文件**：`apps/api/app/processor/stages/analysis.py`（新建）

**职责**：协调数据画像 + LLM 分析

```python
class AnalysisStage(Stage):
    """数据分析阶段"""

    stage = ProcessStage.ANALYZE

    def run(
        self,
        tables: FileCollection,
        query: str,
        config: ProcessConfig,
        context: dict,
    ) -> Generator[ProcessEvent, None, dict]:
        """
        输出：
        {
            "content": "分析报告文字",
            "profile": {...},      # 数据画像
            "analysis_type": str,  # 场景类型
            "has_cross_table": bool
        }
        """
```

### 5.3 AnalysisService（分析服务）

**文件**：`apps/api/app/services/analysis_service.py`（新建）

**职责**：
- 封装 analysis pipeline
- 处理流式返回
- 支持追问

### 5.4 AnalysisFunctions（专项分析函数）

**文件**：`apps/api/app/engine/analysis_functions.py`（新建）

**职责**：支持专项分析

```python
def pearson_correlation(x: List[float], y: List[float]) -> float:
    """皮尔逊相关系数"""

def covariance(x: List[float], y: List[float]) -> float:
    """协方差"""

def cross_tabulation(table: Table, col_a: str, col_b: str) -> Dict:
    """交叉分布表"""

def distribution_stats(table: Table, column: str, bins: int = 10) -> Dict:
    """分布统计（直方图区间）"""

def trend_analysis(dates: List[date], values: List[float]) -> Dict:
    """趋势分析（环比、同比、走势）"""

def group_comparison(table: Table, group_by: str, metrics: List[str]) -> Dict:
    """分组对比"""
```

### 5.5 RelationshipDetector（关系识别器）

**文件**：`apps/api/app/engine/relationship_detector.py`（新建）

**职责**：识别多表之间的关系

```python
class RelationshipDetector:
    """表关系识别器"""

    def detect_relationships(self, tables: FileCollection) -> List[Relationship]:
        """
        检测表间关系

        策略：
        1. 列名匹配（完全匹配 / 包含匹配）
        2. 样本值验证（匹配率 > 80% 则认为有关联）
        """
```

### 5.6 QualityChecker（质量检测器）

**文件**：`apps/api/app/engine/quality_checker.py`（新建）

**职责**：数据质量检测

```python
class QualityChecker:
    """数据质量检测器"""

    def check_nulls(self, table: Table) -> Dict[str, float]:
        """检测空值比例"""

    def check_duplicates(self, table: Table) -> Dict:
        """检测重复行"""

    def check_anomalies(self, table: Table, column: str) -> List[Any]:
        """检测数值列异常值（3σ原则）"""

    def check_format_consistency(self, table: Table, column: str) -> Dict:
        """检测格式一致性"""
```

---

## 六、文件变更清单

### 6.1 新增文件

| 文件路径 | 说明 |
|----------|------|
| `apps/api/app/engine/data_profiler.py` | 数据画像提取器（L1/L2/L3/L4 共用） |
| `apps/api/app/engine/quality_checker.py` | 数据质量检测器（L1） |
| `apps/api/app/engine/relationship_detector.py` | 表关系识别器（L2 多表联合） |
| `apps/api/app/engine/analysis_functions.py` | 专项分析函数（L3） |
| `apps/api/app/processor/stages/analysis.py` | 分析阶段（L2/L3/L4） |
| `apps/api/app/services/analysis_service.py` | 分析服务 |
| `analysis.md` | 本文档 |

### 6.2 修改文件

| 文件路径 | 修改内容 |
|----------|----------|
| `apps/api/app/engine/intent_classifier.py` | 增强 ANALYSIS 识别，支持 11 种场景子意图 |
| `apps/api/app/engine/context_builder.py` | 扩展 `_build_analysis_prompt_context()` 支持数据画像 |
| `apps/api/app/engine/prompt.py` | 新增分析模式提示词（含 L1-L4 各场景指导） |
| `apps/api/app/processor/types.py` | 添加 `ProcessStage.ANALYZE` |
| `apps/api/app/processor/excel_processor.py` | 注册 `AnalysisStage` |
| `apps/api/app/api/routes/chat.py` | ANALYSIS 路由到分析 pipeline |
| `apps/api/app/services/processing_pipeline.py` | 添加 `stream_analysis_pipeline()` |

---

## 七、任务拆分

### Task 1: 数据画像提取器

**文件**：`apps/api/app/engine/data_profiler.py`

| 子任务 | 说明 | 适用层次 |
|--------|------|----------|
| 1.1 `TableProfile` 数据类 | 定义单表画像结构 | L1-L4 |
| 1.2 `MultiTableProfile` 数据类 | 定义多表画像结构 | L2 |
| 1.3 `ColumnProfiler` | 提取单列统计特征 | L1-L4 |
| 1.4 `DataSampler` | 分层采样（行数 > 2000 时触发） | L1-L4 |

**依赖**：无

---

### Task 2: 质量检测器

**文件**：`apps/api/app/engine/quality_checker.py`

| 子任务 | 说明 | 适用层次 |
|--------|------|----------|
| 2.1 空值检测 | 每列空值比例 | L1 |
| 2.2 重复检测 | 完全重复行 | L1 |
| 2.3 异常检测 | 3σ 原则离群点 | L1 |
| 2.4 格式一致性检测 | 日期、金额等格式 | L1 |

**依赖**：无（可与 Task 1 并行）

---

### Task 3: 关系识别器

**文件**：`apps/api/app/engine/relationship_detector.py`

| 子任务 | 说明 | 适用层次 |
|--------|------|----------|
| 3.1 列名匹配检测 | 列名相同/包含识别 | L2 |
| 3.2 样本值验证 | 匹配率 > 80% 确认关联 | L2 |

**依赖**：Task 1

---

### Task 4: 专项分析函数

**文件**：`apps/api/app/engine/analysis_functions.py`

| 子任务 | 说明 | 适用层次 |
|--------|------|----------|
| 4.1 `pearson_correlation()` | 皮尔逊相关系数 | L3/L4 |
| 4.2 `covariance()` | 协方差 | L3/L4 |
| 4.3 `cross_tabulation()` | 交叉分布表 | L3/L4 |
| 4.4 `distribution_stats()` | 分布统计 | L3 |
| 4.5 `trend_analysis()` | 趋势分析 | L3 |
| 4.6 `group_comparison()` | 分组对比 | L3 |

**依赖**：Task 1

---

### Task 5: 分析阶段

**文件**：`apps/api/app/processor/stages/analysis.py`

| 子任务 | 说明 | 适用层次 |
|--------|------|----------|
| 5.1 `AnalysisStage` 类 | 核心分析阶段实现 | L1-L4 |
| 5.2 场景路由 | 根据子意图选择分析策略 | L1-L4 |
| 5.3 流式 LLM 调用 | 支持流式返回分析文字 | L1-L4 |
| 5.4 SSE 事件推送 | `analyze` / `analyze_stream` / `analyze_done` | L1-L4 |

**依赖**：Task 1, Task 2, Task 3, Task 4

---

### Task 6: 分析服务

**文件**：`apps/api/app/services/analysis_service.py`

| 子任务 | 说明 |
|--------|------|
| 6.1 `AnalysisService` 类 | 封装分析 pipeline |
| 6.2 流式返回封装 | `stream_analysis()` 异步生成器 |
| 6.3 多轮对话支持 | 继承历史分析上下文 |

**依赖**：Task 5

---

### Task 7: 提示词增强

**涉及文件**：
- `apps/api/app/engine/prompt.py`
- `apps/api/app/engine/context_builder.py`

| 子任务 | 说明 |
|--------|------|
| 7.1 L1 分析提示词 | 信息提取类场景指导 |
| 7.2 L2 分析提示词 | 通用分析类场景指导 |
| 7.3 L3 分析提示词 | 专项分析类场景指导 |
| 7.4 L4 分析提示词 | 智能推断类场景指导 |
| 7.5 画像格式说明 | 告诉 LLM 如何解读数据画像 |

**依赖**：Task 1, Task 2

---

### Task 8: 意图识别增强

**文件**：`apps/api/app/engine/intent_classifier.py`

| 子任务 | 说明 |
|--------|------|
| 8.1 扩展 `analysis_keywords` | 增加 11 种场景关键词 |
| 8.2 子意图识别 | 识别具体场景类型 |
| 8.3 指定分析识别 | 识别"分析A列和B列"等模式 |

**依赖**：无

---

### Task 9: 路由和 Pipeline 集成

**涉及文件**：
- `apps/api/app/api/routes/chat.py`
- `apps/api/app/services/processing_pipeline.py`

| 子任务 | 说明 |
|--------|------|
| 9.1 新增 `stream_analysis_pipeline()` | 分析专用 pipeline |
| 9.2 修改 `chat.py` 路由 | ANALYSIS intent 路由到分析 pipeline |
| 9.3 `ProcessStage.ANALYZE` | 添加分析阶段枚举值 |
| 9.4 注册 `AnalysisStage` | 到 ExcelProcessor |

**依赖**：Task 5, Task 6

---

## 八、任务依赖关系

```
┌─────────────────────────────────────────────────────────────────┐
│                         并行可开始                               │
├─────────────────────────────────────────────────────────────────┤
│  Task 1 (DataProfiler)  ──┐                                    │
│  Task 2 (QualityChecker)  ──┼──► Task 7 (Prompts)              │
│  Task 8 (Intent)          ──┘                                    │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│  Task 3 (RelationshipDetector)                                  │
│  Task 4 (AnalysisFunctions)                                     │
│          │                                                      │
│          └──────────┐                                           │
│                     │                                           │
└─────────────────────┼───────────────────────────────────────────┘
                      ▼
┌─────────────────────────────────────────────────────────────────┐
│  Task 5 (AnalysisStage)                                         │
│          │                                                      │
│          └──────────┐                                           │
│                     │                                           │
└─────────────────────┼───────────────────────────────────────────┘
                      ▼
┌─────────────────────────────────────────────────────────────────┐
│  Task 6 (AnalysisService)                                       │
│          │                                                      │
│          └──────────┐                                           │
│                     │                                           │
└─────────────────────┼───────────────────────────────────────────┘
                      ▼
┌─────────────────────────────────────────────────────────────────┐
│  Task 9 (Routing & Pipeline)                                   │
└─────────────────────────────────────────────────────────────────┘
```

---

## 九、实现顺序建议

### Phase 1: L1 基础（Task 1 → 2 → 9）

```
目标：实现基本概况 + 数据质量检测
1. Task 1: DataProfiler
2. Task 2: QualityChecker
3. Task 9.3 + 9.4: Types & Registration
4. Task 9.1 + 9.2: Routing
```

### Phase 2: L2 核心（Task 3 → 5 → 6 → 9）

```
目标：实现开放分析 + 指定维度 + 多表联合
1. Task 3: RelationshipDetector
2. Task 5: AnalysisStage
3. Task 6: AnalysisService
4. Task 9 (整合): Routing & Pipeline
```

### Phase 3: L3 增强（Task 4 → 7 → 5 更新）

```
目标：实现相关性 + 对比 + 趋势 + 分布
1. Task 4: AnalysisFunctions
2. Task 7: Prompts (L3 部分)
3. Task 5 更新：支持 L3 场景路由
```

### Phase 4: L4 智能（Task 7 完成 → 可选）

```
目标：实现原因归因 + 关系发现
- 取决于 L3 实现后的效果
- 可能需要 LLM 直接读少量采样数据
```

---

## 十、现有代码复用

| 现有模块 | 复用方式 |
|----------|----------|
| `IntentClassifier` | 扩展 ANALYSIS 识别逻辑，支持子意图 |
| `ContextBuilder._build_analysis_prompt_context()` | 扩展支持数据画像 |
| `ExcelParser` | 复用读取 Excel 数据 |
| `FileCollection` | 复用表集合管理 |
| `StepTracker` | 复用进度追踪 |
| SSE 流式框架 | 复用事件推送机制 |
| `group_by` / `aggregate` | L2/L3 分析时复用 |

---

## 十一、大文件处理策略

| 行数 | 策略 |
|------|------|
| ≤ 2000 行 | 全量读取发送给 LLM |
| > 2000 行 | 分层采样 2000 行 + 全量画像统计 |

**分层采样逻辑**：
1. 如果有分类列（如地区、产品），按各类别比例采样
2. 如果无分类列，随机采样
3. 画像统计（min/max/mean 等）始终用全量数据

---

## 十二、隐私安全

1. **数据外传提示**：在 UI 上提示"分析数据将发送至 LLM 服务"
2. **敏感列过滤**（可选）：自动检测并过滤"身份证"、"手机号"等敏感列
3. **列名脱敏**（可选）：将列名替换为"列A"、"列B"后再发送

---

## 十三、后续扩展方向

| 功能 | 说明 |
|------|------|
| 图表生成 | 基于分析结果生成简单图表（Excel 图表 API） |
| 报告导出 | 将分析报告保存为 Markdown/PDF |
| 自动建议 | 基于分析结果自动建议下一步操作 |

---

## 十四、实现状态

### Phase 1: L1 基础 ✅ 已完成

| 任务 | 文件 | 状态 | 测试 |
|------|------|------|------|
| DataProfiler | `app/engine/data_profiler.py` | ✅ | 见 L1 测试 |
| QualityChecker | `app/engine/quality_checker.py` | ✅ | 见 L1 测试 |
| Types & Registration | `app/processor/types.py` | ✅ | 路由已集成 |
| Routing | `app/services/processor_stream.py` | ✅ | 见集成测试 |

### Phase 2: L2 核心 ✅ 已完成

| 任务 | 文件 | 状态 | 测试 |
|------|------|------|------|
| RelationshipDetector | `app/engine/relationship_detector.py` | ✅ | 见 L2 测试 |
| AnalysisStage (L2) | `app/processor/stages/analysis.py` | ✅ | 见 L2 测试 |
| AnalysisService | 集成到现有 pipeline | ✅ | 见集成测试 |
| Prompts (L2) | `app/engine/prompt.py` | ✅ | 提示词已定义 |
| Intent 增强 | `app/services/intent_service.py` | ✅ | 场景检测已集成 |

### Phase 3: L3 专项 ✅ 已完成

| 任务 | 文件 | 状态 | 测试 |
|------|------|------|------|
| AnalysisFunctions | `app/engine/analysis_functions.py` | ✅ | 见 L3 测试 |
| - pearson_correlation | - | ✅ | 函数已实现 |
| - correlation_analysis | - | ✅ | 函数已实现 |
| - group_comparison | - | ✅ | 函数已实现 |
| - trend_analysis | - | ✅ | 函数已实现 |
| - distribution_stats | - | ✅ | 函数已实现 |
| - cross_tabulation | - | ✅ | 函数已实现 |
| - format_*_for_llm | - | ✅ | 格式化函数已实现 |
| AnalysisStage (L3) | `app/processor/stages/analysis.py` | ✅ | 见 L3 测试 |

### Phase 4: L4 智能 ✅ 已完成

| 任务 | 文件 | 状态 | 测试 |
|------|------|------|------|
| L4 归因分析 | `app/processor/stages/analysis.py` | ✅ | 见 L4 测试 |
| - _perform_drilldown_analysis | - | ✅ | 下钻分析已实现 |
| L4 关系发现 | `app/processor/stages/analysis.py` | ✅ | 见 L4 测试 |
| - _perform_correlation_scan | - | ✅ | 全列相关性扫描已实现 |
| L4 prompts | `app/engine/prompt.py` | ✅ | 提示词已定义 |
| L4 scenario detection | `app/engine/prompt.py` | ✅ | 场景检测已实现 |

---

## 十五、测试指南

### 测试数据准备

推荐准备包含以下内容的测试 Excel：

**订单.xlsx**
| 订单号 | 日期 | 地区 | 产品 | 客户 | 销售额 | 销量 | 利润 |
|--------|------|------|------|------|--------|------|------|
| ORD001 | 2024-01-01 | 华北 | 产品A | 客户甲 | 10000 | 100 | 2000 |
| ORD002 | 2024-01-02 | 华南 | 产品B | 客户乙 | 15000 | 150 | 3000 |
| ... | ... | ... | ... | ... | ... | ... | ... |

**客户.xlsx**
| 客户ID | 客户名称 | 客户等级 | 注册日期 |
|--------|----------|----------|----------|
| C001 | 客户甲 | VIP | 2023-01-01 |
| C002 | 客户乙 | 普通 | 2023-06-01 |
| ... | ... | ... | ... |

---

### L1 信息提取类 测试

#### 测试 1-1: 基本概况

```python
# 测试提示词
prompts = [
    "这份数据大概是什么？",
    "有多少行数据？",
    "有哪些列？",
    "这个表是关于什么的？",
]

# 预期场景: l1_basic
# 验证: 返回行列数、列名及含义
```

#### 测试 1-2: 数据质量

```python
# 测试提示词
prompts = [
    "这份数据有什么问题吗？",
    "有没有缺失值或异常值？",
    "数据质量怎么样？",
    "检查一下数据质量",
]

# 预期场景: l1_quality
# 验证: 返回空值率、重复率、异常值检测结果
```

**快速验证（无需启动服务）**
```bash
cd apps/api
uv run python -c "
from app.engine.prompt import detect_analysis_scenario

prompts = [
    '这份数据大概是什么？',
    '有什么质量问题吗？',
]
for p in prompts:
    print(f'{p} -> {detect_analysis_scenario(p)}')
"
```

---

### L2 通用分析类 测试

#### 测试 2-1: 开放分析

```python
# 测试提示词
prompts = [
    "分析一下这份数据",
    "帮我看看这份数据有什么特点",
    "对这份数据进行全面分析",
]

# 预期场景: l2_open
# 验证: 返回全面洞察报告
```

#### 测试 2-2: 指定维度分析

```python
# 测试提示词
prompts = [
    "各地区的销售情况怎么样？",
    "按产品分组统计一下",
    "分析一下不同类别的表现",
    "各地区的利润对比",
]

# 预期场景: l2_dimension
# 验证: 按维度聚合后 LLM 解读
```

#### 测试 2-3: 多表联合分析

```python
# 测试提示词
prompts = [
    "结合客户信息表分析订单",
    "这三个表之间有什么关系？",
    "按客户等级分析购买力（含客户名称）",
]

# 预期场景: l2_multi_table
# 验证: 表关系识别 + 联合分析
# 注意: 需要上传多个关联的 Excel 文件
```

---

### L3 专项分析类 测试

#### 测试 3-1: 相关性分析

```python
# 测试提示词
prompts = [
    "销售额和销量有什么关系？",
    "这两个列相关性高吗？",
    "分析订单金额和利润的关系",
    "sales and quantity relationship",
]

# 预期场景: l3_correlation
# 验证: 返回皮尔逊相关系数及解读
```

#### 测试 3-2: 对比分析

```python
# 测试提示词
prompts = [
    "华东地区和华南地区有什么差异？",
    "VIP客户和普通客户谁购买力更强？",
    "对比一下各产品的表现",
    "compare regions",
]

# 预期场景: l3_comparison
# 验证: 分组对比 + 差异分析
```

#### 测试 3-3: 趋势分析

```python
# 测试提示词
prompts = [
    "销售额有什么变化趋势？",
    "最近几个月的走势如何？",
    "分析一下数据的时间变化",
    "sales trend over time",
]

# 预期场景: l3_trend
# 验证: 时间聚合 + 趋势解读
# 注意: 数据需要包含日期列
```

#### 测试 3-4: 分布分析

```python
# 测试提示词
prompts = [
    "各产品的销售分布怎么样？",
    "订单金额主要分布在哪个区间？",
    "地区维度的占比如何？",
    "sales distribution",
]

# 预期场景: l3_distribution
# 验证: 分布统计 + 形态解读
```

---

### L4 智能推断类 测试

#### 测试 4-1: 归因分析

```python
# 测试提示词
prompts = [
    "为什么C地区的销售额最高？",
    "为什么VIP客户占比这么高？",
    "分析销售额最高的原因",
    "why is region C sales highest",
]

# 预期场景: l4_causation
# 验证: 多维度下钻 + 原因推断
```

#### 测试 4-2: 关系发现

```python
# 测试提示词
prompts = [
    "这些列之间有什么关系？",
    "有没有我不知道的关联？",
    "帮我发现数据中的隐藏规律",
    "find patterns in the data",
]

# 预期场景: l4_relation_discovery
# 验证: 全列相关性扫描 + 规律发现
```

---

### 快速场景检测测试

```bash
cd apps/api
uv run python -c "
from app.engine.prompt import detect_analysis_scenario

test_cases = [
    # L1
    ('这份数据大概是什么？', 'l1_basic'),
    ('有什么质量问题吗？', 'l1_quality'),
    # L2
    ('分析一下这份数据', 'l2_open'),
    ('各地区的销售情况怎么样？', 'l2_dimension'),
    # L3
    ('销售额和销量有什么关系？', 'l3_correlation'),
    ('华东和华南有什么差异？', 'l3_comparison'),
    ('销售额有什么趋势？', 'l3_trend'),
    ('各产品的分布怎么样？', 'l3_distribution'),
    # L4
    ('为什么C地区销售额最高？', 'l4_causation'),
    ('这些列之间有什么关系？', 'l4_relation_discovery'),
]

print('场景检测测试:')
for query, expected in test_cases:
    detected = detect_analysis_scenario(query)
    status = 'PASS' if detected == expected else 'FAIL'
    print(f'  [{status}] {query[:20]}... -> {detected} (expected {expected})')
"
```

---

### 集成测试（需要启动服务）

```bash
# 1. 启动 API
pnpm dev:api

# 2. 上传 Excel 文件，获取 file_id

# 3. 测试完整流程
curl -X POST "http://localhost:8000/api/chat" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{
    "query": "分析一下这份数据",
    "file_ids": ["YOUR_FILE_ID"]
  }' | jq '.'
```

---

### 函数单元测试

```bash
cd apps/api
uv run python -c "
from app.engine.analysis_functions import (
    pearson_correlation, correlation_analysis,
    group_comparison, distribution_stats,
    trend_analysis, format_correlation_for_llm
)
import pandas as pd
import numpy as np

# 相关性测试
x = list(range(10))
y = [v * 2 + 1 for v in x]
r, p = pearson_correlation(x, y)
print(f'Correlation: r={r:.4f}, p={p:.4f}')

# 分组对比测试
df = pd.DataFrame({
    '地区': ['华北', '华南', '华东'],
    '销售额': [100, 200, 150],
})
result = group_comparison(df, '地区', ['销售额'])
print(f'Groups: {result.groups}')

# 分布测试
df2 = pd.DataFrame({'金额': np.random.normal(100, 20, 1000)})
dist = distribution_stats(df2, '金额')
print(f'Distribution type: {dist.distribution_type}')

print('All function tests passed!')
"
```

---

### 分析函数列表

| 函数 | 功能 | 输出 |
|------|------|------|
| `pearson_correlation(x, y)` | 皮尔逊相关系数 | (r, p_value) |
| `correlation_analysis(df, col_a, col_b)` | 两列相关性分析 | CorrelationResult |
| `format_correlation_for_llm(result)` | 格式化相关性结果 | str |
| `group_comparison(df, group_by, metrics)` | 分组对比 | ComparisonResult |
| `format_comparison_for_llm(result)` | 格式化对比结果 | str |
| `trend_analysis(df, date_col, value_col)` | 趋势分析 | TrendResult |
| `format_trend_for_llm(result)` | 格式化趋势结果 | str |
| `distribution_stats(df, column)` | 分布统计 | DistributionResult |
| `format_distribution_for_llm(result)` | 格式化分布结果 | str |
| `cross_tabulation(df, col_a, col_b)` | 交叉分布表 | Dict |
| `format_crosstab_for_llm(crosstab)` | 格式化交叉表 | str |
| `get_numeric_columns(df)` | 获取数值列 | List[str] |
| `get_date_columns(df)` | 获取日期列 | List[str] |
| `get_categorical_columns(df)` | 获取类别列 | List[str] |
