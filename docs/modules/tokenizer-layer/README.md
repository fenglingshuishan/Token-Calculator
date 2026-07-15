# Tokenizer Layer (分词器层)

> Token 计量的核心层。封装 tiktoken、HuggingFace Transformers、SentencePiece 三种开源分词库，通过统一抽象接口向上层提供精确的 token 计数、编码和解码服务。是整个 Prompt 优化工作站的计量基石。

```
                          ┌─────────────────────────────┐
                          │       Frontend (三面板)       │
                          │  面板3: 多模型对比表          │
                          └──────────┬──────────────────┘
                                     │ POST /api/tokenize
                                     ▼
                          ┌─────────────────────────────┐
                          │      API Gateway             │
                          │  app.py → /api/tokenize      │
                          └──────────┬──────────────────┘
                                     │ 调用 tokenize()
                                     ▼
                     ┌─────────────────────────────────────┐
                     │         Tokenizer Layer              │
                     │                                     │
                     │  ┌─ TokenizerBase (抽象基类) ──────┐ │
                     │  │  count_tokens()                  │ │
                     │  │  encode() / decode()             │ │
                     │  └──────────┬───────────────────────┘ │
                     │             │                         │
                     │  ┌──────────┼──────────┬──────────┐  │
                     │  ▼          ▼          ▼          ▼  │
                     │ ┌────────┐ ┌────────┐ ┌────────┐  ┌─┐│
                     │ │Tiktoken│ │   Hf   │ │Sentence│  │…││
                     │ │Tokenizer│ │Tokenizer│ │PieceTok│  │ ││
                     │ └────────┘ └────────┘ └────────┘  └─┘│
                     └─────────────────────────────────────┘
                                     │
                     ┌───────────────┼───────────────┐
                     ▼               ▼               ▼
             ┌────────────┐  ┌────────────┐  ┌────────────┐
             │ 模型注册表  │  │ 价格系统    │  │ 成本模拟器  │
             │model-      │  │pricing     │  │cost-       │
             │registry    │  │simulator   │  │simulator   │
             └────────────┘  └────────────┘  └────────────┘
```

> **实施计划**: 见 [IMPLEMENTATION-PLAN.md](./IMPLEMENTATION-PLAN.md)。本文档定义接口契约和设计规范。

---

## 目录

1. [模块概述](#1-模块概述)
2. [TokenizerBase 抽象接口](#2-tokenizerbase-抽象接口)
3. [TiktokenTokenizer 设计](#3-tiktokentokenizer-设计)
4. [HfTokenizer 设计](#4-hftokenizer-设计)
5. [SentencePieceTokenizer 设计](#5-sentencepiecetokenizer-设计)
6. [Phase 2 预留接口（已延期）](#6-phase-2-预留接口已延期)
7. [统一返回格式](#7-统一返回格式)
8. [错误处理](#8-错误处理)
9. [与其他模块的关系](#9-与其他模块的关系)
10. [扩展指南](#10-扩展指南)

---

## 1. 模块概述

### 1.1 定位

分词器层负责将文本转换为 token 序列并精确计量 token 数量，是计量层的核心。它向上层调用方屏蔽了不同 LLM 分词器之间的实现差异——无论底层用的是 OpenAI 的 tiktoken、HuggingFace 的 transformers、还是 Google 的 SentencePiece，上层都通过同一组接口获取结果。

### 1.2 核心职责

| 职责 | 说明 |
|---|---|
| **统一计量** | 通过 `TokenizerBase` 抽象基类，为所有分词器暴露 `count_tokens()`, `encode()`, `decode()` 三个核心方法 |
| **多引擎封装** | 同时管理三种不同性质的分词库：tiktoken（纯本地，零网络）、HuggingFace Transformers（需下载 tokenizer.json）、SentencePiece（需本地 .model 文件） |
| **批量对比** | 支持同一段文本在多个模型分组下同时分词，返回 `BatchTokenizeResult` 供前端多模型对比表使用 |
| **费用计算** | 每个分词结果附带 `cost_usd` 字段，结合模型价格数据计算输入 token 费用 |
| **生命周期管理** | 处理分词器的懒加载、缓存、文件不存在等状态，确保上层调用方无需关心底层初始化细节 |

### 1.3 阶段划分

| 阶段 | 内容 | 状态 |
|---|---|---|
| **Phase 1（当前）** | TiktokenTokenizer, HfTokenizer, SentencePieceTokenizer, MistralTokenizer — 全部实现 | ✅ 实施中（详见 [IMPLEMENTATION-PLAN.md](./IMPLEMENTATION-PLAN.md)） |
| **Phase 2（后续）** | ClaudeEstimateTokenizer, GeminiTokenizer — 仅骨架类，抛出 `NotImplementedError` | 预留 |

---

## 2. TokenizerBase 抽象接口

### 2.1 接口契约

`TokenizerBase` 是所有分词器实现必须继承的抽象基类。它定义了三个抽象方法和四个只读属性，所有子类必须实现全部方法。

**属性**

| 属性 | 类型 | 说明 |
|---|---|---|
| `group_id` | `str` | 分组标识符，与模型注册表中的 `id` 一致。唯一值如 `"o200k_base"`, `"llama3"`, `"gemma"` |
| `name` | `str` | 人类可读的名称，用于前端展示。如 `"OpenAI o200k_base"`, `"Llama 3 Tokenizer"` |
| `type` | `Literal["open", "estimated"]` | 分词器类型。`"open"` 表示精确计数（开源），`"estimated"` 表示估算（闭源，Phase 2） |
| `available` | `bool` | 当前是否可用。`true` 表示已初始化完毕，`false` 表示文件缺失或未就绪 |

**方法**

| 方法 | 输入 | 输出 | 契约 |
|---|---|---|---|
| `count_tokens(text)` | `str` — 待计数字符串 | `int` — token 数量 | 返回文本在该分词器下的精确 token 数。对于 Phase 2 预留类，抛出 `NotImplementedError` |
| `encode(text)` | `str` — 待编码字符串 | `List[int]` — token ID 序列 | 将文本编码为 token ID 列表。用于调试或高级用户查看 token 组成 |
| `decode(tokens)` | `List[int]` — token ID 序列 | `str` — 还原的字符串 | 将 token ID 列表解码回文本。用于验证编码-解码的往返一致性 |

### 2.2 生命周期

```
[创建] → __init__() 设置 group_id / name / type / available
           │
           ▼
  [就绪] → count_tokens() / encode() / decode() 可被反复调用
           │
           ▼ (Python 进程退出时自然释放)
  [销毁] → 无需显式销毁方法；tiktoken 和 SentencePiece 为纯内存操作，
           HuggingFace 的缓存由该库自身的缓存机制管理
```

**关键设计原则**：
- 分词器实例是无状态的——多次调用 `count_tokens()` 同一段文本返回相同结果（纯函数）
- 线程安全——所有方法不修改内部共享状态，可安全用于多线程和异步上下文
- 初始化是幂等的——即使多次创建同一 `group_id` 的分词器，也不会重复下载

---

## 3. TiktokenTokenizer 设计

### 3.1 支持的编码

| 分组 ID | 编码名称 | 对应模型 | token 数量参考（"Hello world"） |
|---|---|---|---|
| `o200k_base` | o200k_base | GPT-4o, GPT-4o-mini, GPT-4.1, GPT-4.5 | — |
| `cl100k_base` | cl100k_base | GPT-4, GPT-4-turbo, GPT-3.5-turbo, text-embedding-3 | 2 |

### 3.2 初始化流程

```
TiktokenTokenizer.__init__("cl100k_base")
    │
    ├── 1. 检查 tiktoken 库是否已安装 → 否 → available = false
    │                                      → 日志警告 "tiktoken not installed"
    │
    ├── 2. tiktoken.get_encoding("cl100k_base")
    │      │
    │      ├── 成功 → 保存 encoding 对象引用
    │      │         available = true
    │      │
    │      └── 失败 → available = false
    │                抛出 ValueError（如编码名不存在）
    │
    └── 3. 设置 group_id / name / type = "open"
```

- **网络依赖**: 无。tiktoken 的编码定义已内置于库中，无需下载
- **性能目标**: `count_tokens()` 单次调用 < 1 毫秒
- **内存占用**: 每个 encoding 对象约 10-50 MB（根据词表大小），进程内共享

### 3.3 注意事项

- tiktoken 编码是 OpenAI 专属格式，仅用于 OpenAI 模型系列。当前使用 `o200k_base`（新）和 `cl100k_base`（旧）两种编码
- 不支持批处理——每次只对一个字符串计数，上层调用方负责聚合
- 编码后的 token ID 范围因编码而异，不应跨编码比较 token ID

> **实现文件**: `_tokenizer_tiktoken.py` | 详见 [IMPLEMENTATION-PLAN.md](./IMPLEMENTATION-PLAN.md) 的 TiktokenTokenizer 章节。

---

## 4. HfTokenizer 设计

### 4.1 支持的模型

| 分组 ID | HuggingFace 模型仓库 | 对应模型系列 | Tokenizer 文件大小 |
|---|---|---|---|
| `llama3` | `meta-llama/Llama-3.1-8B` | Llama 3, Llama 3.1, Llama 3.2, Llama 4 | ~2-5 MB |
| `qwen` | `Qwen/Qwen2.5-7B` | Qwen 2.5, Qwen 3 | ~5-10 MB |
| `deepseek_v4` | `deepseek-ai/DeepSeek-V3` | DeepSeek V3, DeepSeek R1, DeepSeek Coder V2 | ~5-10 MB |
| `glm` | `THUDM/glm-4-9b` | ChatGLM-4, GLM-4-Plus | ~2-5 MB |
| `mistral` | `mistralai/Mistral-Large-Instruct-2407` | Mistral Large, Mistral Small 3.1 | ~1-3 MB |

### 4.2 初始化流程

```
HfTokenizer.__init__("llama3")
    │
    ├── 1. 检查 transformers 库是否安装 → 否 → available = false
    │
    ├── 2. 检查本地缓存是否命中
    │      │
    │      ├── 缓存命中 → 从 ~/.cache/huggingface/ 加载 tokenizer.json
    │      │
    │      └── 缓存未命中 → 从 HuggingFace Hub 下载 tokenizer.json
    │                        （首次下载约 1-10 MB，视模型大小）
    │                        若网络不可用 → available = false
    │
    ├── 3. AutoTokenizer.from_pretrained("meta-llama/Llama-3.1-8B")
    │      │
    │      ├── 成功 → 保存 tokenizer 对象引用
    │      │         available = true
    │      │
    │      └── 失败 → available = false
    │                抛出异常（网络错误 / 仓库不存在 / 认证失败）
    │
    └── 4. 设置 group_id / name / type = "open"
```

### 4.3 缓存策略

- **本地缓存目录**: `~/.cache/huggingface/hub/`（可通过 `HF_HOME` 环境变量覆盖）
- **缓存粒度**: 整个模型仓库的 tokenizer 文件。如果用户已下载过 Llama 3.1 模型的完整权重，tokenizer 文件已包含在缓存中，无需重新下载
- **懒加载**: 只在实际调用该 `group_id` 的 `count_tokens()` 时才触发加载。系统启动时不预加载任何 HfTokenizer
- **实例池**: `group_id` 到 tokenizer 实例的映射存储在模块级字典中，同一 `group_id` 的 tokenizer 只初始化一次

### 4.4 性能特征

- **首次调用**: 取决于网络速度 + 文件大小，通常 2-10 秒（含下载）
- **后续调用**: 完全缓存到内存后，`count_tokens()` < 5 毫秒
- **内存占用**: 每个 HfTokenizer 实例约 50-200 MB（分词器模型 + Python 对象开销）。同时加载所有分组可能占用 300 MB+
- **建议**: 对于内存敏感的部署，仅在必要时加载对应分组

### 4.5 注意事项

- HuggingFace 的 `AutoTokenizer` 内部会自动选择正确的分词器子类（如 `LlamaTokenizerFast`），无需手动指定
- 部分模型仓库需要用户登录 HuggingFace 并接受许可协议（如 Llama 系列），首次下载时可能需要通过 `huggingface-cli login` 认证
- `tokenizer.json` 文件版本须与模型版本匹配，否则可能出现解码不一致

> **实现文件**: `_tokenizer_hf.py`、`_tokenizer_mistral.py` | 详见 [IMPLEMENTATION-PLAN.md](./IMPLEMENTATION-PLAN.md) 的 HfTokenizer / MistralTokenizer 章节。

---

## 5. SentencePieceTokenizer 设计

### 5.1 支持的模型

| 分组 ID | 对应模型系列 | .model 文件来源 | 文件大小 |
|---|---|---|---|
| `gemma` | Gemma 3 (gemma-3-4b-it) | 从 Google HuggingFace 仓库下载 `tokenizer.model` | ~5-10 MB |

### 5.2 初始化流程

```
SentencePieceTokenizer.__init__("gemma")
    │
    ├── 1. 检查 sentencepiece 库是否安装 → 否 → available = false
    │
    ├── 2. 查找本地 .model 文件路径
    │      │
    │      ├── 路径 1: models/{group_id}/tokenizer.model（项目内 models/ 目录）
    │      ├── 路径 2: ~/.cache/sentencepiece/{group_id}.model
    │      └── 路径 3: 配置文件中指定的自定义路径
    │
    ├── 3. 文件存在？→ 是 → spm.SentencePieceProcessor() 加载
    │      │               │
    │      │               └── 成功 → available = true
    │      │                           保存 processor 对象引用
    │      │
    │      └── 否 → 提示用户手动下载，或走 HuggingFace 中转下载
    │                日志警告: "model file not found: {path}"
    │                available = false
    │
    └── 4. 设置 group_id / name / type = "open"
```

### 5.3 .model 文件获取方式

SentencePiece 的 `.model` 文件无法通过 pip 安装获得，需要手动或自动从模型仓库获取。

**推荐方式**：
1. **从 HuggingFace 仓库的 tokenizer 子目录提取**: 大多数模型在 HuggingFace 仓库中包含 `tokenizer.model` 文件，可通过 `huggingface_hub` 库的 `hf_hub_download()` 方法下载到本地
2. **项目 `models/` 目录**: 将下载的 `.model` 文件放入 `F:\AAA\work\token-calculator\models\{group_id}\` 目录，分词器层自动识别
3. **环境变量**: 通过 `SENTENCEPIECE_MODEL_DIR` 环境变量指定自定义搜索路径

**首次使用流程**：
```
用户选择 Gemma 3 模型 → HfTokenizer 不存在 → SentencePieceTokenizer
    → 本地无 .model 文件
    → 自动从 HuggingFace Hub 下载 (google/gemma-3-4b-it → tokenizer.model)
    → 保存到 models/gemma/tokenizer.model
    → 加载完成 → 返回 TokenizeResult
```

### 5.4 注意事项

- 与 tiktoken 不同，SentencePiece 使用字节对编码（BPE），其 token 边界可能与 tiktoken 不同，这是正常的
- `.model` 文件与 Python 的 `sentencepiece` 库版本需兼容。新版 sentencepiece 可加载旧版 .model 文件，但反之未必
- Gemma 的 tokenizer 词表包含特殊控制符，`count_tokens()` 会自动排除控制符的影响

> **实现文件**: `_tokenizer_sentencepiece.py` | 详见 [IMPLEMENTATION-PLAN.md](./IMPLEMENTATION-PLAN.md) 的 SentencePieceTokenizer 章节。

---

## 6. Phase 2 预留接口（已延期）

### 6.1 设计原则

Claude 和 Gemini 的分词器在 Phase 1 中**不作为精确计数实现**，而是以骨架类的形式存在，确保模块接口、注册表、前端展示在 Phase 1 就具备完整的闭环。当闭源分词器在 Phase 2 可用时，只需填充实现体，整个过程对前端无感知。

### 6.2 骨架类规范

两个骨架类遵循相同的设计模式：

| 类名 | group_id | type | available | 行为 |
|---|---|---|---|---|
| `ClaudeEstimateTokenizer` | `claude` | `estimated` | `false` | `count_tokens()` 抛出 `NotImplementedError("Tokeniser not open-source; development in progress")` |
| `GeminiTokenizer` | `gemini` | `estimated` | `false` | `count_tokens()` 抛出 `NotImplementedError("Tokeniser not open-source; development in progress")` |

### 6.3 如何与前端联动

```
前端选择 "Claude Opus 4"
    │
    ├── GET /api/models 返回 type: "estimated", available: false
    │
    ├── 前端显示 "Claude (即将支持)" + 灰色不可选状态
    │
    └── 若用户仍然点击 → 弹窗提示 "分词器未开源，功能开发中"
```

### 6.4 Phase 2 实现路径

当闭源分词器可用时：

1. **ClaudeEstimateTokenizer**: 关注 Anthropic 是否会像 OpenAI 的 tiktoken 那样独立开源分词器。如果开源，参照 TiktokenTokenizer 的实现方式；如果不开源，则采用字符估算法（如中文约 1.8-2.2 char/token，英文约 3.5-4.0 char/token），type 保持 `estimated`
2. **GeminiTokenizer**: Gemini 与 Gemma 共享词表，Phase 2 可以直接复用 `gemma` 的 SentencePiece 模型文件，实现精确计数，type 升级为 `open`

---

## 7. 统一返回格式

### 7.1 单模型返回格式

每次 `count_tokens()` 调用返回一个 `TokenizeResult` 字典：

```json
{
  "group_id": "cl100k_base",
  "model_name": "GPT-4o",
  "tokens": 120,
  "char_count": 520,
  "cost_usd": 0.00030,
  "available": true
}
```

| 字段 | 类型 | 说明 |
|---|---|---|
| `group_id` | `str` | 分组标识符，与模型注册表一致 |
| `model_name` | `str` | 对应的人类可读模型名称，由 model-registry 提供 |
| `tokens` | `int` | token 计数结果。如果 `available = false`，值为 `-1` |
| `char_count` | `int` | 输入文本的字符数（Unicode），与分词器无关的通用属性 |
| `cost_usd` | `float` | 输入 token 费用（USD）。计算公式：`tokens / 1_000_000 * model_pricing[model_name]["input"]`。当 `tokens = -1` 时值为 `0.0` |
| `available` | `bool` | 分词器是否可用。`false` 时 `tokens` 值不可信 |

### 7.2 批量对比返回格式

当一次请求中包含多个 `group_id` 时，返回 `BatchTokenizeResult`：

```json
{
  "char_count": 520,
  "results": [
    {
      "group_id": "o200k_base",
      "model_name": "GPT-4o",
      "tokens": 120,
      "char_count": 520,
      "cost_usd": 0.00030,
      "available": true
    },
    {
      "group_id": "claude",
      "model_name": "Claude Opus 4",
      "tokens": -1,
      "cost_usd": 0.0,
      "available": false
    }
  ]
}
```

### 7.3 费用计算公式

```
cost_usd = tokens / 1_000_000 * pricing
```

其中 `pricing` 来自 model-registry 模块，对应模型的 `input` 价格（单位：美元/百万 token）。`tokens = -1` 时费用设为 `0.0`。

- → 参见 [cost-simulator 模块](../cost-simulator/README.md) 获取完整的价格计算模型，包括 output 费用和缓存命中折扣

---

## 8. 错误处理

### 8.1 错误分类矩阵

| 类别 | 触发条件 | 表现 | 降级策略 |
|---|---|---|---|
| **分词器未初始化** | 依赖库未安装（tiktoken / transformers / sentencepiece 缺失），或首次下载网络故障 | `available = false`，日志警告 | API 层返回 HTTP 503，前端展示 "分词器暂不可用" |
| **模型文件缺失** | SentencePiece 的 `.model` 文件不存在，或 HfTokenizer 的本地缓存被清除 | `available = false`，日志提示下载命令 | API 层返回 HTTP 404 + `available: false`，前端引导用户下载文件 |
| **文本编码异常** | 输入包含非法 UTF-8 序列、二进制数据、或空字符串 | 抛出 `ValueError` | API 层捕获异常，返回 HTTP 400，错误信息 "Invalid text encoding" |
| **不支持的分组 ID** | `group_id` 不在 model-registry 中 | 抛出 `KeyError` 或 `LookupError` | API 层返回 HTTP 400，错误信息 "Unknown group_id: {id}" |
| **Phase 2 预留调用** | 尝试使用 `ClaudeEstimateTokenizer` 或 `GeminiTokenizer` 的 `count_tokens()` | 抛出 `NotImplementedError` | API 层捕获异常，返回 HTTP 501 + `available: false`，前端显示 "即将支持" |

### 8.2 错误传播链

```
TokenizerLayer.count_tokens()
    │  内部异常
    ▼
TokenizerError (自定义异常类，包装原始异常)
    │
    ▼
API Gateway (app.py)
    │  捕获 TokenizerError → 映射为 HTTP 状态码
    │
    ▼
Frontend (JavaScript)
    │  解析响应 → 展示错误提示
    │
    ▼
用户看到可理解的错误信息
```

### 8.3 边界情况处理

| 边界情况 | 处理方式 |
|---|---|
| **空字符串** | 返回 `tokens: 0`，不抛出异常 |
| **纯空白字符串** | 按分词器逻辑正常计数（通常为 1 或 2 个 token） |
| **超长文本（>1M 字符）** | 正常处理，不做截断。但性能预期会显著下降（HfTokenizer 可能 >100ms） |
| **仅包含特殊字符** | 按分词器逻辑正常计数 |
| **并发请求同一分词器** | 安全——`count_tokens()` 使用 loc 级对象，不修改共享状态 |

### 8.4 日志规范

所有错误以 `ERROR [tokenizer:{group_id}] {message}` 格式记录，便于根据 group_id 过滤日志：

```
ERROR  [tokenizer:gemma] Model file not found: models/gemma/tokenizer.model
ERROR  [tokenizer:llama3] transformers library not installed, install with: pip install transformers
WARN   [tokenizer:claude] ClaudeEstimateTokenizer called count_tokens() — not implemented yet
```

---

## 9. 与其他模块的关系

### 9.1 依赖关系

```
┌─────────────────────┐
│    Model Registry    │ ◄── 读取：tokenizer 分组 ID、模型名称、类型
│ (model-registry)     │     启动时 tokenizer-layer 获取分组列表
└─────────┬───────────┘
          │ 提供分组配置
          ▼
┌─────────────────────┐
│   Tokenizer Layer   │
└──┬──┬──┬──┬──┬─────┘
   │  │  │  │  │
   │  │  │  │  └── 被调用：POST /api/tokenize
   │  │  │  │               API Gateway (api-gateway)
   │  │  │  │
   │  │  │  └────── 消费：tokenize_result.tokens
   │  │  │               Pricing Simulator (cost-simulator)
   │  │  │               → token × price = cost
   │  │  │
   │  │  └───────── 消费：压缩前后 token 对比
   │  │               Compression Engine (compression-engine)
   │  │               → 原始 token vs 压缩后 token
   │  │
   │  └──────────── 消费：多模型对比表数据
   │                 Frontend UI (frontend-ui)
   │                 → 面板 3 的 token 对比表
   │
   └─────────────── 配置：通过 model-registry 读取
                    → HfTokenizer 需要 group_id → repo_id 映射
                    → SentencePieceTokenizer 需要 model_id → .model 文件路径
```

### 9.2 各模块交互详情

| 关联模块 | 方向 | 交互内容 | 接口 / 契约 |
|---|---|---|---|
| [model-registry](../model-registry/README.md) | 依赖 | 读取分组 ID、模型列表、类型（open/estimated）、价格数据 | `registry.get_group(group_id) → GroupConfig` |
| [api-gateway](../api-gateway/README.md) | 被调用 | `POST /api/tokenize` 转发请求到 tokenizer-layer | `tokenizer_layer.count_tokens_batch(text, group_ids) → BatchTokenizeResult` |
| [frontend-ui](../frontend-ui/README.md) | 被消费 | 面板 3 的多模型对比表渲染数据 | `BatchTokenizeResult` JSON 直供前端 |
| [cost-simulator](../cost-simulator/README.md) | 配合 | token 数 × 价格 = 费用。tokenizer-layer 的 `cost_usd` 字段使用了 pricing 数据 | `cost_usd = tokens / 1_000_000 * PRICING[model_name]["input"]` |
| [compression-engine](../compression-engine/README.md) | 配合 | 压缩前调用 `count_tokens()` 获取原始 token 数，压缩后再次调用得到对比 | 两次独立调用，结果对比由 compression-engine 完成 |

### 9.3 API 调用示例

- → 参见 [api-gateway 模块](../api-gateway/README.md#post-apitokenize) 了解 `POST /api/tokenize` 的完整请求/响应格式
- → 参见 [frontend-ui 模块](../frontend-ui/README.md#面板-3对比结果) 了解 token 数据在前端面板 3 中的渲染方式
- → 参见 [cost-simulator 模块](../cost-simulator/README.md#费用计算公式) 了解价格计算细节
- → 参见 [model-registry 模块](../model-registry/README.md#模型分组按分词器) 了解分组配置结构

---

## 10. 扩展指南

### 10.1 添加新的开源分词器

如果你需要为一个新模型添加分词器支持（例如新增的 `command-r` 或 `aya` 模型），按以下步骤操作。

#### 步骤 1：在 model-registry 中注册分组

- → 参见 [model-registry 模块](../model-registry/README.md#扩展指南)

在 `model-registry` 的 `GROUP_MAP` 或配置文件中新增一个分组条目：

```
分组 ID: "cohere"
分词器类型: "hf"       (使用 HuggingFace Transformers)
HuggingFace 仓库: "CohereForAI/aya-23-8B"
模型列表: ["Command R+", "Aya 23"]
```

#### 步骤 2：创建 Tokenizer 子类

在 `backend/tokenizers/` 目录下创建新的 Python 文件，继承 `TokenizerBase`。

**决策树** —— 选择用哪种基类驱动：

```
新模型的分词器来源是？
    ├── OpenAI tiktoken 编码 → 继承 TiktokenTokenizer 并设置 encoding_name
    ├── HuggingFace AutoTokenizer → 继承 HfTokenizer 并设置 repo_id
    ├── SentencePiece .model 文件 → 继承 SentencePieceTokenizer 并设置 model_path
    └── 其他自定义格式 → 直接继承 TokenizerBase，手动实现全部 3 个方法
```

#### 步骤 3：实现三个抽象方法

- `count_tokens(text)`：调用底层分词库的编码方法，返回 len(tokens)
- `encode(text)`：调用底层分词库的编码方法，返回 token ID 列表
- `decode(tokens)`：调用底层分词库的解码方法，返回字符串

实现时需要关注：
- 特殊 token 的处理（如 `<|endoftext|>`, `<s>`, `</s>`）——通常不需要计数，但不同分词器处理方式不同
- 是否添加了 BOS/EOS token——某些分词器自动添加，某些不添加。`count_tokens()` 应以实际业务场景为准（API 调用时模型自动添加的 BOS/EOS 不计入用户输入 token）

#### 步骤 4：注册到 Tokenizer 工厂

在 tokenizer-layer 的注册工厂（或 `registry.py`）中将新分组 ID 与实现的类关联：

```
group_id → Class 映射
"cohere" → CohereTokenizer
```

### 10.2 添加新分词器的检查清单

| 检查项 | 说明 |
|---|---|
| [ ] 分组 ID 不与现有分组冲突 | 检查 model-registry 中的所有 group_id |
| [ ] 继承 `TokenizerBase` | 确保所有抽象方法已实现 |
| [ ] 设置正确的 `type` | 开源为 `"open"`，闭源估测为 `"estimated"` |
| [ ] 设置正确的 `group_id` | 必须与 model-registry 中的配置一致 |
| [ ] `available` 状态管理 | 初始化失败时应设为 `false` |
| [ ] 测试「空字符串」和「纯空白」边界 | 确保返回 0 或合理值 |
| [ ] 测试「编码-解码」往返一致性 | `decode(encode(text))` 应接近原文本 |
| [ ] 注册到工厂 | 确保 `registry.py` 中包含新映射 |
| [ ] 前端无改动 | 如果使用已有 `group_id` 类型，前端自动适配 |

### 10.3 常见问题

| 问题 | 解决方法 |
|---|---|
| **分词器文件版本不匹配** | 确保 HuggingFace 仓库中的 `tokenizer.json` 版本与模型权重版本一致。下载时固定仓库的 commit hash 或 tag |
| **特殊 token 导致 token 计数不一致** | 阅读模型的 tokenizer 配置文件（`tokenizer_config.json`），确认 `add_bos_token` 和 `add_eos_token` 的设置 |
| **SentencePiece .model 文件加载报错** | 检查 `.model` 文件是否完整（被截断的下载），以及 `sentencepiece` 库版本是否 >= 0.1.99 |
| **HuggingFace 认证失败** | 需要用户运行 `huggingface-cli login` 并接受模型仓库的许可协议（如 Llama 系列需要访问请求） |
| **多个分词器同时加载后内存不足** | 建议按需懒加载，不要一次性初始化所有分词器。可考虑为 HfTokenizer 设置最大实例数 |
