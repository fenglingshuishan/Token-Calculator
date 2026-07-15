# 模型注册表 (Model Registry) — 模块设计文档

> **版本**: v2.0  
> **日期**: 2026-07-06  
> **定位**: 管理所有 AI 模型的元数据，包括模型名、所属分词器分组、价格信息、可用状态。是整个系统的"数据黄页"。
>
> **修订: 2026-07-07** — 确认最终计划架构决策:
> - 模型分组从 15 组精简为 8 组（移除已废弃的 p50k_base、llama2、mistral_old、gemma2、yi 分组）
> - Phase 2 预留分组（claude、gemini）已移除（不在 Phase 1 范围内）
> - 模型数据与 backend/pricing.py 中的 MODEL_GROUPS 和 PRICING 定义保持同步
> - 前端通过 `GET /api/models` 获取定价数据，不维护独立的价格副本

---

## 目录

1. [模块概述](#1-模块概述)
2. [数据结构定义](#2-数据结构定义)
3. [完整注册表](#3-完整注册表)
4. [查询接口](#4-查询接口)
5. [价格映射表](#5-价格映射表)
6. [可用状态管理](#6-可用状态管理)
7. [与其他模块的关系](#7-与其他模块的关系)
8. [扩展指南](#8-扩展指南)

---

## 1. 模块概述

模型注册表是系统的元数据管理中心，以分组为单位维护所有 AI 模型的注册信息。每个分组对应一个特定的分词器实现（如 `o200k_base`、`llama3`），分组内绑定一组共享同一分词器的模型，以及该分组的价格数据和可用状态标记。

注册表不负责实际的 token 计数，只回答"有哪些模型"、"模型属于哪个分词器分组"、"价格是多少"、"是否已可用"这类元数据问题。→ 参见 [项目顶层设计文档](../../design-document.md#4-分词器--模型注册表)

---

## 2. 数据结构定义

### 2.1 ModelGroup 结构

```python
ModelGroup = {
    "group_id": str,            # 唯一标识，用作分词器查找键
    "name": str,                # 人类可读的显示名称
    "type": "open" | "estimated",  # 开源/估测
    "provider": str,            # 模型厂商名称
    "library": str,             # 底层分词库名称
    "models": [str],            # 属于该分组的模型名称列表
    "vocab_size": str,          # 词表大小描述
    "pricing": dict,            # 价格数据（$ / 1M tokens）
    "available": bool,          # Phase 1 是否可用
    "phase": int                # 所属阶段 (1 或 2)
}
```

### 2.2 字段详细说明

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `group_id` | `str` | 是 | 唯一标识。同时用作分词器注册表中的查找键，也是 `POST /api/tokenize` 接口中 `group_ids` 阵列的值。采用小写+下划线命名。取值示例：`o200k_base`、`llama3`、`claude` |
| `name` | `str` | 是 | 用户友好的显示名称，用于前端下拉列表和表格。取值示例：`"OpenAI o200k_base"`、`"Meta Llama 3"` |
| `type` | `str` | 是 | 分组类型。`"open"` 表示该分词器已开源可精确计数；`"estimated"` 表示使用估算法（字符 × 系数），仅用于闭源模型的近似估算 |
| `provider` | `str` | 是 | 模型厂商，用于前端按厂商筛选。取值示例：`"OpenAI"`、`"Meta"`、`"Alibaba"` |
| `library` | `str` | 是 | 底层使用的分词库名称。决定 `ModelRegistry` 在运行时查找哪个 `TokenizerBase` 实现。取值示例：`"tiktoken"`、`"transformers"`、`"sentencepiece"`、`"mistral-common"` |
| `models` | `list[str]` | 是 | 该分词器分组下的具体模型名称列表。至少包含一个元素。模型名称同时也是 `pricing` 字典的键。取值示例：`["GPT-4o", "GPT-4o-mini", "GPT-4.1"]` |
| `vocab_size` | `str` | 是 | 词表大小的文字描述。用于前端信息展示。取值示例：`"~100K"`、`"128K"`、`"152K"` |
| `pricing` | `dict` | 是 | 模型价格映射。外层键为模型名称，内层包含 `input`、`output`、`cache_hit` 三个价格字段。详见下文 [2.3 Pricing 子结构](#23-pricing-子结构) |
| `available` | `bool` | 是 | 可用性标记。当前所有 8 个分组均为 `true`。保留此字段以便未来扩展，新增分组时设为 `true` |
| `phase` | `int` | 是 | 实现阶段标记。当前所有分组均为 `1`。保留此字段以便未来扩展 |

### 2.3 Pricing 子结构

```python
pricing = {
    "GPT-4o": {
        "input": float,       # 输入价格（$ / 1M tokens）
        "output": float,      # 输出价格（$ / 1M tokens）
        "cache_hit": float | None  # 缓存命中价格（$ / 1M tokens），无缓存时填 None
    },
    ...
}
```

| 字段 | 类型 | 说明 |
|---|---|---|
| `input` | `float` | 每 1M token 的输入价格（美元）。对应模型的 prompt / input 定价 |
| `output` | `float` | 每 1M token 的输出价格（美元）。对应模型的 completion / output 定价 |
| `cache_hit` | `float` | 每 1M token 的缓存命中价格（美元）。`None` 表示该模型不支持或未提供缓存定价。仅在启用了 Prompt Caching 的模型上有值 |

---

## 3. 完整注册表

### 3.1 分组总览（8 组，全部可用）

| group_id | 显示名称 | type | provider | library | 模型数 | vocabsize |
|---|---|---|---|---|---|---|
| `o200k_base` | OpenAI (o200k_base) | open | OpenAI | tiktoken | 7 | 200K |
| `cl100k_base` | OpenAI Legacy + Embeddings (cl100k_base) | open | OpenAI | tiktoken | 4 | 100K |
| `llama3` | Meta Llama 4 | open | Meta | transformers | 3 | 128K |
| `qwen` | Alibaba Qwen 3 | open | Alibaba | transformers | 3 | 152K |
| `deepseek_v4` | DeepSeek V4 | open | DeepSeek | transformers | 2 | 128K |
| `mistral` | Mistral AI | open | Mistral AI | mistral-common | 3 | 131K |
| `gemma` | Google Gemma | open | Google | sentencepiece | 2 | 256K |
| `glm` | Z.ai GLM-4.7 | open | Zhipu AI | transformers | 3 | 65K |

> 所有分组均为 Phase 1 可用。已移除的 5 个废弃分组（p50k_base、llama2、mistral_old、gemma2、yi）不再维护。Phase 2 预留分组（claude、gemini）已从注册表中移除。

### 3.2 分组内模型清单与定价

价格单位：美元 / 1M tokens。数据同步自 `backend/pricing.py`。

#### o200k_base (tiktoken)
| 模型 | input | output | cache_hit |
|---|---|---|---|
| GPT-5.6 Luna | 1.00 | 6.00 | 0.10 |
| GPT-4.1 | 2.00 | 8.00 | 1.00 |
| GPT-4.1-mini | 0.40 | 1.60 | 0.20 |
| GPT-4.1-nano | 0.10 | 0.40 | 0.05 |
| GPT-4o | 2.50 | 10.00 | 1.25 |
| GPT-4o-mini | 0.15 | 0.60 | 0.075 |
| o4-mini | 1.10 | 4.40 | 0.55 |

#### cl100k_base (tiktoken)
| 模型 | input | output | cache_hit |
|---|---|---|---|
| GPT-4 | 30.00 | 60.00 | null |
| GPT-4-turbo | 10.00 | 30.00 | null |
| text-embedding-3-small | 0.02 | 0.02 | null |
| text-embedding-3-large | 0.13 | 0.13 | null |

> text-embedding-3 系列为嵌入模型，input 与 output 价格相同。前端在单元格中正常显示。

#### llama3 (transformers)
| 模型 | input | output | cache_hit |
|---|---|---|---|
| Llama 4 Maverick | 0.27 | 0.85 | 0.09 |
| Llama 4 Scout | 0.11 | 0.34 | 0.05 |
| Llama 3.3 70B | 0.30 | 0.80 | 0.08 |

#### qwen (transformers)
| 模型 | input | output | cache_hit |
|---|---|---|---|
| Qwen 3.7 Plus | 0.32 | 1.28 | 0.10 |
| Qwen3-235B | 0.18 | 0.54 | null |
| Qwen 3.6 27B | 0.29 | 3.20 | null |

#### deepseek_v4 (transformers)
| 模型 | input | output | cache_hit |
|---|---|---|---|
| DeepSeek V4 Flash | 0.14 | 0.28 | 0.0028 |
| DeepSeek V4 Pro | 0.435 | 0.87 | 0.0087 |

#### mistral (mistral-common)
| 模型 | input | output | cache_hit |
|---|---|---|---|
| Mistral Large 3 | 0.50 | 1.50 | 0.25 |
| Mistral Small 4 | 0.15 | 0.60 | 0.075 |
| Mistral Medium 3.5 | 1.50 | 7.50 | 0.75 |

#### gemma (sentencepiece)
| 模型 | input | output | cache_hit |
|---|---|---|---|
| Gemma 4 12B | 0.15 | 0.60 | 0.10 |
| Gemma 3 27B | 0.15 | 0.60 | 0.10 |

#### glm (transformers)
| 模型 | input | output | cache_hit |
|---|---|---|---|
| GLM-4.7 | 0.60 | 2.20 | 0.11 |
| GLM-4.5 | 0.50 | 2.00 | 0.10 |
| GLM-4.5-Air | 0.20 | 1.10 | 0.05 |

---

## 4. 查询接口

`ModelRegistry` 对外提供以下查询方法。所有方法均为纯数据查询，不涉及 I/O。

### 4.1 `get_by_id(group_id: str) -> ModelGroup`

按 `group_id` 精确查找单个分组。

| 参数 | 类型 | 说明 |
|---|---|---|
| `group_id` | `str` | 分组标识，如 `"o200k_base"`、`"llama3"` |
| 返回 | `ModelGroup` | 匹配的分组数据。不区分大小写（内部统一小写匹配） |

**行为**:
- 精确匹配 `group_id`，忽略大小写。
- 若未找到，返回 `None`（而非抛异常），调用方自行处理。

**使用场景**:
- `POST /api/tokenize` 内部根据请求中的 `group_ids` 逐个查找分组，获取分词器工厂索引。
- → 参见 [tokenizer-layer 模块](../tokenizer-layer/README.md#tokenizer-注册与查找)

### 4.2 `get_by_provider(provider: str, include_unavailable: bool = False) -> List[ModelGroup]`

按供应商筛选分组。

| 参数 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `provider` | `str` | - | 供应商名称，如 `"OpenAI"`、`"Meta"`、`"Google"` |
| `include_unavailable` | `bool` | `false` | 是否包含 `available=false` 的分组 |
| 返回 | `List[ModelGroup]` | - | 匹配的分组列表，按 `group_id` 字母序排列 |

**行为**:
- 按 `provider` 精确匹配。
- `include_unavailable=false` 时，仅返回 `available=true` 的分组。

**使用场景**:
- 前端按供应商筛选模型列表（仅 Phase 1 可用分组）。
- 成本模拟器按供应商聚合价格数据。

### 4.3 `list_available() -> List[ModelGroup]`

列出所有可用分组。

```python
def list_available() -> List[ModelGroup]:
    """返回 available == true 的所有分组"""
```

| 返回 | 说明 |
|---|---|
| `List[ModelGroup]` | 8 个开源分组，按 `group_id` 字母序排列 |

**行为**:
- 等价于遍历全表，过滤 `available == true` 的分组。
- 结果顺序稳定（按 `group_id` 字母序），前端无需再排序。

**使用场景**:
- `GET /api/models` 默认返回 `list_available()` 的结果（前端模型选择器）。
- 前端 Token 对比表的默认模型列表。
- → 参见 [api-gateway 模块](../api-gateway/README.md#get-apimodels)

### 4.4 `list_all() -> List[ModelGroup]`

列出所有 8 个分组。

```python
def list_all() -> List[ModelGroup]:
    """返回所有分组，按 group_id 字母序排列"""
```

| 返回 | 说明 |
|---|---|
| `List[ModelGroup]` | 全部 8 个分组，按 `group_id` 字母序排列 |

**行为**:
- 返回完整的注册表数据。
- 排序规则：`group_id` 字母序。

**使用场景**:
- 后端生成完整的模型清单供成本模拟器调取价格数据。
- → 参见 [cost-simulator 模块](../cost-simulator/README.md#数据源)

### 4.5 `get_models_by_group(group_id: str) -> List[str]`

获取指定分组下的模型名称列表。

| 参数 | 类型 | 说明 |
|---|---|---|
| `group_id` | `str` | 分组标识 |
| 返回 | `List[str]` | 模型名称列表 |

**行为**:
- 若 `group_id` 不存在，返回空列表 `[]`。

**使用场景**:
- 前端分组展开时展示该分组下的所有模型。
- 成本模拟器获取某分组的默认模型用于价格计算。

### 4.6 `get_pricing(model_id: str) -> dict`

按模型名称直接查询价格。

| 参数 | 类型 | 说明 |
|---|---|---|
| `model_id` | `str` | 模型名称，如 `"GPT-4o"`、`"DeepSeek V3"` |
| 返回 | `dict` | 包含 `input`、`output`、`cache_hit` 的字典 |

**行为**:
- 遍历所有分组，查找 `models` 列表中匹配的模型。
- 若未找到，返回 `{"input": None, "output": None, "cache_hit": None}`。

**使用场景**:
- `POST /api/tokenize` 中计算 cost。
- → 参见 [tokenizer-layer 模块](../tokenizer-layer/README.md#api-tokenize-内部流程)

### 4.7 批量查询接口 (Map 形式)

为减少遍历开销，提供批量版本的查询：

| 方法 | 参数 | 返回类型 | 说明 |
|---|---|---|---|
| `get_by_ids(group_ids: List[str])` | 分组标识列表 | `Dict[str, ModelGroup]` | Key 为 group_id，Value 为分组对象 |
| `get_pricings(model_ids: List[str])` | 模型名称列表 | `Dict[str, dict]` | Key 为 model_id，Value 为价格字典 |

---

## 5. 价格映射表

### 5.1 完整模型价格汇总

以下为全量模型价格一览表，按 $/1M tokens 计价。数据源 → `backend/pricing.py` 中的 `PRICING` 字典，与 [`MODEL_GROUPS` 定义](#32-分组内模型清单与定价) 保持同步。

| 模型 | input ($) | output ($) | cache_hit ($) | 所属分组 |
|---|---|---|---|---|
| GPT-5.6 Luna | 1.00 | 6.00 | 0.10 | o200k_base |
| GPT-4.1 | 2.00 | 8.00 | 1.00 | o200k_base |
| GPT-4.1-mini | 0.40 | 1.60 | 0.20 | o200k_base |
| GPT-4.1-nano | 0.10 | 0.40 | 0.05 | o200k_base |
| GPT-4o | 2.50 | 10.00 | 1.25 | o200k_base |
| GPT-4o-mini | 0.15 | 0.60 | 0.075 | o200k_base |
| o4-mini | 1.10 | 4.40 | 0.55 | o200k_base |
| GPT-4 | 30.00 | 60.00 | - | cl100k_base |
| GPT-4-turbo | 10.00 | 30.00 | - | cl100k_base |
| text-embedding-3-small | 0.02 | 0.02 | - | cl100k_base |
| text-embedding-3-large | 0.13 | 0.13 | - | cl100k_base |
| Llama 4 Maverick | 0.27 | 0.85 | 0.09 | llama3 |
| Llama 4 Scout | 0.11 | 0.34 | 0.05 | llama3 |
| Llama 3.3 70B | 0.30 | 0.80 | 0.08 | llama3 |
| Qwen 3.7 Plus | 0.32 | 1.28 | 0.10 | qwen |
| Qwen3-235B | 0.18 | 0.54 | - | qwen |
| Qwen 3.6 27B | 0.29 | 3.20 | - | qwen |
| DeepSeek V4 Flash | 0.14 | 0.28 | 0.0028 | deepseek_v4 |
| DeepSeek V4 Pro | 0.435 | 0.87 | 0.0087 | deepseek_v4 |
| Mistral Large 3 | 0.50 | 1.50 | 0.25 | mistral |
| Mistral Small 4 | 0.15 | 0.60 | 0.075 | mistral |
| Mistral Medium 3.5 | 1.50 | 7.50 | 0.75 | mistral |
| Gemma 4 12B | 0.15 | 0.60 | 0.10 | gemma |
| Gemma 3 27B | 0.15 | 0.60 | 0.10 | gemma |
| GLM-4.7 | 0.60 | 2.20 | 0.11 | glm |
| GLM-4.5 | 0.50 | 2.00 | 0.10 | glm |
| GLM-4.5-Air | 0.20 | 1.10 | 0.05 | glm |

### 5.2 价格数据的维护策略

- 价格数据在 `backend/pricing.py` 中以 `PRICING` 字典定义。`MODEL_GROUPS` 中的各分组引用 `PRICING` 中的键名。
- 更新价格时，修改 `pricing.py` 中的对应条目即可。无需修改其他模块的代码。
- 不同来源的价格取最新公开定价（以各模型厂商官网为准）。
- 不支持缓存定价的模型，`cache_hit` 填入 `null`，前端据此显示 `-` 或 `N/A`。
- **前端不维护独立的定价副本**。前端通过 `GET /api/models` 获取包含定价数据的完整模型分组列表。如需刷价格数据，刷新页面即可。

---

## 6. 可用状态管理

Phase 1 所有 8 个分组**全部可用**。所有模型可提供 token 计数、价格计算和成本模拟。当前不维护 Phase 2 预留分组。

### 6.1 新增分组流程

如需在未来添加新分组，按以下步骤操作：

1. 在 `backend/pricing.py` 的 `MODEL_GROUPS` 列表中添加新分组定义。
2. 在 `PRICING` 字典中添加该分组内所有模型的价格数据。
3. 确认 `library` 字段指向 tokenizer-layer 中已支持的分词库（tiktoken / transformers / sentencepiece / mistral-common）。
4. 无需修改 api-gateway 或 frontend-ui——数据通过 `GET /api/models` 动态交付。

---

## 7. 与其他模块的关系

### 7.1 依赖关系总览

```
┌─────────────────────────────────────────────────────────────┐
│                     Model Registry                           │
│                     (数据提供方)                              │
└────────────┬─────────────┬──────────────┬───────────────────┘
             │             │              │
             ▼             ▼              ▼
      ┌──────────┐ ┌──────────────┐ ┌────────────┐
      │Tokenizer │ │Pricing       │ │API Gateway │
      │Layer     │ │Simulator     │ │(数据源)    │
      └──────────┘ └──────────────┘ └────────────┘
                                           │
                                           ▼
                                    ┌────────────┐
                                    │Frontend UI │
                                    │(展示层)    │
                                    └────────────┘
```

### 7.2 被 tokenizer-layer 依赖

→ 参见 [tokenizer-layer 模块](../tokenizer-layer/README.md#模块概述)

- **使用字段**: `group_id`、`type`、`library`
- **使用方式**: `TokenRegistry` 初始化时调用 `registry.get_by_id(group_id)` 获取 `library` 字段，根据 `library` 值（`"tiktoken"` / `"transformers"` / `"sentencepiece"` / `"mistral-common"` / `"estimate"`）匹配对应的 `TokenizerBase` 实现类。
- **关键逻辑**:
  ```python
  # 伪代码示意
  entry = model_registry.get_by_id("o200k_base")
  if entry.library == "tiktoken":
      tokenizer = TiktokenTokenizer(group_id)
  elif entry.library == "transformers":
      tokenizer = HfTokenizer(group_id)
  ```
- **影响**: 如果新增一个分组，但其 `library` 字段指向一个尚未实现的库，tokenizer-layer 需要在匹配分支中添加新 case。

### 7.3 被 cost-simulator 依赖

→ 参见 [cost-simulator 模块](../cost-simulator/README.md#数据源)

- **使用字段**: `pricing`、`models`
- **使用方式**: 成本模拟器调用 `registry.get_pricings(model_ids)` 批量获取价格数据，结合压缩前后的 token 数计算费用。
- **关键逻辑**:
  ```python
  # 伪代码示意
  prices = model_registry.get_pricings(["GPT-4o", "DeepSeek V3"])
  # 返回: {"GPT-4o": {"input": 2.50, "output": 10.00, "cache_hit": 1.25}, ...}
  ```
- **影响**: 价格数据完全由注册表维护。cost-simulator 不维护自己的价格副本。如果注册表价格过期，成本模拟结果也会过期。

### 7.4 被 api-gateway 依赖

→ 参见 [api-gateway 模块](../api-gateway/README.md#get-apimodels)

- **使用字段**: 全字段
- **使用方式**: `GET /api/models` 路由调用 `registry.list_available()` 或 `registry.list_all()`（取决于查询参数 `include_unavailable`）返回 JSON 格式的模型列表。
- **API 响应格式**:
  ```json
  {
    "groups": [
      {
        "id": "o200k_base",
        "name": "OpenAI o200k_base",
        "type": "open",
        "provider": "OpenAI",
        "models": ["GPT-4o", "GPT-4o-mini", "GPT-4.1"],
        "pricing": {"input": 2.50, "output": 10.00, "cache_hit": 1.25},
        "available": true
      }
    ]
  }
  ```
- **影响**: `api-gateway` 是注册表数据对外的唯一出口。所有 HTTP 客户端都通过此接口获取模型元数据。

### 7.5 被 frontend-ui 依赖

→ 参见 [frontend-ui 模块](../frontend-ui/README.md#顶部模型选择器)

- **使用字段**: `group_id`、`name`、`type`、`provider`、`models`、`available`、`pricing`
- **使用方式**: 前端通过 `GET /api/models` 获取注册表数据，用于：
  1. **模型选择器** — `group_id` 作为下拉选项值，`name` 作为显示文本。
  2. **多模型对比表** — 勾选多个 `models` 列表中的模型名，逐行展示 token 数和费用。
  3. **类型标签** — `type` 字段决定显示 "开源" 或 "估测" 标签。
  4. **价格展示** — `pricing` 中的 input / output / cache_hit 渲染为价格表格。

### 7.6 依赖方向

| 使用方 | 读取字段 | 写入字段 | 依赖性质 |
|---|---|---|---|
| tokenizer-layer | `group_id`, `type`, `library` | 无 | 读依赖（强） |
| cost-simulator | `pricing`, `models` | 无 | 读依赖（强） |
| api-gateway | 全字段 | 无 | 读依赖（强） |
| frontend-ui | 全字段 | 无 | 间接读依赖（通过 api-gateway） |

所有外部模块对 model-registry 均为**只读依赖**。注册表数据只能通过直接修改注册表定义来变更（参见 [扩展指南](#8-扩展指南)）。

---

## 8. 扩展指南

### 8.1 添加新模型到现有分组

如果某个已有分组中新增了一个模型（例如 OpenAI 发布了 GPT-5，使用 o200k_base 分词器）：

**步骤**:
1. 在 `registry.py` 中找到目标分组的定义。
2. 将新模型名称追加到该分组的 `models` 列表中。
3. 在同样的 `pricing` 字典中添加新模型的价格条目。
4. （可选）如果新模型支持缓存定价，补充 `cache_hit` 字段；否则填入 `None`。

**示例**: 在 o200k_base 分组下新增 GPT-5
```diff
  "o200k_base": {
      "group_id": "o200k_base",
      "name": "OpenAI o200k_base",
      "type": "open",
      "provider": "OpenAI",
      "library": "tiktoken",
      "models": [
-         "GPT-4o", "GPT-4o-mini", "GPT-4.1", "GPT-4.1-mini", "GPT-4.1-nano"
+         "GPT-4o", "GPT-4o-mini", "GPT-4.1", "GPT-4.1-mini", "GPT-4.1-nano",
+         "GPT-5"
      ],
      "pricing": {
          "GPT-4o":       {"input": 2.50,  "output": 10.00, "cache_hit": 1.25},
          "GPT-4o-mini":  {"input": 0.15,  "output": 0.60,  "cache_hit": 0.075},
          "GPT-4.1":      {"input": 2.00,  "output": 8.00,  "cache_hit": 1.00},
          "GPT-4.1-mini": {"input": 0.40,  "output": 1.60,  "cache_hit": 0.20},
          "GPT-4.1-nano": {"input": 0.10,  "output": 0.40,  "cache_hit": 0.05},
+         "GPT-5":       {"input": 3.00,  "output": 12.00, "cache_hit": 1.50},
      },
      ...
  }
```

**验证清单**:
- [ ] 模型名在 `models` 列表中。
- [ ] 模型名在 `pricing` 字典中作为 key 存在。
- [ ] `pricing` 中的 input / output / cache_hit 都有值（不支持缓存填 `None`）。

### 8.2 添加全新分组

如果添加一个全新的模型家族（例如 Cohere Command R+ 使用的全新分词器）：

**前置条件**: 确认该模型使用的分词器类型。可能有四种情况：
- **已有库支持**（如 tiktoken / transformers / sentencepiece）— 只需添加注册表条目 + 确认分词器工厂支持该库。
- **需要新库** — 需要：
  1. 在 `requirements.txt` 中添加依赖库。
  2. 在 tokenizer-layer 中实现新的 `TokenizerBase` 子类。
  3. 在 `TokenRegistry` 的工厂分支中添加匹配该 `library` 值的新 case。

**步骤**:
1. **在注册表中添加新分组** — 在 `REGISTRY` 字典中插入一条新记录。
2. **明确 `library` 字段** — 确保 `library` 值与 tokenizer-layer 中已有的或新实现的工厂分支匹配。
3. **设置 `available` 和 `phase`** — Phase 1 实现设为 `true` / `1`，预留设为 `false` / `2`。
4. **提供至少一个模型和其定价** — `models` 不能为空，`pricing` 不能为空。
5. **确认 tokenizer-layer 工厂分支能处理新的 `library` 值** — 如果不能，同时修改 tokenizer-layer。

**完整示例**: 新增 Cohere Command R+ 分组

```python
# 1. 注册表定义
"command_r": {
    "group_id": "command_r",
    "name": "Cohere Command R",
    "type": "open",
    "provider": "Cohere",
    "library": "transformers",  # Cohere 使用 HuggingFace transformers 分词
    "models": [
        "Command R+",
        "Command R",
    ],
    "vocab_size": "256K",
    "pricing": {
        "Command R+": {"input": 0.50, "output": 1.50, "cache_hit": None},
        "Command R":  {"input": 0.15, "output": 0.60, "cache_hit": None},
    },
    "available": true,
},
```

```python
# 2. tokenizer-layer 工厂新增分支（仅在 library 值为全新值时需要）
# 本例中 library = "transformers"，已有 HfTokenizer 覆盖，无需改动
```

**验证清单**:
- [ ] `group_id` 全局唯一，且与 tokenizer-layer 中的查找键一致。
- [ ] `library` 字段与 tokenizer-layer 工厂分支中的一个值匹配。
- [ ] `models` 列表非空。
- [ ] `pricing` 包含 `models` 列表中每个模型的完整价格（input / output / cache_hit）。
- [ ] `provider` 名称与已有供应商相同或一致（按厂商维度筛选时行为正确）。
- [ ] 确保 `available` 为 `true`（所有分组 Phase 1 即可用）。
- [ ] 如果使用了新的 `library` 值，确保 `requirements.txt` 已添加对应依赖。
- [ ] 前端无需修改（因为前端通过 `GET /api/models` 动态渲染，注册表一变更前端自动拿新数据）。

### 8.3 更新价格

**频率**: 建议与各模型厂商的定价变更保持同步（季度审查或收到价格变更通知时更新）。

**步骤**:
1. 定位到目标模型所在的 `pricing` 字典条目。
2. 直接修改 `input`、`output` 或 `cache_hit` 的数值。
3. 无需触及外部模块或 API 路由，变更自动通过 `GET /api/models` 反射到前端。

**示例**: GPT-4o 降价
```diff
  "GPT-4o": {
-     "input": 2.50,
-     "output": 10.00,
-     "cache_hit": 1.25,
+     "input": 2.00,
+     "output": 8.00,
+     "cache_hit": 1.00,
  },
```

**注意**: 价格更新后，成本模拟器的计算结果会立即反映新价格。建议在更新前通知测试团队确认预期。

### 8.4 扩展检查清单总结

| 场景 | 修改 pricing.py | 修改 tokenizer-layer | 修改 requirements.txt | 修改前端 |
|---|---|---|---|---|
| 已有分组新增模型 | 是 | 否 | 否 | 否 |
| 新增分组（已有库） | 是 | 否 | 否 | 否 |
| 新增分组（新库） | 是 | 是 | 是 | 否 |
| 更新价格 | 是 | 否 | 否 | 否 |

---

> **本模块文档的版本管理**: 本文档与 `backend/tokenizers/registry.py` 中的数据结构声明共同构成 model-registry 的权威定义。如注册表数据变更，请同步更新本文档中的表格和描述，确保设计文档与实现保持一致。
