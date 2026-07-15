# Token 计算器 & 语义压缩引擎 — 项目设计文档 v2.0

> **版本**: v2.0  
> **日期**: 2026-07-06  
> **定位**: 语义压缩 + Token 计量 + 成本模拟，三位一体的 Prompt 优化工作站

> **Revision 2026-07-07**: Model groups reduced 15 to 8 (active only). Context compression cancelled. Project restructured to src/token_calculator/ package layout. CSS variables use no namespace prefix. Frontend fetches model data from GET /api/models with local fallback. 5-step incremental migration.

---

## 目录

1. [产品定位](#1-产品定位)
2. [核心架构](#2-核心架构)
3. [语义压缩引擎](#3-语义压缩引擎)
4. [分词器 & 模型注册表](#4-分词器--模型注册表)
5. [价格系统 & 成本模拟器](#5-价格系统--成本模拟器)
6. [项目结构](#6-项目结构)
7. [后端 API 设计](#7-后端-api-设计)
8. [前端设计](#8-前端设计)
9. [实现步骤](#9-实现步骤)
10. [验证方案](#10-验证方案)

---

## 1. 产品定位

### 1.1 一句话描述

> **粘贴 Prompt → 一键压缩 → 看到省了多少 Token、省了多少钱、在多个模型上分别省多少。**

### 1.2 核心流程

```
原始 Prompt
    │
    ▼
┌──────────────┐
│ 语义压缩引擎  │  ← 规则引擎 / LLM 压缩
│   (核心)     │
└──────────────┘
    │
    ▼
压缩后 Prompt
    │
    ▼
┌──────────────┐
│  分词器       │  ← 计量：原 520 token → 压缩后 180 token
│  (计量)      │
└──────────────┘
    │
    ▼
"原 520 token → 压缩后 180 token，节省 65%，每月省 $42"
```

### 1.3 功能矩阵

| 功能 | 说明 |
|---|---|
| **语义压缩** | 规则引擎 + LLM 智能压缩 |
| **Token 计量** | 8 个分词器分组（仅当前活跃模型） |
| **多模型对比** | 同一段文本，并排对比各模型的 token 消耗 |
| **成本预估** | Token × 实时模型单价 = 费用预估 |
| **成本模拟器** | 输入月均调用量 → 压缩前后费用对比柱状图 |
| **一站式导出** | 一键复制压缩后 Prompt |
| **压缩文本展示** | 原文 vs 压缩后文本并排对比，高亮差异 |
| **压缩率统计** | 按 prompt 类型统计压缩率排行榜 |

> **注意**: 上下文压缩策略已取消。现代 LLM (GPT-4, Claude 4, Gemini 2.5 等) 均内置上下文压缩能力，无需外部工具介入。

---

## 2. 核心架构

```
┌─────────────────────────────────────────────────────────┐
│                     Frontend (三面板布局)                 │
│                                                         │
│  ┌──────────────┬──────────────┬──────────────────────┐  │
│  │ 面板1:原始输入│ 面板2:压缩策略│ 面板3:对比结果        │  │
│  │              │              │                      │  │
│  │ textarea     │ 策略选择     │ 原始: 520 token      │  │
│  │ 粘贴prompt   │ [规则压缩]  │ 压缩后: 180 token    │  │
│  │ 多轮对话     │ [LLM 压缩]  │ ↓65% 节省 $42/月    │  │
│  │ 字符/估算    │              │ 多模型对比表          │  │
│  │ token 预览   │ [一键压缩]   │ GPT-4o  Claude  ...  │  │
│  │              │              │ 成本模拟器            │  │
│  └──────────────┴──────────────┴──────────────────────┘  │
│                                                         │
│  fetch() → localhost:8000/api/*                         │
└────────────────────────┬────────────────────────────────┘
                         │ HTTP
┌────────────────────────▼────────────────────────────────┐
│                   Backend (FastAPI)                      │
│                                                         │
│  app.py              → API 路由层                        │
│                                                         │
│  compressor/          → 语义压缩引擎                     │
│  ├── rule_compressor.py    (规则引擎)                   │
│  ├── llm_compressor.py     (LLM 压缩，需 API key)       │
│                                                         │
│  tokenizers/          → 分词器层                         │
│  ├── tiktoken_tokenizer.py                               │
│  ├── hf_tokenizer.py                                     │
│  ├── sentencepiece_tokenizer.py                          │
│  └── registry.py                                         │
│                                                         │
│  pricing.py           → 模型价格数据库                   │
│  cost_simulator.py    → 月度成本投影                     │
└─────────────────────────────────────────────────────────┘
```

---

## 3. 语义压缩引擎

### 3.1 架构

```
                    ┌─────────────────────┐
  原始 Prompt ─────▶│  CompressorBase     │─────▶ 压缩后 Prompt
                    │  (抽象基类)          │
                    └─────────────────────┘
                              │
          ┌───────────────────┼───────────────────┐
          ▼                   ▼
┌─────────────────┐ ┌─────────────────┐
│ RuleCompressor  │ │ LLMCompressor   │
│                 │ │                 │
│ 纯本地/无API    │ │ 调用LLM API     │
│ 规则匹配+替换   │ │ 智能改写压缩    │
│ 即时 (毫秒级)   │ │ 需要API key     │
└─────────────────┘ └─────────────────┘
```

### 3.2 策略 1：规则引擎压缩 (RuleCompressor)

**定位**: 本地运行，毫秒级响应，无需 API。适合快速清理冗余。

#### 压缩规则集

**中文规则:**

| 规则 | 模式 | 替换 | 示例 |
|---|---|---|---|
| 冗余敬语 | `请帮我(.*?)一下` | `$1` | "请帮我看一下这个" → "看这个" |
| 礼貌前缀 | `能否(请您)?` | (删除) | "能否请您帮我" → "帮我" |
| 冗余修饰 | `(非常\|十分\|特别\|极其)` | (删除) | "非常重要" → "重要" |
| 口语填充 | `(那个\|就是说\|然后呢\|对吧)` | (删除) | 口语填充词移除 |
| 重复标点 | `[。！？,!?]{2,}` | 单个 | "好的！！" → "好的！" |
| 多余空白 | `\n{3,}` | `\n\n` | 多处空行合并 |
| 合并指令 | 多个`\n-`开头的简短项 | 合并为一句 | 见示例 |

**英文规则:**

| 规则 | 模式 | 替换 | 示例 |
|---|---|---|---|
| 礼貌请求 | `(C|c)ould you (please )?` | (删除) | "Could you please help" → "Help" |
| 冗余前缀 | `I (would like you to\|want you to)` | (删除) | "I want you to analyze" → "Analyze" |
| 填充短语 | `(basically\|essentially\|actually\|really)` | (删除) | 弱化词移除 |
| 冗余问句 | `Can you tell me (.*?)\?` | `$1` | "Can you tell me the price?" → "Price?" |
| 定冠词省略 | `\bthe\b` (在非必要位置) | (删除) | 列表项中去 the |
| 多个空格 | `\s{2,}` | ` ` | 空白标准化 |

**通用规则:**

| 规则 | 说明 |
|---|---|
| 多余空白清理 | 合并连续空行、行首尾去空白 |
| 重复句检测 | 相似度 > 80% 的相邻句，保留一句 |
| Markdown 优化 | 列表项去多余修饰词、保持结构 |
| 代码块保护 | ` ``` ` 内的内容不压缩 |
| 示例收束 | "例如 / 比如 / for example" 后的多个示例收束为 1-2 个代表性示例 |

#### 压缩强度级别

```
Level 1 (轻度): 仅去冗余空白 + 合并重复标点
Level 2 (中度): Level 1 + 去口语填充 + 去冗余修饰词
Level 3 (重度): Level 2 + 去敬语/礼貌前缀 + 示例收束 + 合并指令
```

### 3.3 策略 2：LLM 智能压缩 (LLMCompressor)

**定位**: 调用 LLM API 进行语义级压缩，质量最高但需要 API key。

#### 压缩 Prompt 模板

```
You are a prompt compression engine. Your task is to rewrite the following 
prompt to be maximally concise while preserving ALL key instructions, 
constraints, examples, and required output format.

Rules:
1. Remove all politeness, filler phrases, and redundant explanations
2. Keep all technical requirements, constraints, and format specifications
3. Preserve all examples but condense them
4. If the original contains multi-step instructions, use numbered lists
5. Do NOT change the core meaning or remove any required output fields
6. Output ONLY the compressed prompt, no explanation

Compression target: achieve at least 40% token reduction.

Original prompt:
---
{user_prompt}
---

Compressed prompt:
```

#### 压缩策略参数

| 参数 | 默认值 | 说明 |
|---|---|---|
| `target_ratio` | 0.4 | 目标压缩率（40% token 减少） |
| `preserve_tone` | false | 是否保留原始语气 |
| `aggressive` | false | 激进模式（合并示例、删减次要指令） |
| `temperature` | 0.1 | LLM 温度（低=更保守/忠实） |

~~### 3.4 策略 3：多轮对话上下文压缩 (ContextCompressor)~~

**~~已取消~~** — 现代 LLM (GPT-4, Claude 4, Gemini 2.5 等) 均内置上下文压缩能力，无需外部工具介入。

---

## 4. 分词器 & 模型注册表

### 4.0 分词器覆盖范围

当前实现 8 个开源分词器分组（仅当前活跃模型）。所有分词器均为开源实现，无闭源估测依赖。

### 4.1 模型分组（按分词器）

| 分组 ID | 分词器 | Python 库 | 模型列表 |
|---|---|---|---|
| `o200k_base` | tiktoken o200k_base | `tiktoken` | GPT-4o, GPT-4o-mini, GPT-4.1, GPT-4.5 |
| `cl100k_base` | tiktoken cl100k_base | `tiktoken` | GPT-4, GPT-4-turbo, GPT-3.5-turbo, text-embedding-3 |
| `llama3` | Llama 3/4 Tokenizer | `transformers` | Llama 3, Llama 3.1, Llama 3.2, Llama 4 |
| `qwen` | Qwen 2.5/3 Tokenizer | `transformers` | Qwen 2.5, Qwen 3 |
| `deepseek_v4` | DeepSeek V3/R1 Tokenizer | `transformers` | DeepSeek V3, DeepSeek R1, DeepSeek Coder V2 |
| `mistral` | Tekken (tiktoken-based) | `mistral-common` | Mistral Large, Mistral Small 3.1 |
| `gemma` | Gemma 3 SentencePiece | `sentencepiece` | Gemma 3 |
| `glm` | ChatGLM Tokenizer | `transformers` | ChatGLM-4, GLM-4-Plus |

---

## 5. 价格系统 & 成本模拟器

> **注意**：价格数据覆盖所有模型，供成本模拟器和多模型对比使用。所有模型的 token 计数均已实现。

### 5.1 模型价格数据

```python
# 价格单位: $/1M token
PRICING = {
    "GPT-4o":           {"input": 2.50,  "output": 10.00, "cache_hit": 1.25},
    "GPT-4o-mini":      {"input": 0.15,  "output": 0.60,  "cache_hit": 0.075},
    "GPT-4.1":          {"input": 2.00,  "output": 8.00,  "cache_hit": 1.00},
    "GPT-4.1-mini":     {"input": 0.40,  "output": 1.60,  "cache_hit": 0.20},
    "GPT-4.1-nano":     {"input": 0.10,  "output": 0.40,  "cache_hit": 0.05},
    "GPT-4":            {"input": 30.00, "output": 60.00, "cache_hit": None},
    "GPT-4-turbo":      {"input": 10.00, "output": 30.00, "cache_hit": None},
    "GPT-3.5-turbo":    {"input": 0.50,  "output": 1.50,  "cache_hit": None},
    "Claude Opus 4":    {"input": 15.00, "output": 75.00, "cache_hit": 1.50},
    "Claude Sonnet 4":  {"input": 3.00,  "output": 15.00, "cache_hit": 0.30},
    "Claude Haiku 3.5": {"input": 0.80,  "output": 4.00,  "cache_hit": 0.08},
    "Gemini 2.5 Pro":   {"input": 1.25,  "output": 10.00, "cache_hit": 0.3125},
    "Gemini 2.5 Flash": {"input": 0.15,  "output": 0.60,  "cache_hit": 0.0375},
    "DeepSeek V3":      {"input": 0.27,  "output": 1.10,  "cache_hit": 0.07},
    "DeepSeek R1":      {"input": 0.55,  "output": 2.19,  "cache_hit": 0.14},
    "Llama 4 Maverick": {"input": 0.35,  "output": 0.90,  "cache_hit": 0.09},
    "Qwen 3-235B":      {"input": 0.35,  "output": 1.20,  "cache_hit": None},
    "Qwen 3-30B":       {"input": 0.10,  "output": 0.35,  "cache_hit": None},
    "Mistral Large 2":  {"input": 2.00,  "output": 6.00,  "cache_hit": None},
}
```

### 5.2 成本模拟器

```
┌─────────────────────────────────────────────┐
│           成本模拟器                         │
│                                             │
│  月均 API 调用量: [10000] 次                │
│  平均输入 token:  [520]  (压缩前)          │
│  平均输出 token:  [200]                     │
│  缓存命中率:      [30] %                    │
│                                             │
│  选择模型对比:                               │
│  ☑ GPT-4o   ☑ Claude Opus 4   ☑ DeepSeek   │
│                                             │
│  ┌─────────────────────────────────────────┐│
│  │          压缩前          压缩后          ││
│  │ GPT-4o:   $18.75/月  →  $6.50/月       ││
│  │ Claude:   $45.00/月  →  $15.60/月      ││
│  │ DeepSeek: $1.62/月   →  $0.56/月       ││
│  └─────────────────────────────────────────┘│
│                                             │
│  年度节省: GPT-4o $147 | Claude $352.8      │
└─────────────────────────────────────────────┘
```

---

## 6. 项目结构

```
token-calculator/
├── src/
│   └── token_calculator/
│       ├── __init__.py
│       ├── _app.py              ← create_app() 工厂函数
│       ├── _pricing.py          ← PricingRegistry 类
│       ├── _models.py           ← Pydantic 模型
│       ├── _static.py           ← 静态文件服务
│       ├── _tokenizer_base.py          ← TokenizerBase 抽象基类
│       ├── _tokenizer_tiktoken.py      ← TiktokenTokenizer (o200k_base, cl100k_base)
│       ├── _tokenizer_hf.py            ← HfTokenizer (Llama, Qwen, DeepSeek, GLM)
│       ├── _tokenizer_sentencepiece.py ← SentencePieceTokenizer (Gemma)
│       ├── _tokenizer_mistral.py       ← MistralTokenizer (Tekken)
│       ├── _tokenizer_registry.py      ← Tokenizer 工厂 + 懒加载缓存
│       ├── _cost_simulator.py          ← CostSimulator 月度成本模拟
│       ├── _compressor_base.py         ← CompressorBase 抽象基类
│       ├── _rule_compressor.py         ← RuleCompressor 规则引擎
│       └── _llm_compressor.py          ← LLMCompressor 智能压缩
├── frontend/                    ← 改名 (原 prototype/)
│   ├── index.html
│   ├── js/
│   │   ├── config.js
│   │   └── app.js
│   └── css/
│       ├── variables.css
│       └── style.css
├── pyproject.toml
├── Dockerfile
├── .dockerignore
├── .env.example
├── run.py
├── docs/
└── tests/
```

---

## 7. 后端 API 设计

### 7.1 `GET /api/models`

返回模型注册表，供前端渲染模型选择器。

```json
{
  "groups": [
    {
      "id": "o200k_base",
      "name": "OpenAI o200k_base",
      "type": "open",
      "provider": "OpenAI",
      "models": ["GPT-4o", "GPT-4o-mini", "GPT-4.1"],
      "pricing": {"input": 2.50, "output": 10.00, "cache_hit": 1.25}
    }
  ]
}
```

### 7.2 `POST /api/tokenize`

核心 token 计数接口。

```json
// Request
{
  "text": "请帮我分析这份数据...",
  "group_ids": ["o200k_base", "llama3", "deepseek_v4"],  // 支持多个 = 多模型对比
  "mode": "input"  // "input" | "output" | "cache"
}

// Response
{
  "char_count": 520,
  "results": [
    {"group_id": "o200k_base", "model_name": "GPT-4o", "tokens": 120, "cost_usd": 0.00030, "available": true},
    {"group_id": "deepseek_v4", "model_name": "DeepSeek V3", "tokens": 110, "cost_usd": 0.00003, "available": true},
    {"group_id": "llama3", "model_name": "Llama 4 Maverick", "tokens": -1, "cost_usd": 0.0, "available": false}
  ],
  "cache_info": null
}
```

`char_count` 为输入文本的 Unicode 字符数，由后端统一计算（与分词器无关）。每个结果的 `available` 字段表示该分词器是否可用：`true` 表示初始化成功并使用真实分词器计数；`false` 表示分词器不可用（依赖未安装 / 文件缺失），此时 `tokens` 回退为 `-1`，后端使用 `len(text) * 0.25` 估算。`available = false` 的结果仅供前端展示参考，实际费用计算应跳过。
```

### 7.3 `POST /api/compress`

语义压缩接口。

```json
// Request
{
  "text": "能否请您帮我看一下这个数据集...",
  "strategy": "rule",      // "rule" | "llm"
  "level": "medium",       // "light" | "medium" | "aggressive" (仅 rule)
  "target_ratio": 0.4,     // 目标压缩率 (仅 llm)
  "llm_config": {          // LLM 配置 (仅 llm 策略)
    "provider": "openai",  // "openai" | "anthropic" | "deepseek"
    "api_key": "sk-...",   // 可选，也可用后端配置的 key
    "model": "gpt-4o-mini" // 用于压缩的模型（建议用小模型）
  }
}

// Response
{
  "strategy": "rule",
  "original_text": "能否请您帮我看一下这个数据集...",
  "compressed_text": "分析此数据集...",
  "original_tokens": {"o200k_base": 120},
  "compressed_tokens": {"o200k_base": 42},
  "savings": {
    "tokens_saved": 78,
    "percentage": 65.0,
    "estimated_monthly_savings_usd": 42.50  // 基于默认月调用量
  },
  "changes": [
    {"type": "rule", "rule": "redundant_honorific", "original": "能否请您帮我看一下", "replaced": ""},
    {"type": "rule", "rule": "filler_word", "original": "这个", "replaced": "此"}
  ]
}
```

### 7.4 `POST /api/cost-simulate`

成本模拟接口。

```json
// Request
{
  "monthly_calls": 10000,
  "avg_input_tokens": 520,
  "avg_output_tokens": 200,
  "cache_hit_rate": 0.30,
  "compression_ratio": 0.65,        // 来自压缩结果的节省比例
  "model_ids": ["GPT-4o", "Claude Opus 4", "DeepSeek V3"]
}

// Response
{
  "monthly_calls": 10000,
  "comparisons": [
    {
      "model": "GPT-4o",
      "before_compression": {"input_cost": 13.00, "output_cost": 20.00, "total": 33.00},
      "after_compression": {"input_cost": 4.55, "output_cost": 20.00, "total": 24.55},
      "monthly_savings": 8.45,
      "yearly_savings": 101.40
    }
  ],
  "best_value_model": "DeepSeek V3"
}
```

### 7.5 `GET /api/pricing`

返回全部模型价格数据。

### 7.6 `POST /api/export`

导出压缩后的 prompt（纯文本复制用）。

```json
// Request
{
  "text": "compressed prompt text...",
  "format": "plain"  // "plain" | "json" | "markdown"
}
// Response: 直接返回文本
```

---

## 8. 前端设计

### 8.1 整体布局：三面板

The three-panel layout described below applies to the Prompt Optimization Workstation (phases 2+). The Phase 1 prototype uses a simplified single-page layout with all three panels visible simultaneously, as described in frontend-ui/README.md section 3.

```
┌──────────────────────────────────────────────────────────────────┐
│  🔧 Prompt 优化工作站                    [模型: GPT-4o ▾]        │
│  ────────────────────────────────────────────────────────────────│
│                                                                  │
│  ┌─────────────────┬──────────────────┬─────────────────────────┐│
│  │  原始输入        │  压缩策略         │  对比结果               ││
│  │                 │                  │                         ││
│  │ ┌─────────────┐ │ 策略:            │ ┌─────────────────────┐ ││
│  │ │ 粘贴 Prompt  │ │ ○ 规则引擎(本地) │ │ 原始:  520 tokens   │ ││
│  │ │              │ │ ○ LLM 智能压缩   │ │         $0.0013     │ ││
│  │ │ 多轮对话JSON │ │                  │ │ 压缩后:180 tokens   │ ││
│  │ │              │ │ 强度: [中度 ▾]   │ │         $0.0005     │ ││
│  │ │              │ │                  │ │                     │ ││
│  │ │              │ │ LLM配置:         │ │ ↓ 65% 节省          │ ││
│  │ │              │ │ 模型: [GPT-4o-m] │ │                     │ ││
│  │ │              │ │ API Key: [****]  │ │ 月省: $42.50        │ ││
│  │ │              │ │                  │ │ 年省: $510.00       │ ││
│  │ └─────────────┘ │                  │ └─────────────────────┘ ││
│  │                 │                  │                         ││
│  │ 字符: 520       │ [🪄 一键压缩]    │ ┌─ 多模型对比 ────────┐ ││
│  │ 预估: ~120 tok  │                  │ │ GPT-4o:  120→42    │ ││
│  │                 │ [📋 导出] [↩️]   │ │ Claude:  135→48    │ ││
│  └─────────────────┴──────────────────┘ │ DeepSeek: 110→38    │ ││
│                                         │ Qwen:     115→40    │ ││
│                                         └─────────────────────┘ ││
│                                         ┌─ 成本模拟器 ────────┐ ││
│                                         │ 月调用: [10000] 次   │ ││
│                                         │ 月费用: $33→$24.55  │ ││
│                                         │ [条形图: 压缩前 vs 后]│││
│                                         └─────────────────────┘ ││
│                                         ┌─ 压缩率排行榜 ──────┐ ││
│                                         │ 规则引擎: 平均 38%   │ ││
│                                         │ LLM压缩: 平均 52%   │ ││
│                                         └─────────────────────┘ ││
│  └─────────────────┴──────────────────┴─────────────────────────┘│
└──────────────────────────────────────────────────────────────────┘
```

### 8.2 面板 1：原始输入

- **输入区**: 大 textarea，接受自由文本或 JSON 格式的多轮对话
- **实时预览**: 字符数 + 选中模型的预估 token 数（轻量前端估算，不等后端）
- **输入模式切换**: 
  - 📝 自由文本（默认）
  - 💬 多轮对话（提供 JSON 模板 `[{"role":"user","content":"..."}, ...]`）
- **粘贴按钮**: 一键从剪贴板粘贴

### 8.3 面板 2：压缩策略

- **策略选择**: 两个单选项，每个带简短说明
  - 🏠 规则引擎 "本地运行，毫秒级，无需 API"
  - 🤖 LLM 智能压缩 "调用小模型，质量最高"
- **强度/参数**: 根据策略动态显示
  - 规则引擎 → 强度选择 (轻度/中度/重度)
  - LLM 压缩 → 目标压缩率滑块 + 模型选择 + API Key 输入
- **一键压缩按钮**: 主行动按钮，绿色强调色
- **导出/撤销按钮**: 压缩后可导出或退回原文

### 8.4 面板 3：对比结果

#### 区域 A：核心对比卡片

```
┌────────────────────────────────┐
│  原始:  520 tokens  $0.0013    │
│          ↓ -65%                │
│  压缩后:180 tokens  $0.0005    │
│                                │
│  月省: $42.50   年省: $510.00  │
└────────────────────────────────┘
```

#### 区域 B：多模型对比表

```
┌──────────┬─────────┬─────────┬────────┬──────┐
│ 模型     │ 压缩前  │ 压缩后  │ 节省   │ 费用 │
├──────────┼─────────┼─────────┼────────┼──────┤
│ GPT-4o   │ 120 tok │ 42 tok  │ 65%    │ $0.30│
│ C.Opus 4 │ 135 tok │ 48 tok  │ 64%    │ $2.03│
│ DeepSeek │ 110 tok │ 38 tok  │ 65%    │ $0.03│
│ Qwen3    │ 115 tok │ 40 tok  │ 65%    │ $0.04│
└──────────┴─────────┴─────────┴────────┴──────┘
```

#### 区域 C：成本模拟器（可折叠）

输入月调用量，自动计算各模型压缩前后的月费用对比。用简单的横向柱状图展示。

#### 区域 D：压缩率排行榜（可折叠）

按 prompt 类型（代码类、写作类、分析类、对话类）统计的历史压缩率。

#### 区域 E：原文 vs 压缩后文本对比卡片

```
┌────────────────────────────────────────────┐
│  ▣ 原文 vs 压缩后                          │
│                                            │
│  ┌─────────────────┐  ┌─────────────────┐  │
│  │  原文 (520 字)   │  │  压缩后 (180 字) │  │
│  │                 │  │                 │  │
│  │  请帮我分析这份  │  │  分析数据，找出  │  │
│  │  数据，找出其中  │  │  异常和趋势...   │  │
│  │  的异常和趋势... │  │                 │  │
│  │                 │  │  差异高亮:       │  │
│  └─────────────────┘  │  ~~请帮我~~      │  │
│                        │  新增: 可视化    │  │
│                        └─────────────────┘  │
└────────────────────────────────────────────┘
```

- 左右并排展示原文与压缩后文本，语法高亮保留
- 差异部分使用颜色标记：删除内容红色~~删除线~~，新增内容绿色高亮
- 支持单个压缩结果对比，也支持多模型压缩结果切换对比
- 滚动同步：左右面板滚动位置联动

### 8.5 顶部模型选择器

全局模型切换器，切换后：
- 面板 1 的"预估 token"更新
- 面板 3 的对比表重新计算
- 成本模拟器结果更新

### 8.6 颜色系统（暗色仪表盘主题）

The authoritative color system is defined in frontend-ui/README.md. Below is a summary subset.

| 变量 | 色值 | 用途 |
|---|---|---|
| `--bg-page` | `#0a0e14` | 最深背景 |
| `--bg-panel` | `#12171f` | 面板背景 |
| `--bg-card` | `#1a1f2b` | 卡片/结果区 |
| `--border` | `#2a3040` | 面板/卡片边框 |
| `--accent` | `#00a8ff` | 主交互色（蓝） |
| `--success` | `#00e676` | 节省/压缩成功 |
| `--warning` | `#ff9100` | 估测/警告 |
| `--danger` | `#ff5252` | 错误 |
| `--text-primary` | `#e8ecf1` | 主文字 |
| `--text-secondary` | `#8899aa` | 次要文字 |
| `--text-dim` | `#4a5568` | 占位文字 |

> **CSS 变量约定**: CSS 变量不加命名空间前缀 — 本项目为独立部署工具，非嵌入式组件。如需集成到其他网站，使用 iframe + sandbox 属性隔离样式。完整变量定义见 frontend-ui/README.md。

### 8.7 响应式布局

| 断点 | 布局 |
|---|---|
| > 1200px | 三列并排 |
| 768-1200px | 面板 3 移到下方，上两列下全宽 |
| < 768px | 单列堆叠，面板依次排列 |

---

## 9. 实现步骤（增量迁移）—— 全部完成 ✅

> 截至 2026-07-07，所有 6 个实现步骤均已交付。以下是已完成步骤的存档记录。

### 第 1 步：`prototype/` → `frontend/` 改名 ✅ COMPLETED
- 重命名目录，调整所有内部路径引用
- 拆分 CSS：`style.css` → `variables.css` + `style.css`
- JS 封装为 IIFE，避免全局变量污染
- 验证改名前后的功能一致性

### 第 2 步：`src/token_calculator/` 包 + `create_app()` 工厂 ✅ COMPLETED
- 创建 `src/token_calculator/` 包结构
- `_app.py`：FastAPI `create_app()` 工厂函数，注册路由 + CORS
- `_pricing.py`：`PricingRegistry` 类封装价格数据
- `_models.py`：Pydantic 请求/响应模型
- `_static.py`：静态文件服务（挂载 frontend/ 目录）
- `run.py`：入口点 `uvicorn.run(create_app())`

### 第 3 步：前端对接 API（fetchModelGroups + 离线回退）✅ COMPLETED
- 前端调用 `GET /api/models` 获取模型分组（含定价）
- 实现离线回退：API 不可用时使用内联默认数据
- 三面板数据流贯通：粘贴 → 压缩 → token 计量 → 成本模拟

### 第 4 步：IIFE 封装 + CSS 拆分 ✅ COMPLETED
- 前端 JS 封装为 IIFE，暴露 `App` 命名空间
- CSS 拆分为 `variables.css`（设计令牌）和 `style.css`（组件样式）
- 统一错误处理与加载状态

### 第 5 步：Dockerfile + 部署配置 ✅ COMPLETED
- 多阶段构建（Python 构建 → 运行）
- `pyproject.toml`：项目元数据 + 依赖声明
- `.dockerignore`：排除开发文件
- `.env.example`：环境变量模板

### 第 6 步：分词器层实现（Phase 1A-1D）✅ COMPLETED

实现 4 个 Tokenizer 子类 + 注册表工厂，替换当前 `len*0.25` 占位符。

**Phase 1A：TokenizerBase + TiktokenTokenizer**
- `_tokenizer_base.py`：TokenizerBase 抽象基类，定义 `count_tokens()`、`encode()`、`decode()` 契约
- `_tokenizer_tiktoken.py`：支持 `o200k_base` 和 `cl100k_base` 两种 tiktoken 编码
- 依赖：`tiktoken >= 0.7`
- 特性：纯本地零网络，初始化 < 1ms，计数 < 1ms

**Phase 1B：HfTokenizer + MistralTokenizer**
- `_tokenizer_hf.py`：基于 transformers `AutoTokenizer`，支持 Llama 3.1、Qwen 2.5、DeepSeek V3、GLM-4
- `_tokenizer_mistral.py`：使用 mistral-common 的 Tekken 分词器，支持 Mistral Large
- 依赖：`transformers >= 4.40`，`mistral-common >= 1.3`，`huggingface-hub`
- 特性：首次加载需下载 tokenizer.json（2-10s），后续缓存到内存 < 5ms
- 注意：PyTorch 不要求（`use_fast=True` 使用 Rust 分词器库，无需安装深度学习框架）

**Phase 1C：SentencePieceTokenizer**
- `_tokenizer_sentencepiece.py`：基于 sentencepiece，支持 Gemma 3
- 依赖：`sentencepiece >= 0.2`
- 特性：`.model` 文件从 HuggingFace Hub 自动下载到 `models/gemma/tokenizer.model`
- 首次加载需下载 ~5-10 MB 的模型文件

**Phase 1D：TokenizerRegistry + API 集成**
- `_tokenizer_registry.py`：工厂函数、懒加载缓存池、`count_tokens_batch()` 批量接口
- `_pricing.py`：在 `MODEL_GROUPS` 条目中添加 `repo_id` 字段
- `_models.py`：在 `TokenizeResult` 中添加 `char_count` 字段
- `_app.py`：重写 `/api/tokenize` 和 `/api/compress` 使用真实分词器；不可用时回退 `len*0.25` 估算
- `frontend/js/app.js`：在 `runCompression()` 中添加后端 API 调用获取精确 token 数
- `pyproject.toml`：添加 `tiktoken`、`transformers`、`sentencepiece`、`mistral-common`、`huggingface-hub` 依赖

**关键设计约束**：
- 懒加载：分词器只在首次使用时初始化，缓存到进程级别字典
- 降级策略：分词器不可用时 `available=false`，`tokens=-1`，后端静默使用 `len*0.25` 估算
- 空字符串：返回 `tokens: 0` 而非报错
- Phase 2（Claude / Gemini 分词器）当前不实现，已延期

---

## 10. 验证方案

### 10.1 核心流程验证

| 步骤 | 操作 | 预期结果 |
|---|---|---|
| 1 | 粘贴中文 Prompt（~500 字） | 面板1 显示字符数 + 预估 token |
| 2 | 选择"规则引擎"策略 → 强度"中度" | — |
| 3 | 点击"一键压缩" | 面板3 显示压缩前后对比，面板1 文本替换为压缩版 |
| 4 | 切换到 "GPT-4o" 模型 | 面板3 对比表更新 |
| 5 | 添加 "Claude Opus 4" 对比 | 面板3 对比表增加一行 |
| 6 | 成本模拟器输入月调用 10000 | 显示各模型月费用对比 |
| 7 | 点击"导出" | 压缩后文本复制到剪贴板 |
| 8 | 点击"撤销" | 面板1 恢复原始文本 |

### 10.2 范围外验证（当前未覆盖）

| 项目 | 状态 |
|---|---|
| LLM 智能压缩（需 API key） | 🔲 代码结构就绪，功能测试需 API key |

### 10.3 压缩效果验证

| 测试 Prompt 类型 | 目标压缩率 (规则引擎) | 目标压缩率 (LLM) |
|---|---|---|
| 中文客服对话 prompt | 30-40% | 50-60% |
| 英文代码生成 prompt | 20-30% | 40-50% |
| 中英混合分析 prompt | 25-35% | 45-55% |

### 10.4 Token 校准

| 测试文本 | 分词器 | 预期 Token |
|---|---|---|
| `Hello world` | cl100k_base | 2 |
| `你好世界` | cl100k_base | 4 |
| 1000 字中文 | cl100k_base | ~700-800 |

---

## 附录 A: 后续扩展

### 近期（Phase 1 路线图内）
- [x] 分词器层完整实现（Phase 1A-1D，4 个 Tokenizer 子类 + 注册表 + API 集成）
- [ ] 接入真实 API 价格（自动抓取各平台官网定价）

### 中长期（无时间表）
- [ ] 图片 token 估算（GPT-4 Vision）
- [ ] 工具调用 token 估算（function calling 开销）
- [ ] 压缩历史 + 收藏夹
- [ ] 批量压缩（CSV 导入多条 prompt）
- [ ] 压缩前后对比 diff 高亮
- [ ] Chrome 插件版（一键压缩网页上的 prompt）
- [ ] Phase 2 闭源分词器（Claude / Gemini 精确计数）

## 附录 B: 规则压缩引擎详细规则

详见代码实现 `src/token_calculator/_rule_compressor.py`（规划中），核心规则：

**中文 (15 条规则)**:
冗余敬语、礼貌前缀、冗余修饰词、口语填充词、重复标点、多余空白、冗余连词、相同句合并、指令合并、示例收束……

**英文 (12 条规则)**:
礼貌请求、冗余前缀、填充短语、冗余问句、定冠词省略、多余空格……

**通用 (5 条规则)**:
空白清理、Markdown 结构保持、代码块保护、行首尾去空白、重复换行合并

---

## 11. Current Status (2026-07-07)

### 项目总体状态

| 维度 | 状态 |
|------|------|
| **实现进度** | 全部 6 个实现步骤已完成交付 |
| **前端** | 三面板暗色主题仪表盘，支持实时预览、压缩、多模型对比、成本模拟、导出/撤销，含原文 vs 压缩后文本对比 |
| **后端** | FastAPI 应用，6 个 API 端点（`/api/models`, `/api/tokenize`, `/api/compress`, `/api/cost-simulate`, `/api/pricing`, `/api/export`） |
| **分词器层** | 4 个 Tokenizer 子类（Tiktoken、HfTokenizers、SentencePiece、Mistral），8 个模型分组，懒加载注册表，可用时精确计数，不可用时自动降级 `len*0.25` 估算 |
| **压缩引擎** | 规则引擎（3 级强度 15+12+5 条规则）+ LLM 智能压缩（代码结构就绪，需 API key 验证） |
| **成本模拟器** | 月度费用模拟，支持多模型对比，缓存命中率折算 |
| **基础设施** | Docker 多阶段构建，pyproject.toml 依赖管理，.env.example 配置模板 |

### 已知待办 / 延期项

| 项目 | 延期原因 |
|------|----------|
| Gemma 分词器 (google/gemma-3-4b-it) | Google 审核中，暂缓 |
| LLM 智能压缩端到端验证 | 需 API key |
| 自动抓取实时定价 | 暂无时间表 |
| 压缩历史 / 收藏夹 | 暂无时间表 |
| Chrome 插件版 | 暂无时间表 |

### 核心指标

- **模型分组**: 8 个（o200k_base, cl100k_base, llama3, qwen, deepseek_v4, mistral, gemma🔶, glm）
- **压缩策略**: 2 种（规则引擎 + LLM 智能压缩），规则引擎含 3 级强度
- **前端响应式**: 3 档断点（>1200px / 768-1200px / <768px）
- **项目代码行数**: ~2000 行（Python + JS + CSS + HTML）
