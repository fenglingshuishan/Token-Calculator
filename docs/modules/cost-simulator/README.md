> Revision 2026-07-07: frontend can compute costs locally after fetching pricing via GET /api/models. What-if slider adjustments require no backend call.

# 费用模拟模块 (Cost Simulator)

> **模块 ID**: `cost-simulator`
> **所属项目**: Prompt 优化工作站
> **设计版本**: v2.0
> **更新日期**: 2026-07-06

---

## 1. 模块概述

### 1.1 定位

费用模拟模块是 Prompt 优化工作站的核心业务价值展示层。它将语义压缩带来的 token 节省转化为直观的财务数字，回答用户最关心的问题：**压缩能省多少钱**。

该模块不直接处理用户输入文本，也不执行压缩或分词，而是聚合来自 model-registry（价格数据）和 tokenizer-layer（token 计数）的信息，以模型单价为权重，计算压缩前后的费用差异，生成结构化的对比报告。

### 1.2 设计目标

| 目标 | 说明 |
|------|------|
| **可信** | 计算结果可追溯、可校验，每一步有对应的价格源 + token 数源 |
| **灵活** | 支持任意模型数量对比、任意压缩率假设、缓存命中率调节 |
| **快速反馈** | 假设分析场景下，参数调整后立即重算，不依赖后端重跑压缩或分词 |
| **可扩展** | 计费模式可扩展（图像 token、batch pricing、自定义折扣） |

### 1.3 核心功能一览

```
┌───────────────────────────────────────────────────────────┐
│                  费用模拟模块                               │
│                                                           │
│  ┌─────────────────┐  ┌─────────────────────────────┐    │
│  │ 单次费用计算     │  │ 月度批量模拟                │    │
│  │                 │  │                             │    │
│  │ input_tokens    │  │ monthly_calls × single_cost │    │
│  │ × input_price   │  │   ├─ 压缩前费用            │    │
│  │ + output_tokens │  │   ├─ 压缩后费用            │    │
│  │ × output_price  │  │   └─ 节省额                │    │
│  │ / 1M            │  │                             │    │
│  └─────────────────┘  └─────────────────────────────┘    │
│                                                           │
│  ┌─────────────────┐  ┌─────────────────────────────┐    │
│  │ 多模型对比       │  │ 假设分析 (What-if)          │    │
│  │                 │  │                             │    │
│  │ 3+ 模型并排      │  │ 调整调用量 / 压缩率 /      │    │
│  │ 按节省额排序     │  │ 模型 → 实时重算           │    │
│  │ 标记最优方案     │  │ 前端无等待                 │    │
│  └─────────────────┘  └─────────────────────────────┘    │
└───────────────────────────────────────────────────────────┘
```

---

## 2. 核心数据结构

本模块定义三种数据载体，分别对应三种计算场景的输出。所有金额单位为 **美元**。

### 2.1 CostBreakdown — 单次请求费用明细

```python
CostBreakdown = {
    "model_id":    str,     # 模型标识，如 "GPT-4o"
    "input_cost":  float,   # 输入 token 费用
    "output_cost": float,   # 输出 token 费用
    "cache_discount": float,# 缓存命中带来的折扣金额（正数表示节省）
    "total_cost":  float,   # input_cost + output_cost - cache_discount
}
```

| 字段 | 类型 | 含义 | 计算逻辑 |
|------|------|------|----------|
| `model_id` | string | 模型标识，与 model-registry 一致 | 由调用方指定 |
| `input_cost` | float | 输入 token 对应的费用 | `(input_tokens - cache_hit_tokens) x input_price / 1M` |
| `output_cost` | float | 输出 token 对应的费用 | `output_tokens x output_price / 1M` |
| `cache_discount` | float | 缓存节省的金额 | `cache_hit_tokens x (input_price - cache_hit_price) / 1M` |
| `total_cost` | float | 实际总费用 | `input_cost + output_cost` (已扣除缓存折扣) |

**缓存折扣规则**: 当缓存命中时，命中的 token 按 `cache_hit_price` 而非 `input_price` 计费，两者的差价即为折扣。`cache_hit_price` 通常为 `input_price` 的 50%（OpenAI 标准）或 10-50%（各模型不等）。如果模型不支持缓存命中（`cache_hit_price = None`），则 `cache_discount = 0`。

### 2.2 SimulationReport — 月度模拟报告

```python
SimulationReport = {
    "monthly_calls":      int,                        # 月调用量
    "comparisons":        list[ModelComparison],      # 每个模型的对比数据
    "best_value_model":   str,                        # 综合最优模型 ID
}
```

其中 `ModelComparison`:

```python
ModelComparison = {
    "model_id":          str,     # 模型标识
    "before": {                  # 压缩前费用
        "input_cost":    float,  # 月输入费用
        "output_cost":   float,  # 月输出费用
        "total":         float,  # 月总费用
    },
    "after": {                   # 压缩后费用
        "input_cost":    float,
        "output_cost":   float,
        "total":         float,
    },
    "monthly_savings":   float,  # 月节省金额
    "yearly_savings":    float,  # 年节省金额 = monthly_savings x 12
    "savings_percentage": float, # 节省百分比
}
```

| 字段 | 含义 |
|------|------|
| `before.input_cost` | 压缩前（原始 token 数）月度输入费用 |
| `before.output_cost` | 压缩前月度输出费用（输出 token 不受压缩影响） |
| `before.total` | 压缩前月度总费用 |
| `after.input_cost` | 压缩后（压缩后 token 数）月度输入费用 |
| `after.output_cost` | 压缩后月度输出费用（与压缩前相同） |
| `after.total` | 压缩后月度总费用 |
| `monthly_savings` | `before.total - after.total` |
| `yearly_savings` | `monthly_savings x 12` |
| `savings_percentage` | `(monthly_savings / before.total) x 100` |

**`best_value_model` 判定规则**: 在 `comparisons` 中按 `after.total` 升序排列，取总费用最低的模型。当费用相同或差距小于 $0.01/月 时，按 `savings_percentage` 降序取。

### 2.3 ModelSavings — 单模型详细节省分析

```python
ModelSavings = {
    "model_id":           str,    # 模型标识
    "original_tokens": {         # 压缩前 token 分布
        "input":    int,         # 原始输入 token 数
        "output":   int,         # 输出 token 数
    },
    "compressed_tokens": {       # 压缩后 token 分布
        "input":    int,         # 压缩后输入 token 数
        "output":   int,         # 输出 token 数（与压缩前一致）
    },
    "tokens_saved_per_call": int,    # 单次节省 token 数
    "cost_saved_per_call":   float,  # 单次节省金额
    "monthly_savings":       float,  # 月节省金额
    "yearly_savings":        float,  # 年节省金额
    "savings_percentage":    float,  # 节省百分比（按金额）
}
```

| 字段 | 含义 | 计算 |
|------|------|------|
| `tokens_saved_per_call` | 单次调用节省的 token 数 | `original_input - compressed_input`（输出不变） |
| `cost_saved_per_call` | 单次节省金额 | `tokens_saved_per_call x input_price / 1M` |
| `monthly_savings` | 月省 | `cost_saved_per_call x monthly_calls` |
| `yearly_savings` | 年省 | `monthly_savings x 12` |
| `savings_percentage` | 节省% | `(original_total - compressed_total) / original_total x 100` |

`ModelSavings` 是细颗粒度结构，供前端逐个模型展示 token 节省和金额节省的对应关系。`SimulationReport.ModelComparison` 更粗粒度，聚焦月度总额对比。两者数据源相同，聚合层级不同。

---

## 3. 单次费用计算

### 3.1 通用公式

```
input_cost  = (input_tokens - cache_hit_tokens) x input_price / 1,000,000
output_cost = output_tokens x output_price / 1,000,000
cache_discount = cache_hit_tokens x (input_price - cache_hit_price) / 1,000,000
total       = input_cost + output_cost - cache_discount
```

> 注意：`(input_tokens - cache_hit_tokens)` 确保缓存命中的 token 不再按原价计费，而是走缓存价格。如果模型不支持缓存，则 `cache_hit_price = None`，此时 `cache_hit_tokens` 被强制置为 0。

### 3.2 价格参数来源

价格参数从 model-registry 读取。以 GPT-4o 为例：

| 参数 | 值 | 单位 |
|------|-----|------|
| `input_price` | 2.50 | $/1M token |
| `output_price` | 10.00 | $/1M token |
| `cache_hit_price` | 1.25 | $/1M token |

→ 参见 [model-registry](../model-registry/README.md#pricing-字段说明)

### 3.3 计算示例：GPT-4o 单次请求

**场景**: 用户提交一个 520 token 的 prompt，期望输出 200 token，缓存命中 100 token。

```
输入:
  input_tokens  = 520
  output_tokens = 200
  cache_hit     = 100

价格 (from model-registry):
  input_price      = 2.50   $/1M
  output_price     = 10.00  $/1M
  cache_hit_price  = 1.25   $/1M

计算:
  input_cost  = (520 - 100) x 2.50 / 1,000,000 = 0.00105
  output_cost = 200 x 10.00 / 1,000,000        = 0.00200
  cache_discount = 100 x (2.50 - 1.25) / 1M    = 0.000125
  无缓存时总费用 = 0.00130 + 0.00200 = 0.00330
  有缓存时总费用 = 0.00105 + 0.00200 - 0.000125 = 0.002925

CostBreakdown:
  model_id:       "GPT-4o"
  input_cost:     0.00105
  output_cost:    0.00200
  cache_discount: 0.000125
  total_cost:     0.002925
```

### 3.4 缓存折扣的边界处理

| 场景 | 处理 |
|------|------|
| 模型不支持缓存（`cache_hit_price = None`） | `cache_hit_tokens` 强制为 0，`cache_discount` 恒为 0 |
| `cache_hit_tokens > input_tokens` | 截断：`cache_hit_tokens = input_tokens` |
| `input_tokens = 0` | `input_cost = 0`，`cache_discount = 0` |
| `output_tokens = 0` | `output_cost = 0` |

---

## 4. 月度模拟计算

### 4.1 输入参数

| 参数 | 类型 | 范围 | 默认值 | 说明 |
|------|------|------|--------|------|
| `monthly_calls` | int | 1 ~ 10^9 | (必填) | 月均 API 调用次数 |
| `avg_input_tokens` | int | 1 ~ 10^6 | (必填) | 平均输入 token 数（压缩前） |
| `avg_output_tokens` | int | 0 ~ 10^6 | (必填) | 平均输出 token 数 |
| `compression_ratio` | float | 0 ~ 1 | (必填) | 压缩节省比例，如 0.65 表示节省 65% |
| `cache_hit_rate` | float | 0 ~ 1 | 0.0 | 缓存命中率，如 0.30 表示 30% 的输入 token 命中缓存 |
| `model_ids` | list[str] | 1 ~ 50 | (必填) | 要对比的模型 ID 列表 |

### 4.2 计算流程

```
输入: monthly_calls = 10000, avg_input_tokens = 520, avg_output_tokens = 200,
      compression_ratio = 0.65, cache_hit_rate = 0.30,
      model_ids = ["GPT-4o", "Claude Opus 4", "DeepSeek V3"]

第 1 步: 推算压缩后 token 数
  compressed_input = avg_input_tokens x (1 - compression_ratio)
                   = 520 x 0.35 = 182
  → 即压缩后每调用只需 182 输入 token

第 2 步: 推算缓存命中 token 数
  cache_hit_per_call = round(avg_input_tokens x cache_hit_rate)
                     = round(520 x 0.30) = 156

第 3 步: 获取各模型价格 (from model-registry)
  GPT-4o:         input=2.50,  output=10.00, cache=1.25
  Claude Opus 4:  input=15.00, output=75.00, cache=1.50
  DeepSeek V3:    input=0.27,  output=1.10,  cache=0.07

第 4 步: 对每个模型计算单次费用（使用第 2 节公式）

第 5 步: 单次费用 x monthly_calls = 月度费用
  before_total = before_single x monthly_calls
  after_total  = after_single x monthly_calls
  savings     = before_total - after_total

第 6 步: 按 after_total 升序排序，标记 best_value_model
```

### 4.3 输出示例

```python
{
  "monthly_calls": 10000,
  "comparisons": [
    {
      "model_id": "GPT-4o",
      "before": {"input_cost": 13.00, "output_cost": 20.00, "total": 33.00},
      "after":  {"input_cost":  4.55, "output_cost": 20.00, "total": 24.55},
      "monthly_savings":   8.45,
      "yearly_savings":  101.40,
      "savings_percentage": 25.6
    },
    {
      "model_id": "Claude Opus 4",
      "before": {"input_cost": 78.00, "output_cost": 150.00, "total": 228.00},
      "after":  {"input_cost": 27.30, "output_cost": 150.00, "total": 177.30},
      "monthly_savings":   50.70,
      "yearly_savings":   608.40,
      "savings_percentage": 22.2
    },
    {
      "model_id": "DeepSeek V3",
      "before": {"input_cost": 1.40, "output_cost": 2.20, "total": 3.60},
      "after":  {"input_cost": 0.49, "output_cost": 2.20, "total": 2.69},
      "monthly_savings":   0.91,
      "yearly_savings":   10.92,
      "savings_percentage": 25.3
    }
  ],
  "best_value_model": "DeepSeek V3"   # 月度总费用最低
}
```

### 4.4 输出格式说明

- 所有金额保留 **2 位小数**（美元），中间计算保留 5 位小数防止精度丢失
- `savings_percentage` 保留 **1 位小数**
- `comparisons` 数组按 `after.total` 升序排列
- `best_value_model` 取 `after.total` 最低的模型；持平则取 `savings_percentage` 最高的

---

## 5. 多模型对比

### 5.1 场景

用户希望对比同一组 token 数据在不同模型上的费用表现，找出最优性价比。典型场景：

> "我每月调用 10000 次，平均输入 520 token，输出 200 token，压缩后输入降到 180 token。GPT-4o、Claude Opus 4、DeepSeek V3 各要花多少钱？"

### 5.2 计算逻辑

`compare_models` 的核心逻辑是**模型维度展开**：同一份 token 数据，分别套用每个模型的价格表计算。

```
输入: original_tokens = {input: 520, output: 200}
      compressed_tokens = {input: 180, output: 200}  (压缩仅减少 input)
      model_ids = ["GPT-4o", "Claude Opus 4", "DeepSeek V3"]
      monthly_calls = 10000

对每个 model_id:
  1. 从 model-registry 读取 price = pricing[model_id]
  2. 原始费用 = (520 x price.input + 200 x price.output) / 1M
  3. 压缩后费用 = (180 x price.input + 200 x price.output) / 1M
  4. 单次节省 = 原始费用 - 压缩后费用
  5. 月节省 = 单次节省 x monthly_calls
  6. 年节省 = 月节省 x 12
  7. 节省% = 单次节省 / 原始费用 x 100

返回: list[ModelSavings] (按 monthly_savings 降序排列)
```

### 5.3 排名与推荐

| 排名维度 | 指标 | 排序方向 |
|----------|------|----------|
| **省钱绝对值** | `monthly_savings` | 降序（省最多的排第一） |
| **省钱百分比** | `savings_percentage` | 降序 |
| **绝对费用** | `after.total`（仅 SimulationReport） | 升序（费用最低的最优） |

**多模型推荐逻辑**: `compare_models` 按 `monthly_savings` 降序排列；`simulate_monthly` 则按 `after.total` 升序排列并标记 `best_value_model`。两者视角不同：前者关注"压缩后哪个模型省最多"，后者关注"压缩后哪个模型最便宜"。

### 5.4 模型数量上限

单次 `compare_models` 调用支持 1 ~ 50 个模型。超过 50 个时，调用方应分批请求。模型数量主要影响响应体大小，计算复杂度为 O(n) 可忽略。

---

## 6. 假设分析 (What-if)

### 6.1 设计目标

假设分析允许用户调整任意输入参数后**立即重算**，不需要重新执行压缩或分词流程。它是面板 3 成本模拟器的交互基础。

### 6.2 可调参数与重算范围

| 参数 | 调整后影响范围 | 是否需要后端调用 |
|------|----------------|-----------------|
| `monthly_calls` | 所有模型的月度/年度金额 | 否，纯前端重算（或缓存计算结果后重算） |
| `compression_ratio` | 所有模型的输入费用 | 否 |
| `cache_hit_rate` | 所有模型的 `input_cost` | 否 |
| `avg_input_tokens` | 所有模型的输入费用 | 否 |
| `avg_output_tokens` | 所有模型的输出费用 | 否 |
| `model_ids` (增减) | 对比列表增减 | 否，前端过滤即可 |
| 切换价格数据源 | 所有费用 | 是，需重新读取 model-registry |

> 所有不涉及价格数据源刷新的调整，均可在前端或后端缓存层完成，无需重新查询 model-registry。

### 6.3 实时重算流程

```
用户调整滑块 → 前端捕获新参数
    │
    ▼
判断是否需要后端参与？
  ├─ 仅调整调用量/压缩率/cache/avg_tokens → 前端已有价格缓存
  │    → 本地即时重算 → 更新柱状图 + 对比表
  │
  └─ 切换/新增模型 → 前端缓存该模型价格？
       ├─ 是 → 本地重算
       └─ 否 → GET /api/pricing?models=xxx → 获取新模型价格 → 重算

重算后更新:
  - SimulationReport（月度对比卡片）
  - 柱状图（压缩前 vs 压缩后）
  - 多模型对比表
  - best_value_model 标注
```

### 6.4 交互设计（前端面板）

详见 → [frontend-ui](../frontend-ui/README.md#面板-3contrast-results)

```
┌─ 成本模拟器 (可折叠) ──────────────────────────────┐
│                                                      │
│  月均调用量: [10000]   ───●─────────────── 滑块     │
│  压缩率:    [65%]      ───●─────────────── 滑块     │
│  缓存率:    [30%]      ───●─────────────── 滑块     │
│                                                      │
│  ┌─────────┬──────────┬──────────┬──────────┐      │
│  │ 模型    │ 压缩前/月 │ 压缩后/月 │ 月省     │      │
│  ├─────────┼──────────┼──────────┼──────────┤      │
│  │ GPT-4o  │ $33.00   │ $24.55   │ $8.45    │      │
│  │ Claude  │ $228.00  │ $177.30  │ $50.70   │      │
│  │ DeepSeek│ $3.60    │ $2.69    │ $0.91    │      │
│  └─────────┴──────────┴──────────┴──────────┘      │
│                                                      │
│  [费用对比柱状图 (横向)]                            │
│  GPT-4o    ██████████████████████████  $24.55       │
│  Claude    ████████████████████████████████████ $177 │
│  DeepSeek  ███                                     │
│                                                      │
│  年度节省: GPT-4o $101.40 | Claude $608.40           │
│  ⭐ 最优: DeepSeek V3 ($2.69/月)                    │
└──────────────────────────────────────────────────────┘
```

---

## 7. 与其他模块的关系

### 7.1 模块依赖关系图

```
┌──────────────────────────────┐
│        compression-engine    │──── 压缩率 → cost-simulator
│        (语义压缩引擎)         │
└──────────────────────────────┘
         │
         │ 原始 token 数 + 压缩后 token 数
         ▼
┌──────────────────────────────┐
│     tokenizer-layer          │──── token 计数 → cost-simulator
│     (分词器层)                │
└──────────────────────────────┘
         │
         │ model_id
         ▼
┌──────────────────────────────┐
│     model-registry           │──── pricing 字段 → cost-simulator
│     (模型注册表)              │
└──────────────────────────────┘
         │
         ▼
┌──────────────────────────────┐
│     cost-simulator           │  ← 当前模块
│     (费用模拟)                │
└──────────┬───────────────────┘
           │
           ├──→ api-gateway  (POST /api/cost/simulate)
           │
           └──→ frontend-ui (面板 3 成本模拟器 + 柱状图数据源)
```

### 7.2 详细接口关系

#### 依赖: model-registry (模型注册表)

- **调用目的**: 读取模型的 `pricing` 字段
- **读取字段**: `pricing.input`, `pricing.output`, `pricing.cache_hit`
- **调用时机**: 模块初始化时加载全量价格表，后续通过 `get_model_pricing(model_id)` 按需读取
- **约束**: cost-simulator **只读不写**，价格数据的维护在 model-registry 中
- → 参见 [model-registry](../model-registry/README.md#pricing-字段说明)

#### 依赖: tokenizer-layer (分词器层)

- **调用目的**: 获取输入/输出文本的精确 token 数
- **使用模式**: 仅当用户使用"精确模式"时才调用，快速估算模式可用字符近似
- **调用时机**: 压缩引擎输出压缩结果后，由调用方（api-gateway 或 compression-engine）先调用 tokenizer-layer 计数，再将结果传入 cost-simulator
- → 参见 [tokenizer-layer](../tokenizer-layer/README.md#计数模式)

#### 被调用: api-gateway (API 网关)

- **暴露接口**: `POST /api/cost/simulate`
- **请求体**: 参见 [api-gateway 文档](../api-gateway/README.md#post-apicostsimulate)
- **组装逻辑**: api-gateway 接收前端请求后，先调用 compression-engine 获取压缩结果，再调用 tokenizer-layer 获取 token 计数，最后将 token 数据传入 cost-simulator
- → 参见 [api-gateway](../api-gateway/README.md#post-apicostsimulate)

#### 被使用: frontend-ui (前端界面)

- **使用位置**: 面板 3（对比结果）的可折叠"成本模拟器"
- **数据展示**: 月度对比卡片、多模型柱状图、最优模型高亮
- **交互模式**: 前端滑条调整参数后，本地重算（假设分析），或发送新请求获取完整报告
- **本地计算能力**: 前端在获取 `GET /api/models` 的定价数据后，可在本地独立完成成本计算（无需每次滑块调整都调用后端）。计算逻辑与后端 `cost-simulator` 保持一致：`total = (input_tokens x input_price + output_tokens x output_price) / 1M`。前端本地计算仅用于假设分析的即时反馈，正式报告仍由后端生成。
- → 参见 [frontend-ui](../frontend-ui/README.md#面板-3contrast-results)

#### 配合: compression-engine (语义压缩引擎)

- **配合流程**: compression-engine 输出压缩结果 → tokenizer-layer 分别计数压缩前/后 → cost-simulator 计算费用差异
- **关键传递值**: `compression_ratio` 由 compression-engine 的输出和 tokenizer-layer 的计数共同推导
- → 参见 [compression-engine](../compression-engine/README.md#输出格式)

### 7.3 数据流全景

```
用户输入 Prompt
    │
    ▼
compression-engine
    │ 输出压缩后文本
    ▼
tokenizer-layer (分别计数压缩前和压缩后)
    │ 输出: original_tokens, compressed_tokens
    ▼
model-registry (按模型读取价格)
    │ 输出: pricing info
    ▼
cost-simulator (本模块)
    │ 输入: token 数据 + 月调用量 + 模型 ID 列表
    │ 输出: SimulationReport
    ▼
api-gateway (封装为 API 响应)
    ▼
frontend-ui (渲染柱状图 + 对比表)
```

---

## 8. 价格数据来源

### 8.1 基本原则

- **价格数据存储在 model-registry 中**，cost-simulator 只读取不维护
- 价格数据的初始化、更新、版本控制均由 model-registry 负责
- cost-simulator 假定 model-registry 返回的价格是权威且最新的

### 8.2 价格读取机制

```
cost_simulator.py (初始化时)
    │
    ├── 调用 ModelRegistry.get_all_pricing()
    │    → 返回全量价格字典: {model_id: {input, output, cache_hit}}
    │
    └── 内部缓存: self._pricing_cache = {...}
        │
        ├── cost_simulator.calculate_single() → 从缓存查询
        ├── cost_simulator.simulate_monthly() → 从缓存查询
        └── cost_simulator.compare_models()   → 从缓存查询
```

### 8.3 价格更新策略

| 场景 | 行为 |
|------|------|
| 应用启动 | 从 model-registry 加载全量价格 |
| 用户手动刷新 | 调用 `refresh_pricing()` 重新加载 |
| model-registry 发送更新事件 | 监听事件，更新缓存（如事件系统暂未实现，则依赖手动刷新） |

### 8.4 价格数据示例

当前支持的全部模型价格见 → [项目设计文档](../../design-document.md#51-模型价格数据)

```python
# model-registry 返回结构示意
{
    "GPT-4o":           {"input": 2.50,  "output": 10.00, "cache_hit": 1.25},
    "Claude Opus 4":    {"input": 15.00, "output": 75.00, "cache_hit": 1.50},
    "DeepSeek V3":      {"input": 0.27,  "output": 1.10,  "cache_hit": 0.07},
    # ... 完整列表见设计文档
}
```

---

## 9. 扩展指南

### 9.1 添加新的计费模式

#### 场景 1: 图像 Token 计费

某些模型（如 GPT-4 Vision）支持图像输入，费用计算逻辑不同：

```python
# 当前: 纯文本计费
total = (input_tokens × input_price + output_tokens × output_price) / 1M

# 扩展后: 文本 + 图像混合计费
total = (
    text_input_tokens × text_input_price +
    image_count × image_price_per_image +    # 按图计费
    output_tokens × output_price
) / 1M
```

**扩展方式**:

1. **在 model-registry 中扩展 pricing 结构**:
   ```python
   PRICING["GPT-4o"] = {
       "input": 2.50,
       "output": 10.00,
       "cache_hit": 1.25,
       "image": {                                   # 新增
           "mode": "per_image",                     # "per_image" | "per_token"
           "price": 0.00265,                        # $/image 或 $/token
       }
   }
   ```

2. **在 cost-simulator 中扩展计算逻辑**:
   ```python
   def _calculate_image_cost(self, images: int, pricing: dict) -> float:
       if "image" not in pricing:
           return 0.0
       image_pricing = pricing["image"]
       if image_pricing["mode"] == "per_image":
           return images * image_pricing["price"]
       # elif image_pricing["mode"] == "per_token":
       #     return images * image_pricing["price"] / 1_000_000
   ```

3. **扩展数据结构** — 在 CostBreakdown 中增加 `image_cost` 字段:
   ```python
   CostBreakdown = {
       "model_id": "GPT-4o",
       "input_cost": 0.00105,
       "output_cost": 0.00200,
       "image_cost": 0.00265,       # 新增
       "cache_discount": 0.000125,
       "total_cost": 0.005575,     # input + output + image - cache
   }
   ```

#### 场景 2: Batch Pricing (批量折扣)

某些 API 提供批量调用的折扣价格：

```python
# model-registry 扩展
PRICING["GPT-4o"] = {
    "input": 2.50,
    "output": 10.00,
    "cache_hit": 1.25,
    "batch": {                      # 新增
        "input": 1.25,              # 批量输入价格（原价 50%）
        "output": 5.00,             # 批量输出价格（原价 50%）
        "min_requests": 1000,       # 批量最低请求数（可选限制）
    }
}
```

#### 场景 3: 自定义折扣 / 企业合同价

```python
# cost_simulator 接受可选参数
def simulate_monthly(
    model_ids: list[str],
    monthly_calls: int,
    avg_input_tokens: int,
    avg_output_tokens: int,
    compression_ratio: float,
    cache_hit_rate: float = 0.0,
    custom_pricing_override: dict[str, dict] = None,  # 新增
) -> SimulationReport:
    """
    custom_pricing_override: 
    可用于覆盖 model-registry 的价格
    {"GPT-4o": {"input": 1.50, "output": 8.00}}
    """
```

### 9.2 扩展步骤总结

| 步骤 | 操作 | 涉及模块 |
|------|------|----------|
| 1 | 在 model-registry 的 pricing 结构体增加新字段 | model-registry |
| 2 | 在 cost-simulator 增加对应的计费函数 | cost-simulator |
| 3 | 在 CostBreakdown / SimulationReport 数据结构中增加字段 | cost-simulator |
| 4 | 在 api-gateway 的请求体中增加对应的入参 | api-gateway |
| 5 | 在前端成本模拟器 UI 增加对应控件 | frontend-ui |

### 9.3 非功能性扩展

| 扩展方向 | 说明 |
|----------|------|
| **实时价格抓取** | 从各模型官网自动抓取最新定价，通过 model-registry 更新事件推送给 cost-simulator |
| **汇率换算** | 支持美元以外的货币展示（人民币、欧元等），在展示层转换，不影响计算逻辑 |
| **历史价格回溯** | 记录价格变更历史，支持"按当时价格计算"的场景（如回顾性报告） |

---

## 附录 A: 错误处理与边界条件

| 条件 | 行为 |
|------|------|
| `model_id` 在 model-registry 中不存在 | 抛出 `UnknownModelError`，包含支持的模型列表 |
| `monthly_calls = 0` | 返回空报告（`comparisons` 为空列表，`best_value_model` 为 `N/A`） |
| `compression_ratio = 0` | 压缩后 = 压缩前，节省全部为 0，但费用正常计算 |
| `compression_ratio = 1.0` | 压缩后输入为 0，`input_cost = 0` |
| `cache_hit_rate = 0` | 无缓存命中，`cache_discount = 0` |
| `cache_hit_rate = 1.0` | 全量缓存命中，所有输入 token 走缓存价格 |
| 所有模型 `after.total` 相等 | 取 `savings_percentage` 最高的为 `best_value_model` |

## 附录 B: 与项目顶层设计的关系

本模块对应于以下设计文档章节：

- → 参见 [项目设计文档](../../design-document.md#5-价格系统--成本模拟器) — 价格系统与成本模拟器
- → 参见 [项目设计文档](../../design-document.md#74-post-apicost-simulate) — API 接口定义
- → 参见 [项目设计文档](../../design-document.md#84-面板-3对比结果) — 前端交互面板
