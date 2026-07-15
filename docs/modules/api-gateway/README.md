# API 网关 (API Gateway) — 模块设计文档

> **版本**: v2.0  
> **日期**: 2026-07-06  
> **定位**: FastAPI HTTP 入口层，纯胶水层，不做业务逻辑。定义所有 RESTful 端点、Pydantic 请求/响应模型、CORS 配置、统一错误处理。
>
> **修订: 2026-07-07** — 确认最终计划架构决策:
> - 压缩策略枚举已简化为 `"rule" | "llm"`（移除 "context"）
> - `GET /api/models` 响应中嵌入定价数据（不再需要独立的 `/api/pricing` 端点）
> - `CORS_ORIGINS` 改为通过环境变量配置（不再硬编码）
> - 所有端点仅使用 `GET` 和 `POST` 方法，无 DELETE 端点
> - `POST /api/compress` 的 `CompressRequest` 移除了 `context_history` 字段  

---

## 目录

1. [模块概述](#1-模块概述)
2. [端点全景表](#2-端点全景表)
3. [端点详细定义](#3-端点详细定义)
4. [Pydantic 模型汇总](#4-pydantic-模型汇总)
5. [CORS 配置](#5-cors-配置)
6. [错误处理规范](#6-错误处理规范)
7. [中间件设计](#7-中间件设计)
8. [与其他模块的关系](#8-与其他模块的关系)
9. [OpenAPI 文档](#9-openapi-文档)
10. [测试策略](#10-测试策略)

---

## 1. 模块概述

API 网关是系统的唯一 HTTP 入口，基于 FastAPI 构建。它负责接收前端请求、参数校验、路由分发、统一异常捕获与格式化响应，并将实际业务逻辑全部委派给下层核心模块。

### 1.1 薄胶水层定位

网关层遵循 **"只做路由，不做业务"** 原则：

- **负责**：请求反序列化、参数校验（Pydantic）、路由分发、响应序列化、CORS、请求日志、耗时统计、统一错误格式
- **不负责**：分词、压缩、成本计算、模型元数据管理、配置持久化——这些全部委派给专用模块
- **不直接访问**：文件系统、数据库、外部 API——一切 I/O 操作经由下层模块执行

### 1.2 设计原则

| 原则 | 说明 |
|---|---|
| **单一职责** | 每个端点仅做参数校验 + 委派调用，不引入额外逻辑 |
| **防御性校验** | 所有输入在 Pydantic 层完成边界校验（长度、范围、枚举），校验失败返回 422 而非 500 |
| **统一错误面** | 所有异常（业务级、系统级）收敛到同一 JSON 错误格式，前端只需解析一种结构 |
| **无状态** | 网关层不持有任何会话状态，所有请求上下文由调用方传递 |
| **可观测** | 每个请求记录方法、路径、状态码、耗时，输出结构化日志 |

→ 参见 [项目顶层设计文档](../../design-document.md#7-后端-api-设计)

---

## 2. 端点全景表

| # | 方法 | 路径 | 委派模块 | 用途 |
|---|---|---|---|---|
| 1 | `GET` | `/api/models` | model-registry | 返回所有模型分组（含各分组内模型的定价数据） |
| 2 | `POST` | `/api/tokenize` | tokenizer-layer | 单/多模型 token 计数 |
| 3 | `POST` | `/api/compress` | compression-engine | 执行语义压缩 |
| 4 | `POST` | `/api/cost-simulate` | cost-simulator | 月度成本模拟 |
| 5 | `POST` | `/api/export` | 无委派（直接返回） | 返回压缩后文本 |
| 7 | `GET` | `/api/config` | config-store | 读取持久化配置 |
| 8 | `POST` | `/api/config` | config-store | 保存持久化配置 |

---

## 3. 端点详细定义

### 3.1 GET /api/models

获取所有模型分组列表，包含每个分组下的模型名称、类型、可用状态。

**委派模块**：→ 参见 [模型注册表](../model-registry/README.md#4-查询接口)

**请求参数**：无

**响应体 schema**：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `groups` | `list[ModelGroup]` | 是 | 全量模型分组列表。每个元素的详细字段见 [模型注册表 ModelGroup 结构](../model-registry/README.md#21-modelgroup-结构) |

**错误场景**：无预期业务错误。仅在 `INTERNAL_ERROR` 时返回 500。

### 3.2 POST /api/tokenize

对给定文本执行一个或多个分词器分组的 token 计数。支持 input / output / cache 三种模式。

**委派模块**：→ 参见 [分词器层](../tokenizer-layer/README.md)

**请求体** —— `TokenizeRequest`：

| 字段 | 类型 | 必填 | 约束 | 说明 |
|---|---|---|---|---|
| `text` | `string` | 是 | `1 ≤ length ≤ 100000` | 待分词文本 |
| `group_ids` | `list[string]` | 是 | `1 ≤ length ≤ 10` | 分词器分组 ID 列表，取值来自 model-registry 的 `group_id` |
| `mode` | `string` | 否 | 枚举：`"input"` / `"output"` / `"cache"` | 计数模式，默认 `"input"` |
| `cache_hit_tokens` | `int` | 否 | `≥ 0` | 缓存命中 token 数，仅在 `mode = "cache"` 时有效 |

**响应体** —— `TokenizeResponse`：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `char_count` | `int` | 是 | 输入文本的字符总数 |
| `results` | `list[TokenizeResult]` | 是 | 每个 group_id 对应的计数结果，顺序与请求的 `group_ids` 一致 |
| `cache_info` | `CacheInfo` | 否 | 缓存命中信息。仅 `mode = "cache"` 时存在 |

**错误场景**：

| 错误码 | HTTP 状态 | 触发条件 |
|---|---|---|
| `MODEL_NOT_FOUND` | 400 | 请求的 `group_id` 在模型注册表中不存在 |
| `MODEL_NOT_AVAILABLE` | 503 | 请求的 `group_id` 对应分词器为 Phase 2 预留，尚未实现 |
| `TEXT_TOO_LONG` | 413 | `text` 长度超过 100,000 字符上限 |

### 3.3 POST /api/compress

对原始文本执行语义压缩，支持三种策略和三级压缩力度。

**委派模块**：→ 参见 [压缩引擎](../compression-engine/README.md)

**请求体** —— `CompressRequest`：

| 字段 | 类型 | 必填 | 约束 | 说明 |
|---|---|---|---|---|
| `text` | `string` | 是 | `1 ≤ length ≤ 100000` | 待压缩的原始文本 |
| `strategy` | `string` | 否 | 枚举：`"rule"` / `"llm"` | 压缩策略，默认 `"rule"` |
| `level` | `string` | 否 | 枚举：`"light"` / `"medium"` / `"aggressive"` | 压缩力度，默认 `"medium"` |
| `target_ratio` | `float` | 否 | `0.1 ≤ value ≤ 0.9` | 目标压缩率（压缩后/原始），不指定则由引擎自动决定 |
| `llm_config` | `LLMConfig` | 否 | — | LLM 压缩配置（API key、模型选择），仅在 `strategy = "llm"` 时需要 |

**响应体** —— `CompressResponse`：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `original_text` | `string` | 是 | 压缩前的原始文本，用于前端对比展示 |
| `compressed_text` | `string` | 是 | 压缩后的结果文本 |
| `strategy` | `string` | 是 | 实际使用的策略（可能与请求不一致，引擎可降级） |
| `changes` | `list[CompressionChange]` | 是 | 压缩变更明细，每条记录一次文本替换操作 |
| `stats` | `CompressionStats` | 是 | 压缩统计信息（原长度、压缩后长度、压缩率、节省字符数） |

> **Token 计量集成**: 压缩完成后，前端应额外调用 `POST /api/tokenize` 分别获取原始文本和压缩后文本在各模型下的 token 数，用于面板 3 的对比表展示。该数据不由本端点返回（分离关注点：压缩引擎只压缩，分词器层只计数）。自 Phase 1 起，`/api/tokenize` 已使用真实分词器（Tiktoken / Hf / SentencePiece / Mistral）替代 `len*0.25` 估算法。

**错误场景**：

| 错误码 | HTTP 状态 | 触发条件 |
|---|---|---|
| `TEXT_TOO_LONG` | 413 | `text` 长度超过 100,000 字符上限 |
| `COMPRESSION_FAILED` | 500 | 压缩引擎内部错误（如 LLM 调用超时、规则引擎异常） |

### 3.4 POST /api/cost/simulate

模拟指定调用量下各模型的月度费用，对比压缩前后成本差异。

**委派模块**：→ 参见 [成本模拟器](../cost-simulator/README.md)

**请求体** —— `SimulateRequest`：

| 字段 | 类型 | 必填 | 约束 | 说明 |
|---|---|---|---|---|
| `monthly_calls` | `int` | 否 | `1 ≤ value ≤ 10000000` | 月调用次数，默认 10000 |
| `avg_input_tokens` | `int` | 否 | `≥ 1` | 每次调用的平均输入 token 数，默认 520 |
| `avg_output_tokens` | `int` | 否 | `≥ 0` | 每次调用的平均输出 token 数，默认 200 |
| `cache_hit_rate` | `float` | 否 | `0.0 ≤ value ≤ 1.0` | 缓存命中率，默认 0.0 |
| `compression_ratio` | `float` | 否 | `0.0 ≤ value ≤ 1.0` | 压缩后 token / 原始 token 比率，默认 0.0（不压缩） |
| `model_ids` | `list[string]` | 是 | `1 ≤ length ≤ 10` | 待模拟的模型 ID 列表 |

**响应体** —— `SimulateResponse`：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `monthly_calls` | `int` | 是 | 月调用次数（回显请求参数） |
| `comparisons` | `list[ModelComparison]` | 是 | 每个模型的费用对比数据 |
| `best_value_model` | `string` | 是 | 性价比最优的模型 ID |

**错误场景**：

| 错误码 | HTTP 状态 | 触发条件 |
|---|---|---|
| `MODEL_NOT_FOUND` | 400 | 请求的 `model_ids` 中存在未注册的模型 ID |

### 3.5 POST /api/export

直接返回请求中的文本内容，用于前端"一键复制压缩后 Prompt"功能。此端点不做任何业务处理。

**委派模块**：无。网关层直接返回 `{"text": request.text}`。

**请求体** —— `ExportRequest`：

| 字段 | 类型 | 必填 | 约束 | 说明 |
|---|---|---|---|---|
| `text` | `string` | 是 | `1 ≤ length ≤ 100000` | 待导出的文本 |

**响应体**：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `text` | `string` | 是 | 原样返回的文本 |

**错误场景**：

| 错误码 | HTTP 状态 | 触发条件 |
|---|---|---|
| `TEXT_TOO_LONG` | 413 | `text` 长度超过 100,000 字符上限 |

### 3.6 GET /api/config

读取先前保存的配置文件。

**委派模块**：→ 参见 [config-store](../config-store/README.md)

**请求参数**：无

**响应体** —— `ConfigResponse`：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `config` | `dict` | 是 | 完整的配置键值对。无配置时返回空 `{}` |

**错误场景**：无预期业务错误。

### 3.7 POST /api/config

保存配置到持久化存储。

**委派模块**：→ 参见 [config-store](../config-store/README.md)

**请求体** —— `ConfigRequest`：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `config` | `dict` | 是 | 配置键值对。value 仅支持 `string / number / boolean` 类型 |

**响应体**：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `saved` | `boolean` | 是 | 固定为 `true`，表示保存成功 |
| `config` | `dict` | 是 | 回显已保存的配置内容 |

**错误场景**：无预期业务错误。

---

## 4. Pydantic 模型汇总

### 4.1 TokenizeRequest

| 字段 | 类型 | 必填 | 默认值 | 约束 | 说明 |
|---|---|---|---|---|---|
| `text` | `str` | 是 | — | `min_length=1, max_length=100000` | 待分词文本 |
| `group_ids` | `list[str]` | 是 | — | `min_length=1, max_length=10` | 分词器分组 ID 列表 |
| `mode` | `Literal["input", "output", "cache"]` | 否 | `"input"` | — | 计数模式 |
| `cache_hit_tokens` | `int \| None` | 否 | `None` | `ge=0` | 缓存命中 token 数（cache 模式） |

### 4.2 TokenizeResponse

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `char_count` | `int` | 是 | 输入文本的 Unicode 字符数，由后端统一计算（与分词器无关） |
| `results` | `list[TokenizeResult]` | 是 | 每个 group_id 的计数结果 |
| `cache_info` | `CacheInfo \| None` | 否 | 缓存命中信息 |

### 4.3 TokenizeResult

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `group_id` | `str` | 是 | 分词器分组 ID |
| `token_count` | `int` | 是 | 该分组下的 token 计数值。`available = false` 时值为 `-1` |
| `model_name` | `str` | 是 | 模型名称，由 model-registry 提供 |
| `char_count` | `int` | 是 | 输入文本的 Unicode 字符数（与 `TokenizeResponse.char_count` 一致，冗余字段便于前端逐行展示） |
| `cost_usd` | `float` | 是 | 该模型的单次费用（美元）。`tokens = -1` 时值为 `0.0` |
| `available` | `bool` | 是 | 分词器是否可用。`true` = 使用真实分词器计数；`false` = 分词器不可用（依赖缺失/文件未就绪），回退 `len*0.25` 估算 |

### 4.4 CacheInfo

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `hit_tokens` | `int` | 是 | 缓存命中的 token 数 |
| `total_tokens` | `int` | 是 | 总 token 数（含缓存命中与未命中） |
| `hit_rate` | `float` | 是 | 缓存命中率（0.0 ~ 1.0） |

### 4.5 CompressRequest

| 字段 | 类型 | 必填 | 默认值 | 约束 | 说明 |
|---|---|---|---|---|---|
| `text` | `str` | 是 | — | `min_length=1, max_length=100000` | 待压缩文本 |
| `strategy` | `Literal["rule", "llm"]` | 否 | `"rule"` | — | 压缩策略 |
| `level` | `Literal["light", "medium", "aggressive"]` | 否 | `"medium"` | — | 压缩力度 |
| `target_ratio` | `float \| None` | 否 | `None` | `ge=0.1, le=0.9` | 目标压缩率 |
| `llm_config` | `LLMConfig \| None` | 否 | `None` | — | LLM 配置 |

### 4.6 CompressResponse

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `original_text` | `str` | 是 | 压缩前原始文本 |
| `compressed_text` | `str` | 是 | 压缩后结果文本 |
| `strategy` | `str` | 是 | 实际使用的策略 |
| `changes` | `list[CompressionChange]` | 是 | 压缩变更明细 |
| `stats` | `CompressionStats` | 是 | 压缩统计信息 |

### 4.7 CompressionChange

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `original` | `str` | 是 | 被替换的原始文本片段 |
| `replacement` | `str` | 是 | 替换后的文本片段 |
| `start_pos` | `int` | 是 | 在原始文本中的起始字符位置 |
| `end_pos` | `int` | 是 | 在原始文本中的结束字符位置 |
| `reason` | `str \| None` | 否 | 压缩原因描述（如"移除冗余修饰词"） |

### 4.8 CompressionStats

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `original_chars` | `int` | 是 | 原始字符数 |
| `compressed_chars` | `int` | 是 | 压缩后字符数 |
| `ratio` | `float` | 是 | 压缩比（压缩后/原始） |
| `saved_chars` | `int` | 是 | 节省字符数 |

### 4.9 Message

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `role` | `Literal["user", "assistant"]` | 是 | 消息角色 |
| `content` | `str` | 是 | 消息内容 |

### 4.10 LLMConfig

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `api_key` | `str` | 是 | LLM API 密钥 |
| `model` | `str` | 是 | 模型名称（如 `"gpt-4o"`） |
| `base_url` | `str \| None` | 否 | API 基础 URL，默认为官方端点 |
| `temperature` | `float \| None` | 否 | 生成温度，默认使用引擎默认值 |

### 4.11 SimulateRequest

| 字段 | 类型 | 必填 | 默认值 | 约束 | 说明 |
|---|---|---|---|---|---|
| `monthly_calls` | `int` | 否 | `10000` | `ge=1, le=10000000` | 月调用次数 |
| `avg_input_tokens` | `int` | 否 | `520` | `ge=1` | 平均输入 token |
| `avg_output_tokens` | `int` | 否 | `200` | `ge=0` | 平均输出 token |
| `cache_hit_rate` | `float` | 否 | `0.0` | `ge=0.0, le=1.0` | 缓存命中率 |
| `compression_ratio` | `float` | 否 | `0.0` | `ge=0.0, le=1.0` | 压缩率 |
| `model_ids` | `list[str]` | 是 | — | `min_length=1, max_length=10` | 模型 ID 列表 |

### 4.12 SimulateResponse

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `monthly_calls` | `int` | 是 | 月调用次数（回显） |
| `comparisons` | `list[ModelComparison]` | 是 | 模型费用对比列表 |
| `best_value_model` | `str` | 是 | 性价比最优模型 ID |

### 4.13 ModelComparison

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `model_id` | `str` | 是 | 模型 ID |
| `model_name` | `str` | 是 | 模型显示名称 |
| `monthly_cost_without_compression` | `float` | 是 | 不压缩时月费用（美元） |
| `monthly_cost_with_compression` | `float` | 是 | 压缩后月费用（美元） |
| `monthly_savings` | `float` | 是 | 月节省金额（美元） |
| `savings_percentage` | `float` | 是 | 节省百分比（0.0 ~ 100.0） |

### 4.14 ExportRequest

| 字段 | 类型 | 必填 | 约束 | 说明 |
|---|---|---|---|---|
| `text` | `str` | 是 | `min_length=1, max_length=100000` | 待导出的文本 |

### 4.15 ConfigRequest

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `config` | `dict` | 是 | 配置键值对。value 仅支持 `str \| int \| float \| bool` |

### 4.16 ConfigResponse

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `saved` | `bool` | 是 | 保存成功标记 |
| `config` | `dict` | 是 | 已保存的配置回显 |

### 4.17 ErrorResponse（通用错误格式）

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `error` | `bool` | 是 | 固定为 `true`，用于前端快速判断 |
| `code` | `str` | 是 | 错误码（见 [第 6 章](#6-错误处理规范)） |
| `message` | `str` | 是 | 人类可读的错误描述 |
| `detail` | `dict \| None` | 否 | 可选错误详情，包含具体字段/上下文 |

---

## 5. CORS 配置

### 5.1 允许的来源

允许的来源通过环境变量 `CORS_ORIGINS` 配置，以逗号分隔。不配置时默认回退到开发地址：

| 环境 | 来源 | 配置方式 |
|---|---|---|
| 开发 | `http://localhost:8080, http://localhost:3000` | 默认值（`CORS_ORIGINS` 未设置时自动使用） |
| 开发 | 自定义 | `export CORS_ORIGINS="http://localhost:5173,http://192.168.1.100:8080"` |
| 生产 | 由部署配置决定 | 在部署环境或 docker-compose 中设置 `CORS_ORIGINS` 环境变量 |

### 5.2 允许的 HTTP 方法

`GET`, `POST`, `OPTIONS`

所有端点仅使用 `GET` 和 `POST` 方法；`OPTIONS` 用于 CORS 预检请求。

### 5.3 允许的请求头

- `Content-Type` — 指示请求体编码类型
- `Authorization` — 预留，用于未来 API 鉴权

### 5.4 其他配置

| 配置项 | 值 | 说明 |
|---|---|---|
| `allow_credentials` | `true` | 允许跨域携带凭据（Cookie / Authorization 头） |
| `max_age` | `600` | 预检结果缓存时间（秒） |

---

## 6. 错误处理规范

所有端点错误统一返回 `ErrorResponse` 结构（见 [4.17 ErrorResponse](#417-errorresponse通用错误格式)）。

### 6.1 错误码枚举

| 错误码 | HTTP 状态码 | 说明 | 典型触发场景 |
|---|---|---|---|
| `MODEL_NOT_FOUND` | 400 | 请求的模型 ID 或分组 ID 未在注册表中找到 | `POST /api/tokenize` 传入了不存在的 `group_id`；`POST /api/cost/simulate` 传入了不存在的 `model_id` |
| `MODEL_NOT_AVAILABLE` | 503 | 请求的分组为 Phase 2 预留，尚未实现 | `POST /api/tokenize` 请求了 `claude` 分组但 Phase 1 仅支持开源分词器 |
| `TEXT_TOO_LONG` | 413 | 输入文本超出 100,000 字符上限 | `POST /api/compress` 或 `POST /api/tokenize` 的 `text` 字段超长 |
| `COMPRESSION_FAILED` | 500 | 压缩引擎内部执行错误 | LLM 压缩时 API 调用超时或返回异常；规则引擎处理异常文本 |
| `INTERNAL_ERROR` | 500 | 未预期的服务器内部错误 | Python 运行时异常、模块导入失败、资源耗尽等 |

### 6.2 错误响应示例

```
HTTP/1.1 422 Unprocessable Entity
Content-Type: application/json

{
    "detail": [
        {
            "loc": ["body", "text"],
            "msg": "String should have at least 1 character",
            "type": "string_too_short"
        }
    ]
}
```

Pydantic 校验失败返回 FastAPI 默认 422 格式（非 `ErrorResponse`），前端可根据 `detail` 数组中的 `loc` 和 `msg` 字段定位具体字段错误。

### 6.3 异常处理链

```
FastAPI 端点
    │
    ├─ Pydantic 校验失败 → 422（FastAPI 默认格式）
    │
    ├─ 委派模块抛出已知异常（ModuleNotFoundError、TokenizeError 等）
    │      │
    │      ▼
    │  网关层捕获 → 映射为对应 error_code → 200 + ErrorResponse
    │
    └─ 未捕获异常（Exception）
           │
           ▼
       全局异常处理器 → 500 + ErrorResponse({INTERNAL_ERROR})
```

网关层不抛出 HTTP 异常，而是将所有业务错误封装为 `ErrorResponse` 以 200 状态码返回（应用层错误）或 4xx/5xx（HTTP 层错误）。前端统一检查响应中的 `error` 字段判断是否业务出错。

---

## 7. 中间件设计

### 7.1 请求日志中间件

**用途**：记录每个 HTTP 请求的方法、路径、状态码、客户端 IP、耗时。

**实现位置**：`app.middleware.RequestLoggingMiddleware`

**日志输出格式**（JSON 结构化日志）：

| 字段 | 类型 | 说明 |
|---|---|---|
| `timestamp` | `str` | ISO 8601 格式时间戳 |
| `method` | `str` | HTTP 方法 |
| `path` | `str` | 请求路径（不含 query string） |
| `status` | `int` | HTTP 状态码 |
| `duration_ms` | `int` | 处理耗时（毫秒） |
| `client_ip` | `str` | 客户端 IP 地址 |

**行为**：
- 始终记录，无采样率
- 在响应发回客户端前完成日志写入
- 不记录请求体或响应体内容（保护数据隐私）

### 7.2 耗时统计中间件

**用途**：在响应头中添加 `X-Process-Time` 字段，便于前端调试和性能观测。

**实现位置**：`app.middleware.TimingMiddleware`

**行为**：
- 在请求进入时记录起始时间
- 在响应发出前计算耗时并写入响应头
- 不影响响应体内容

**响应头**：
```
X-Process-Time: 42.5
```

单位为毫秒，精确到 0.1ms。

### 7.3 静态文件缓存中间件

**用途**：为静态资源（JS、CSS、图片）设置 `Cache-Control` 响应头，减少浏览器重复请求。

**实现位置**：`app.middleware.StaticCacheMiddleware`

**行为**：
- 仅对 `.js`、`.css`、`.png`、`.svg`、`.ico` 等静态文件扩展名生效
- `max-age` 值通过环境变量 `STATIC_CACHE_MAX_AGE` 控制（默认 `3600` 秒，即 1 小时）
- API 请求（路径以 `/api/` 开头）不受此中间件影响
- 开发环境下建议设置 `STATIC_CACHE_MAX_AGE=0` 以避免缓存干扰调试

---

## 8. 与其他模块的关系

### 8.1 模块依赖关系图

```
┌──────────────────┐       HTTP
│   frontend-ui    │───────────┐
│  (三面板布局 UI)  │           │
└──────────────────┘           │
                               ▼
                      ┌──────────────────┐
                      │   api-gateway    │
                      │   (FastAPI 网关)  │
                      └───────┬──────────┘
                              │ 委派调用
         ┌────────────────────┼────────────────────┐
         │                    │                    │
         ▼                    ▼                    ▼
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│ model-registry  │  │ tokenizer-layer │  │ compression-engine
│ (模型元数据)     │  │   (分词器层)     │  │  (压缩引擎)      │
└─────────────────┘  └─────────────────┘  └─────────────────┘
         │                                      │
         │                                      │
         ▼                                      ▼
┌─────────────────┐                     ┌─────────────────┐
│ cost-simulator  │                     │  config-store   │
│ (成本模拟器)     │                     │  (配置存储)      │
└─────────────────┘                     └─────────────────┘
```

### 8.2 上游依赖（网关调用方）

| 调用方 | 调用方式 | 说明 |
|---|---|---|
| **frontend-ui** | 浏览器 HTTP fetch | 用户操作触发 API 调用。详见 → 被 [frontend-ui](../frontend-ui/README.md) 运行时调用 |

### 8.3 下游依赖（网关委派目标）

| 被依赖模块 | 委派端点 | 说明 |
|---|---|---|
| **model-registry** | `GET /api/models` | 模型元数据与定价查询。`/api/models` 响应中嵌入各模型的定价数据，不再需要独立的 `/api/pricing` 端点。详见 → 参见 [模型注册表](../model-registry/README.md#4-查询接口) |
| **tokenizer-layer** | `POST /api/tokenize` | 多模型 token 计数。详见 → 参见 [分词器层](../tokenizer-layer/README.md) |
| **compression-engine** | `POST /api/compress` | 语义压缩核心。详见 → 参见 [压缩引擎](../compression-engine/README.md) |
| **cost-simulator** | `POST /api/cost/simulate` | 月度成本模拟。详见 → 参见 [成本模拟器](../cost-simulator/README.md) |
| **config-store** | `GET /api/config`、`POST /api/config` | 配置持久化读写。详见 → 参见 [config-store](../config-store/README.md) |

### 8.4 接口合约

API 网关与各下层模块之间通过 **Python 函数调用**（而非 HTTP）交互。下层模块导出同步/异步函数，网关层直接 import 并调用。每个模块的入口函数签名见各自模块文档中的"查询接口"章节。

---

## 9. OpenAPI 文档

FastAPI 在应用启动时自动生成符合 OpenAPI 3.1 规范的 API 文档。

### 9.1 文档端点

| 端点 | 说明 |
|---|---|
| `/docs` | Swagger UI 交互式文档。可直接在浏览器中测试每个端点的请求与响应 |
| `/redoc` | ReDoc 风格文档。更适用于阅读和导出 |
| `/openapi.json` | 原始 OpenAPI 3.1 Schema 文件。可用于生成客户端 SDK 或集成到 API 管理平台 |

### 9.2 自动生成内容

FastAPI 从以下来源自动生成文档内容：

- **路径与操作**：从路由装饰器（``@app.get``、``@app.post``）推断
- **请求体模型**：从 Pydantic `BaseModel` 派生完整的 JSON Schema，包含字段名、类型、默认值、约束条件、描述
- **响应体模型**：从 `response_model` 参数派生
- **参数校验**：`Query`、`Path`、`Body` 等描述器的约束条件
- **示例值**：Pydantic 字段的 `examples` 参数提供请求体示例

### 9.3 文档定制

| 定制项 | 值 | 说明 |
|---|---|---|
| `title` | `"Prompt 优化工作站 API"` | 文档页标题 |
| `version` | `"2.0.0"` | 与项目版本对齐 |
| `description` | `"Token 计算器 & 语义压缩引擎后端 API"` | 文档页描述 |
| `docs_url` | `"/docs"` | Swagger UI 挂载路径 |
| `redoc_url` | `"/redoc"` | ReDoc 挂载路径 |

---

## 10. 测试策略

API 网关的测试以 **集成测试** 为核心，验证请求路由、参数校验、错误映射和响应格式的正确性。

### 10.1 测试工具

| 工具 | 用途 |
|---|---|
| `pytest` | 测试框架 |
| `httpx.AsyncClient` | 异步 HTTP 客户端，通过 FastAPI 的 `TestClient`（即 Starlette 的 `TestClient`，底层使用 httpx）发送请求 |
| `pytest-asyncio` | 异步测试支持 |

### 10.2 测试范围

**单元测试**（少量）：
- Pydantic 模型字段校验（边界值、默认值、枚举约束）
- 自定义校验器逻辑

**集成测试**（主体）：
- 对每个端点构造合法请求，验证状态码和响应体结构
- 对每个端点构造非法请求（缺字段、超长、枚举越界），验证 422 或 ErrorResponse
- 对委派模块注入 mock，验证网关层正确捕获并转发已知异常
- 验证 CORS 预检请求（OPTIONS）返回正确的响应头
- 验证中间件写入 `X-Process-Time` 响应头
- 验证错误场景返回正确的 `ErrorResponse` 字段结构

### 10.3 测试替身策略

| 场景 | 策略 | 说明 |
|---|---|---|
| 端到端测试 | 使用实际模块（不 mock） | `GET /api/models`、`GET /api/pricing` 等只读查询可直接使用真实 model-registry |
| 异常映射测试 | `unittest.mock` 注入 | 对 compress / tokenize 等复杂端点，mock 下层模块抛出已知异常，验证网关层映射为正确 error_code |
| 外部依赖 | 不涉及 | 网关层自身不调用外部 API，故无需 HTTP mock |

### 10.4 关键测试用例

| # | 测试点 | 端点 | 预期 |
|---|---|---|---|
| 1 | 正常 token 计数 | `POST /api/tokenize` | 200，`results` 长度等于 `group_ids` 个数 |
| 2 | 空文本被拒绝 | `POST /api/tokenize` | 422，`detail` 包含 `string_too_short` |
| 3 | 超长文本被拒绝 | `POST /api/compress` | 413，`error.code == "TEXT_TOO_LONG"` |
| 4 | 不存在 group_id | `POST /api/tokenize` | 200，`error.code == "MODEL_NOT_FOUND"` |
| 5 | 不可用模型 Phase2 | `POST /api/tokenize` | 200（业务错误），`error.code == "MODEL_NOT_AVAILABLE"` |
| 6 | 压缩引擎异常 | `POST /api/compress` | 200（业务错误），`error.code == "COMPRESSION_FAILED"` |
| 7 | CORS 预检通过 | `OPTIONS /api/models` | 204，包含 `Access-Control-Allow-Origin` 头 |
| 8 | 耗时头存在 | 任意端点 | 响应头中包含 `X-Process-Time` |
| 9 | 合法模拟请求 | `POST /api/cost/simulate` | 200，`best_value_model` 为非空字符串 |
| 10 | 配置持久化读写 | `POST → GET /api/config` | 保存后读取返回相同内容 |

### 10.5 测试命令

```bash
# 运行网关层所有测试
pytest tests/test_api_gateway/ -v

# 仅运行集成测试
pytest tests/test_api_gateway/test_integration.py -v

# 含覆盖率报告
pytest tests/test_api_gateway/ --cov=app --cov-report=term
```

---

## 附录 A：FastAPI 应用结构（目录参考）

```
app/
├── main.py                 # FastAPI 应用实例化、CORS 注册、中间件注册、路由挂载
├── api/
│   ├── __init__.py
│   ├── models.py           # GET /api/models, GET /api/pricing
│   ├── tokenize.py         # POST /api/tokenize
│   ├── compress.py         # POST /api/compress
│   ├── simulate.py         # POST /api/cost/simulate
│   ├── export.py           # POST /api/export
│   └── config.py           # GET/POST /api/config
├── schemas/
│   ├── __init__.py
│   ├── tokenize.py         # TokenizeRequest, TokenizeResponse, TokenizeResult, CacheInfo
│   ├── compress.py         # CompressRequest, CompressResponse, CompressionChange, CompressionStats, Message, LLMConfig
│   ├── simulate.py         # SimulateRequest, SimulateResponse, ModelComparison
│   ├── export.py           # ExportRequest
│   ├── config.py           # ConfigRequest, ConfigResponse
│   └── errors.py           # ErrorResponse, error code enum
├── middleware/
│   ├── __init__.py
│   └── logging.py          # RequestLoggingMiddleware, TimingMiddleware
└── tests/
    └── test_api_gateway/
        ├── __init__.py
        ├── test_models.py
        ├── test_tokenize.py
        ├── test_compress.py
        ├── test_simulate.py
        ├── test_export.py
        ├── test_config.py
        ├── test_cors.py
        ├── test_middleware.py
        └── conftest.py       # Fixtures: test client, mock modules
```
