# Prompt 优化工作站 — 架构总览

> **版本**: v2.0  
> **日期**: 2026-07-06  
> **定位**: 本文档是模块文档体系的入口页。阅读后你应理解整个系统的模块划分、数据流向、核心流程和开发约定。

---

## 目录

1. [项目概述](#1-项目概述)
2. [架构全景图](#2-架构全景图)
3. [模块速览表](#3-模块速览表)
4. [核心业务流程](#4-核心业务流程)
5. [Phase 1 vs Phase 2](#5-phase-1-vs-phase-2)
6. [模块间接口契约](#6-模块间接口契约)
7. [技术栈汇总](#7-技术栈汇总)
8. [文档索引](#8-文档索引)
9. [开发约定](#9-开发约定)

---

## 1. 项目概述

### 1.1 一句话描述

> **本地 Web 工具，三面板布局。用户粘贴 Prompt → 语义压缩 → 查看各模型省了多少 Token + 省了多少钱。**

### 1.2 核心流程

```
原始 Prompt
    │
    ▼
┌──────────────────────────────────────────────────────────────┐
│                   语义压缩引擎 (Compression Engine)            │
│                                                              │
│  规则引擎 (本地/毫秒级)   LLM 智能压缩 (需 API Key)           │
└──────────────────────────┬───────────────────────────────────┘
                           │ 压缩后文本
                           ▼
┌──────────────────────────────────────────────────────────────┐
│                   分词器层 (Tokenizer Layer)                   │
│                                                              │
│  分别计量压缩前 / 压缩后 Token 数                             │
│  支持多模型同时对比 (GPT-4o / DeepSeek / Qwen ...)            │
└──────────────────────────┬───────────────────────────────────┘
                           │ Token 对比数据
                           ▼
┌──────────────────────────────────────────────────────────────┐
│                   成本模拟器 (Cost Simulator)                  │
│                                                              │
│  Token × 模型单价 → 压缩前后费用对比                          │
│  月调用量投影 → 年度节省                                     │
└──────────────────────────┬───────────────────────────────────┘
                           │ 省了多少 Token + 省了多少钱
                           ▼
"原 520 Token → 压缩后 180 Token，节省 65%，每月省 $42"
```

---

## 2. 架构全景图

系统由 7 个模块组成。以下为模块依赖关系：

```
                                    ┌──────────────────────┐
                                    │    model-registry    │
                                    │    模型元数据/价格    │
                                    │    (数据黄页)         │
                                    └──────────┬───────────┘
                                               │ 只读依赖
                   ┌──────────────────────────┼──────────────┐
                   │                          │              │
                   ▼                          ▼              ▼
        ┌────────────────────┐    ┌────────────────────┐
        │  tokenizer-layer   │    │  cost-simulator    │
        │  分词计量层         │    │  费用模拟/成本投影   │
        │  (8 个分组)         │    │  (3 种数据载体)     │
        └────────┬───────────┘    └────────┬───────────┘
                 │                         │
                 │   依赖注册表获取 library   │   依赖注册表获取 pricing
                 └─────────────┬───────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │  compression-engine │
                    │  语义压缩引擎        │
                    │  (2 策略 + 3 强度)   │
                    └──────────┬──────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │    api-gateway      │
                    │  FastAPI HTTP 入口   │
                    │  (6 个端点)          │
                    └──────────┬──────────┘
                               │ HTTP
                               ▼
                    ┌─────────────────────┐
                    │    frontend-ui      │
                    │  三面板暗色仪表盘     │
                    │  (4 功能区)          │
                    └─────────────────────┘

                    ┌─────────────────────┐
                    │    config-store     │
                    │  用户偏好 + 历史记录  │
                    │  后端 JSON文件 + 前端 sessionStorage/localStorage 双层缓存 │
                    └─────────────────────┘
```

**依赖规则**: `model-registry` 是只读数据源，被 `tokenizer-layer`、`cost-simulator`、`api-gateway` 读取。所有前端请求经过 `api-gateway` 路由到后端各模块。`config-store` 独立运行于前端 localStorage，不依赖其他模块。

---

## 3. 模块速览表

| 模块 | 位置 | 一句话定位 | 关键接口 | 实现状态 | 文档 |
|------|------|-----------|---------|---------|------|
| **model-registry** | `src/token_calculator/_pricing.py` | 模型元数据 + 价格数据库 | `PricingRegistry.get()`, `list_groups()` | 已完成 | → 参见 [model-registry](./model-registry/README.md) |
| **tokenizer-layer** | `src/token_calculator/_tokenizer_*.py` | 4 个开源分词器 + 注册表工厂 | `count_tokens_batch()`, `get_tokenizer()` | 已完成（Gemma 暂缓，详见 [IMPLEMENTATION-PLAN.md](./tokenizer-layer/IMPLEMENTATION-PLAN.md)） | → 参见 [tokenizer-layer](./tokenizer-layer/README.md) |
| **cost-simulator** | `src/token_calculator/_cost_simulator.py` | 费用计算 + 月度成本模拟 | `simulate_monthly()`, `compare_models()` | 已完成 | → 参见 [cost-simulator](./cost-simulator/README.md) |
| **compression-engine** | `src/token_calculator/_compressor_base.py` | 语义压缩引擎（2 策略 + 3 强度） | `compress()`, `get_compressor()` | 已完成 | → 参见 [compression-engine](./compression-engine/README.md) |
| **api-gateway** | `src/token_calculator/_app.py` | FastAPI HTTP 入口 + 路由 | `create_app()` 工厂函数 | 已完成 | → 参见 [api-gateway](./api-gateway/README.md) |
| **frontend-ui** | `frontend/` | 三面板暗色仪表盘 | `fetch()` → 6 个 API | 已完成 | → 参见 [frontend-ui](./frontend-ui/README.md) |

---

## 4. 核心业务流程

### 4.1 压缩流程

用户从输入 Prompt 到看到压缩结果和节省金额的完整链路：

```
用户粘贴 Prompt 到面板 1
    │
    ▼
前端实时显示字符数 + 选中模型的预估 Token（轻量前端估算）
    │
    ▼
用户在面板 2 选择压缩策略：
  ├─ 规则引擎 (本地，毫秒级，无需 API)
  │   └─ 强度选择：轻度 / 中度 / 重度
  └─ LLM 智能压缩 (需要 API Key)
      └─ 配置：目标压缩率 + 压缩模型 + API Key
    │
    ▼
用户点击 [一键压缩]
    │
    ▼
POST /api/compress ──→ compression-engine 执行压缩
    │                          │
    │                          ├─ rule: 本地正则匹配替换
    │                          └─ llm: 调用 LLM API 改写
    │                          │
    │                          ▼
    │                   返回压缩后文本 + 变更记录
    │
    ▼
POST /api/tokenize (同时发送原始文本和压缩后文本)
    │                     │
    │                     ├─ tokenizer-layer 分别计数
    │                     │  (对每个选中的模型分组)
    │                     └─ model-registry 提供 library 映射
    │                     │
    │                     ▼
    │              返回 TokenizeResult[]
    │
    ▼
POST /api/cost-simulate (传入前后 Token + 月调用量)
    │                     │
    │                     ├─ cost-simulator 读取 pricing
    │                     └─ 计算前后费用差异
    │                     │
    │                     ▼
    │              返回 SimulationReport
    │
    ▼
前端面板 3 渲染：
  ├─ 核心对比卡片 (原 Token → 压缩后 Token，节省百分比)
  ├─ 多模型对比表 (逐行展示每个模型的 Token + 费用)
  ├─ 成本模拟器 (月调用量滑块 → 柱状图)
  └─ 压缩率排行榜 (按 Prompt 类型的历史统计)
```

### 4.2 成本模拟流程

用户调整参数时，系统进行假设分析（What-if）：

```
用户在面板 3 展开 "成本模拟器"
    │
    ▼
设定参数：
  ├─ 月均 API 调用量: [输入框 / 滑块]
  ├─ 平均输入 Token:  从当前压缩结果自动带入
  ├─ 平均输出 Token:  [输入框]
  ├─ 缓存命中率:      [滑块 0-100%]
  └─ 对比模型:        [多选，默认当前选中的全部模型]
    │
    ▼
判断是否需要向后端请求？
  ├─ 仅调整调用量/压缩率/缓存率 → 前端已有价格缓存 → 本地重算
  ├─ 切换/新增模型 → 前端有缓存? → 是→本地重算 / 否→GET /api/pricing
  └─ 首次加载 → POST /api/cost-simulate 完整请求
    │
    ▼
计算逻辑（后端或本地）：
  对每个选中的模型：
    1. 从 model-registry 读取 input_price / output_price / cache_hit_price
    2. 压缩前月费用 = (原始输入 Token × input_price + 输出 Token × output_price) × 月调用量 / 1M
    3. 压缩后月费用 = (压缩后输入 Token × input_price + 输出 Token × output_price) × 月调用量 / 1M
    4. 月节省 = 压缩前 - 压缩后
    5. 年节省 = 月节省 × 12
    │
    ▼
返回 SimulationReport：
  ├─ comparisons[]: 每个模型的 before/after 费用
  ├─ best_value_model: 压缩后总费用最低的模型
  └─ 按 after.total 升序排列
    │
    ▼
前端渲染：
  ├─ 月度对比卡片 (每个模型一行：压缩前 → 压缩后 → 节省)
  ├─ 横向柱状图 (压缩前 vs 压缩后)
  ├─ 年度节省标语 (如 "年省 $608.40")
  └─ ⭐ 最优模型徽章
```

---

## 5. 实现状态与后续计划

### 5.1 当前实现范围

| 维度 | 当前状态 |
|------|---------|
| **分词器覆盖** | 8 个开源分词器分组（tiktoken ×2，transformers ×4，sentencepiece ×1，mistral-common ×1）— Gemma（sentencepiece）暂缓，详见 [tokenizer-layer 实施计划](./tokenizer-layer/IMPLEMENTATION-PLAN.md) |
| **压缩策略** | 规则引擎（3 级强度）+ LLM 智能压缩 |
| **价格数据** | 静态内联字典，手动维护 |
| **前端功能** | 三面板布局 + 对比表 + 成本模拟器 + 导出/撤销 + 原文 vs 压缩后文本对比 |
| **扩展能力** | 纯文本 Token 计量 |
| **配置存储** | 后端 JSON 文件 + 前端 sessionStorage/localStorage 双层缓存 |

### 5.2 后续计划（已延期，暂无时间表）

- 自动抓取各平台官网定价 + 版本化历史
- 压缩历史收藏夹 + 批量 CSV 导入
- 图片 Token 估算 + 工具调用 Token 估算
- 压缩前后 Diff 高亮
- Chrome 插件版

---

## 6. 模块间接口契约

以下四种数据结构跨越模块边界，是模块间通信的核心约定。

### 6.1 ModelGroup — 模型分组元数据

| 字段 | 类型 | 必填 | 定义方 | 消费方 | 说明 |
|------|------|------|--------|--------|------|
| `group_id` | `str` | 是 | model-registry | tokenizer-layer, api-gateway, frontend-ui | 唯一标识，也是分词器查找键 |
| `type` | `"open"` | 是 | model-registry | frontend-ui | 全部分组均为开源实现 |
| `library` | `str` | 是 | model-registry | tokenizer-layer | 分词库名，决定实例化哪个 Tokenizer 子类 |
| `models` | `list[str]` | 是 | model-registry | cost-simulator, frontend-ui | 模型名称列表 |
| `pricing` | `dict` | 是 | model-registry | cost-simulator, frontend-ui | 价格字典，key 为模型名 |
| `available` | `bool` | 是 | model-registry | api-gateway, frontend-ui | Phase 1 可用标记 |

→ 完整定义参见 [model-registry 数据结构](./model-registry/README.md#2-数据结构定义)

### 6.2 TokenizeResult — Token 计数结果

| 字段 | 类型 | 必填 | 来源 | 去向 | 说明 |
|------|------|------|------|------|------|
| `group_id` | `str` | 是 | tokenizer-layer | api-gateway → frontend-ui | 分组标识 |
| `model_name` | `str` | 是 | tokenizer-layer | api-gateway → frontend-ui | 模型名称（仅前端展示用） |
| `tokens` | `int` | 是 | tokenizer-layer | api-gateway → frontend-ui | 精确 Token 数 |
| `cost_usd` | `float` | 是 | tokenizer-layer | api-gateway → frontend-ui | 该模型的单次费用 |

**跨模块传递路径**: `tokenizer-layer` → (被 `api-gateway` 调用) → 封装到 HTTP 响应 → `frontend-ui`

### 6.3 CompressionResult — 压缩结果

| 字段 | 类型 | 必填 | 来源 | 去向 | 说明 |
|------|------|------|------|------|------|
| `strategy` | `str` | 是 | compression-engine | api-gateway → frontend-ui | 使用的压缩策略 (`rule` / `llm`) |
| `original_text` | `str` | 是 | compression-engine | api-gateway → frontend-ui | 原始文本 |
| `compressed_text` | `str` | 是 | compression-engine | api-gateway → frontend-ui | 压缩后文本 |
| `original_tokens` | `dict[str, int]` | 是 | （由 api-gateway 调用 tokenizer-layer 后填充） | frontend-ui | Key 为 group_id，Value 为原始 Token 数 |
| `compressed_tokens` | `dict[str, int]` | 是 | （同上） | frontend-ui | Key 为 group_id，Value 为压缩后 Token 数 |
| `savings` | `dict` | 是 | （由 api-gateway 聚合） | frontend-ui | 含 `tokens_saved`, `percentage`, `estimated_monthly_savings_usd` |
| `changes` | `list[dict]` | 否 | compression-engine | frontend-ui | 变更记录（仅规则引擎提供逐条变更） |

**跨模块传递路径**: `compression-engine` → `api-gateway`（聚合 token 数据后） → `frontend-ui`

### 6.4 SimulationReport — 月度模拟报告

| 字段 | 类型 | 必填 | 来源 | 去向 | 说明 |
|------|------|------|------|------|------|
| `monthly_calls` | `int` | 是 | cost-simulator（来自请求参数） | api-gateway → frontend-ui | 月调用量 |
| `comparisons` | `list[ModelComparison]` | 是 | cost-simulator | api-gateway → frontend-ui | 每个模型的对比数据 |
| `best_value_model` | `str` | 是 | cost-simulator | api-gateway → frontend-ui | 压缩后总费用最低的模型 ID |

其中 `ModelComparison` 包含:

| 子字段 | 类型 | 说明 |
|--------|------|------|
| `model_id` | `str` | 模型标识 |
| `before` | `{input_cost, output_cost, total}` | 压缩前月费用 |
| `after` | `{input_cost, output_cost, total}` | 压缩后月费用 |
| `monthly_savings` | `float` | 月节省金额 |
| `yearly_savings` | `float` | 年节省金额 (= monthly × 12) |
| `savings_percentage` | `float` | 节省百分比 |

→ 完整定义参见 [cost-simulator 数据结构](./cost-simulator/README.md#2-核心数据结构)

### 6.5 接口依赖矩阵

| 消费者 \ 提供者 | model-registry | cost-simulator |
|----------------|---------------|---------------|
| **api-gateway** | 读取全字段用于 API 响应 | 调用 `simulate_monthly()` |
| **cost-simulator** | 读取 `pricing` 字段 | — |
| **frontend-ui** | 通过 `GET /api/models` 间接读取 | 通过 `POST /api/cost-simulate` 间接调用 |
| **config-store** | — | — |

---

## 7. 技术栈汇总

### 7.1 后端（Python 3.11+）

| 包 | 用途 | 版本约束 |
|---|------|---------|
| **FastAPI** | Web 框架，路由 + 请求校验 | ≥ 0.110 |
| **uvicorn** | ASGI 服务器 | ≥ 0.29 |
| **pydantic** | 请求/响应数据模型校验 | ≥ 2.0 |
| **httpx** | LLM 压缩器对外部 API 的 HTTP 请求 | ≥ 0.28 |
| **tiktoken** | OpenAI 系列分词器（o200k_base / cl100k_base） | ≥ 0.7 |
| **transformers** | HuggingFace 分词器（Llama / Qwen / DeepSeek / GLM） | ≥ 4.40 |
| **sentencepiece** | SentencePiece 分词器（Gemma 3） | ≥ 0.2 |
| **mistral-common** | Mistral Tekken 分词器 | ≥ 1.3 |
| **huggingface-hub** | HuggingFace 模型仓库下载（`hf_hub_download`） | ≥ 0.24 |
| （无额外依赖） | CORS 配置、静态文件服务 | FastAPI 内置 |

**Python 标准库使用**: `re`（规则引擎正则）、`json`（序列化）、`dataclasses`（数据结构）、`abc`（抽象基类）

### 7.2 前端（纯三件套，无框架依赖）

| 技术 | 用途 |
|------|------|
| **HTML5** | 三面板布局语义结构 |
| **CSS3** | 暗色仪表盘主题（CSS 自定义属性变量体系 + Flexbox/Grid 布局） |
| **Vanilla JS (ES6+)** | 全部交互逻辑（`fetch()` API 调用、DOM 操作、事件处理、本地缓存） |

**前端响应式断点**: `> 1200px`（三列） / `768-1200px`（两列） / `< 768px`（单列堆叠）

### 7.3 数据层

| 存储 | 用途 | 方式 |
|------|------|------|
| Python 内存字典 | 模型注册表 + 价格数据库 | `_pricing.py` 内联定义 |
| 后端 JSON 文件 + 前端 sessionStorage/localStorage 双层缓存 | 用户偏好 + 压缩历史 | `config-store` 模块管理 |

---

## 8. 文档索引

### 8.1 顶层设计文档

| 文档 | 路径 | 内容 |
|------|------|------|
| **项目设计文档 v2.0** | `../design-document.md` | 产品定位、核心架构、完整 API 设计、前端交互设计、实现步骤、验证方案 |

### 8.2 模块文档（8 个）

| # | 模块 | 文档路径 | 状态 |
|---|------|---------|------|
| 1 | **model-registry** 模型注册表 | [./model-registry/README.md](./model-registry/README.md) | 已完成 |
| 2 | **tokenizer-layer** 分词器层 | [./tokenizer-layer/README.md](./tokenizer-layer/README.md) | 已完成 |
| 3 | **compression-engine** 压缩引擎 | [./compression-engine/README.md](./compression-engine/README.md) | 已完成 |
| 4 | **cost-simulator** 费用模拟 | [./cost-simulator/README.md](./cost-simulator/README.md) | 已完成 |
| 5 | **api-gateway** API 网关 | [./api-gateway/README.md](./api-gateway/README.md) | 已完成 |
| 6 | **frontend-ui** 前端界面 | [./frontend-ui/README.md](./frontend-ui/README.md) | 已完成 |
| 7 | **tokenizer-layer 实施计划** | [./tokenizer-layer/IMPLEMENTATION-PLAN.md](./tokenizer-layer/IMPLEMENTATION-PLAN.md) | 已完成 |

### 8.3 阅读顺序建议

| 读者角色 | 推荐阅读顺序 |
|---------|-------------|
| **新开发者入项** | 本文档 → 项目设计文档 → frontend-ui → api-gateway → model-registry → cost-simulator |
| **功能开发** | 目标模块文档 → 相关模块的接口契约章节 |
| **添加新模型** | model-registry 扩展指南 |
| **Bug 排查** | api-gateway 路由 → 目标后端模块文档 → 接口契约 |

---

## 9. 开发约定

### 9.1 命名规范

| 层 | 规范 | 示例 |
|----|------|------|
| Python 代码 | `snake_case` | `rule_compressor.py`, `count_tokens()`, `compression_ratio` |
| CSS 类名 | `kebab-case` | `panel-original`, `btn-primary`, `savings-card` |
| CSS 变量 | `--kebab-case` | `--bg-panel`, `--text-primary`, `--accent` |
| JavaScript | `camelCase` | `handleCompress()`, `monthlyCalls`, `modelSelector` |
| API 路径 | 小写 + 连字符 | `/api/cost-simulate`, `/api/model-groups` |
| 模型分组 ID | 小写 + 下划线 | `o200k_base`, `mistral`, `deepseek_v4` |
| 配置文件 | `snake_case` | `default_settings.json` |

### 9.2 API 版本策略

- **当前**: 路径前缀 `/api/`，无显式版本号（v1 隐式）
- **未来**: 需要 breaking change 时升级为 `/api/v2/`，同时保留 `/api/v1/` 并存至少一个发布周期
- **兼容性**: 新增字段不视为 breaking change；删除字段、修改字段类型、重命名 endpoint 视为 breaking change
- **弃用通知**: 在响应头中添加 `X-API-Deprecated: v1` + `Sunset: date`，并在 API 文档中标注

### 9.3 模块边界规则

- **所有 HTTP 请求必须经过 api-gateway**，不允许前端直接调用后端模块内部函数
- **model-registry 是只读数据源**，其他模块不得直接修改注册表数据
- **cost-simulator 不执行分词**，依赖调用方提供 Token 数据
- **config-store 纯前端运行**，不涉及后端存储

### 9.4 错误响应格式

所有 API 端点统一错误格式：

```json
{
  "error": {
    "code": "STRING_CODE",
    "message": "人类可读的描述",
    "details": {}
  }
}
```

| 错误码 | HTTP 状态码 | 说明 |
|--------|------------|------|
| `UNKNOWN_MODEL` | 400 | 请求中指定了不存在的模型 ID |
| `UNSUPPORTED_STRATEGY` | 400 | 压缩策略不存在 |
| `MISSING_API_KEY` | 400 | LLM 压缩策略未提供 API Key |
| `RATE_LIMITED` | 429 | 请求频率超限 |
| `INTERNAL_ERROR` | 500 | 内部错误 |

### 9.5 Git 提交约定

| 前缀 | 用途 |
|------|------|
| `feat:` | 新功能 |
| `fix:` | Bug 修复 |
| `docs:` | 文档变更 |
| `refactor:` | 重构 |
| `perf:` | 性能优化 |
| `chore:` | 构建/工具链 |

示例: `feat(compressor): 添加日语规则引擎支持`

---

> **本文档维护**: 本文档是模块文档体系的入口。当新增/删除/合并模块时，请同步更新第 3 节模块速览表、第 6 节接口契约和第 8 节文档索引。所有跨模块引用的模块路径以本文档为准。
