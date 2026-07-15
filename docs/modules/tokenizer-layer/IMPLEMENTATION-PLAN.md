# Tokenizer Layer 实施计划

> **版本**: 2.0.0  
> **日期**: 2026-07-07  
> **状态**: ✅ 全部完成 — 所有 Phase 1A-1D 已交付，Gemma 暂缓  
> **前置依赖**: [tokenizer-layer/README.md](README.md)（设计文档）、[model-registry/README.md](../model-registry/README.md)、[_pricing.py](../../../src/token_calculator/_pricing.py)

---

## 目录

1. [概述](#1-概述)
2. [文件变更清单](#2-文件变更清单)
3. [TokenizerBase 抽象基类](#3-tokenizerbase-抽象基类)
4. [各分词器实现](#4-各分词器实现)
5. [分词器配置映射](#5-分词器配置映射)
6. [分词器注册表](#6-分词器注册表)
7. [后端 API 集成](#7-后端-api-集成)
8. [前端集成](#8-前端集成)
9. [模型文件下载策略](#9-模型文件下载策略)
10. [依赖管理](#10-依赖管理)
11. [降级与回退](#11-降级与回退)
12. [测试计划](#12-测试计划)
13. [实施顺序](#13-实施顺序)

---

## 1. 概述

### 1.1 本文档的定位

本文档是 **分词器层（Tokenizer Layer）的详细实施蓝图**，面向负责编写该模块代码的开发者。它站在设计文档（`README.md`）的肩膀上，将抽象设计转化为可逐行执行的实施指令。

**设计文档与实施计划的分工**：

| 维度 | 设计文档 (README.md) | 实施计划 (本文档) |
|---|---|---|
| 读者 | 所有开发者、架构评审者 | 负责编写的开发者 |
| 内容 | 模块职责、接口设计、架构决策 | 文件清单、类签名、代码变更、实施顺序 |
| 粒度 | 概念级（流程图、接口表） | 实现级（import 路径、错误码值、测试参考值） |
| 维护 | 随架构变更更新 | 随代码变更更新——代码即真相 |

### 1.2 实施范围

本计划覆盖 **Phase 1 的全部 4 个分词器实现**：

| 库 | 类 | 覆盖分组数 | 覆盖分组 |
|---|---|---|---|
| tiktoken | TiktokenTokenizer | 2 | o200k_base, cl100k_base |
| transformers | HfTokenizer | 4 | llama3, qwen, deepseek_v4, glm |
| sentencepiece | SentencePieceTokenizer | 1 | gemma |
| mistral-common | MistralTokenizer | 1 | mistral |

**不在此实施范围内的内容**（已从注册表中移除）：
- Phase 2 预留分组（claude、gemini）
- 已废弃分组（p50k_base, llama2, mistral_old, gemma2, yi）

### 1.3 实施后的架构变化

实施前，`POST /api/tokenize` 使用字符估算法（`estimate_tokens()`）返回粗略 token 估算值。实施后，调用链变为：

```
POST /api/tokenize
  → _app.py: tokenize() 端点
    → TokenizerRegistry.count_tokens_batch(text, group_ids)
      → 逐个 group_id 从注册表获取 TokenizerBase 实例（懒加载）
        → 实例.count_tokens(text)   # 精确计数
      → 合并结果 + 计算费用
    → 返回 TokenizeResponse
```

### 1.4 关键设计决策

以下决策贯穿整个实施过程，在此集中列出以便参考：

| # | 决策 | 理由 |
|---|---|---|
| D1 | 构造函数只设置元数据；`initialize()` 做实际的库加载 | 构造函数应始终成功；库加载可能因缺依赖/网络故障而失败 |
| D2 | 缓存失败的实例（防止重复下载尝试） | 避免每次请求都重试失败的下载 |
| D3 | 空字符串返回 0 token，不抛异常 | `len(encode(""))` 天然为 0，不额外加特殊逻辑；对调用方更友好 |
| D4 | 按 group_id 顺序逐个计数（非并行） | 8 个分组以内，逐个计数总时间 < 1 秒，并行带来的复杂度不值得 |
| D5 | tiktoken 视为总是可用（纯 Python，内置词表） | tiktoken 无原生扩展，pip install 后即可用 |
| D6 | mistral-common 自带内置 tokenizer（无需下载） | 库已打包 tokenizer 文件 |
| D7 | HuggingFace tokenizer 由 transformers 自动缓存到 `~/.cache/huggingface/hub/` | transformers 的 `from_pretrained` 自带缓存机制 |
| D8 | SentencePiece .model 文件下载到 `models/{group_id}/` | 项目级管理，不受系统缓存影响 |
| D9 | `initialize()` 可被多次调用，后续调用为 no-op | 简化生命周期管理 |
| D10 | 所有分词器方法的 text 参数接受空字符串，返回 0 token | 统一边界行为，免除调用方做空检查 |

---

## 2. 文件变更清单

### 2.1 新增文件（6 个）

| # | 文件路径 | 用途 |
|---|---|---|
| F1 | `src/token_calculator/tokenizers/__init__.py` | 包初始化，导出所有公共符号 |
| F2 | `src/token_calculator/tokenizers/_base.py` | TokenizerBase 抽象基类 + TokenizerError 异常 |
| F3 | `src/token_calculator/tokenizers/_tiktoken.py` | TiktokenTokenizer 实现 |
| F4 | `src/token_calculator/tokenizers/_hf.py` | HfTokenizer 实现 |
| F5 | `src/token_calculator/tokenizers/_sentencepiece.py` | SentencePieceTokenizer 实现 |
| F6 | `src/token_calculator/tokenizers/_mistral.py` | MistralTokenizer 实现 |
| F7 | `src/token_calculator/tokenizers/_registry.py` | TokenizerRegistry（工厂+缓存+批量接口） |
| F8 | `scripts/download_tokenizers.sh` | 模型文件批量下载脚本 |

> 新增 8 个文件。F7 虽为核心注册逻辑，但体量较大（约 80 行），单独成文件而非合入 `__init__.py`。

### 2.2 修改文件（5 个）

| # | 文件路径 | 变更说明 |
|---|---|---|
| M1 | `src/token_calculator/_models.py` | TokenizeResult 新增 `char_count` 字段 |
| M2 | `src/token_calculator/_app.py` | 替换 `estimate_tokens()` 调用为 `TokenizerRegistry.count_tokens_batch()` |
| M3 | `pyproject.toml` | 新增 4 个可选依赖组 |
| M4 | `test_e2e.py` | 新增 tokenizer 集成测试用例 |
| M5 | `docs/modules/tokenizer-layer/README.md` | 更新设计文档，对齐最终实施细节 |

### 2.3 实施后的目录结构

```
src/token_calculator/
├── __init__.py
├── _app.py              # [修改] 集成 tokenizer 注册表
├── _models.py           # [修改] TokenizeResult 新增 char_count
├── _pricing.py          # 不变
├── _static.py           # 不变
├── tokenizers/          # [新增] 分词器层
│   ├── __init__.py
│   ├── _base.py
│   ├── _tiktoken.py
│   ├── _hf.py
│   ├── _sentencepiece.py
│   ├── _mistral.py
│   └── _registry.py

scripts/
└── download_tokenizers.sh  # [新增] 模型文件下载脚本

models/                     # [新增] 本地模型文件目录
├── gemma/
│   └── tokenizer.model     # 自动下载
└── .gitkeep
```

---

## 3. TokenizerBase 抽象基类

### 3.1 文件位置

`src/token_calculator/tokenizers/_base.py`

### 3.2 完整类契约

```python
from abc import ABC, abstractmethod
from typing import Literal


class TokenizerError(Exception):
    """分词器异常的基类。

    所有分词器实现抛出的自定义异常都应继承此类，以便 _app.py
    统一捕获并映射为 HTTP 错误响应。

    属性:
        group_id: 发生错误的分词器分组 ID
        message: 人类可读的错误描述
        original_exception: 原始异常（如有），用于日志记录
    """

    def __init__(
        self,
        group_id: str,
        message: str,
        original_exception: Exception | None = None,
    ):
        self.group_id = group_id
        self.original_exception = original_exception
        super().__init__(f"[tokenizer:{group_id}] {message}")


class InitializationError(TokenizerError):
    """分词器初始化失败。例如缺少依赖库、模型文件不存在、网络错误。"""


class TokenizationError(TokenizerError):
    """分词过程出错。例如输入包含非法编码。"""


class TokenizerBase(ABC):
    """所有分词器实现的抽象基类。

    子类必须实现三个抽象方法和四个只读属性。
    子类构造函数应该只设置元数据；实际的库加载工作在 initialize() 中完成。
    """

    # --- 只读属性 ---

    @property
    @abstractmethod
    def group_id(self) -> str:
        """分组标识符，与模型注册表中的 group_id 一致。"""

    @property
    @abstractmethod
    def name(self) -> str:
        """人类可读的名称，用于前端展示。"""

    @property
    @abstractmethod
    def type(self) -> Literal["open", "estimated"]:
        """分词器类型。'open' = 精确计数，'estimated' = 估算。"""

    @property
    @abstractmethod
    def available(self) -> bool:
        """当前是否可用。True = 已初始化完毕。"""

    @property
    @abstractmethod
    def provider(self) -> str:
        """返回模型提供商名称（如 'OpenAI', 'Meta', 'Google'）。"""

    # --- 生命周期 ---

    @abstractmethod
    def initialize(self) -> None:
        """执行实际的库初始化和模型文件加载。

        此方法可能耗时（涉及下载或文件 I/O）。
        - 成功：设置 available = True
        - 失败：设置 available = False，记录日志，不抛异常
        - 幂等：多次调用仅第一次有效，后续为 no-op
        """

    # --- 核心方法 ---

    @abstractmethod
    def count_tokens(self, text: str) -> int:
        """返回文本在该分词器下的精确 token 数。

        空字符串返回 0，不抛异常。
        """

    @abstractmethod
    def encode(self, text: str) -> list[int]:
        """将文本编码为 token ID 列表。"""

    @abstractmethod
    def decode(self, tokens: list[int]) -> str:
        """将 token ID 列表解码回文本。"""
```

### 3.3 异常层次结构

```
TokenizerError (Base)
├── InitializationError     # 初始化失败
└── TokenizationError       # 分词过程出错
```

### 3.4 边界行为

| 输入 | count_tokens 行为 | encode 行为 | decode 行为 |
|---|---|---|---|
| 空字符串 `""` | 返回 `0` | 返回 `[]` | — |
| 纯空白 `"   "` | 按分词器正常计数（通常为 1-2 token） | 正常编码 | — |
| 超长文本 (1M+ 字符) | 正常处理，不做截断（但性能会下降） | 正常编码 | — |
| 空列表 `[]` | — | — | 返回 `""` |

### 3.5 日志规范

所有 tokenizer 模块统一使用以下日志格式：

```
级别  [tokenizer:{group_id}] 消息
```

示例：

```
ERROR   [tokenizer:gemma] Model file not found: models/gemma/tokenizer.model
WARNING [tokenizer:llama3] transformers library not installed, falling back
INFO    [tokenizer:mistral] MistralTokenizer initialized successfully
```

---

## 4. 各分词器实现

### 4.1 TiktokenTokenizer

**文件**: `src/token_calculator/tokenizers/_tiktoken.py`

#### 4.1.1 初始化流程

```
TiktokenTokenizer.__init__(group_id, encoding_name)
  │
  ├── 设置 self._group_id = group_id
  ├── 设置 self._encoding_name = encoding_name
  ├── 设置 self._available = False
  ├── 设置 self._encoding = None
  └── 注意：此时不加载 tiktoken，不调用 get_encoding()

TiktokenTokenizer.initialize()
  │
  ├── 1. 幂等检查：如果 self._available 已为 True，直接返回
  │
  ├── 2. 尝试 import tiktoken
  │      │
  │      ├── 成功 → 继续
  │      └── ImportError → self._available = False
  │                        logging.warning("[tokenizer:{group_id}] tiktoken not installed")
  │                        return
  │
  ├── 3. 尝试 tiktoken.get_encoding(self._encoding_name)
  │      │
  │      ├── 成功 → self._encoding = encoding
  │      │          self._available = True
  │      │
  │      └── 失败 (KeyError) → self._available = False
  │                            logging.error("[tokenizer:{group_id}] Unknown encoding: {name}")
  │                            return
  │
  └── 4. 初始化完成
```

#### 4.1.2 支持的编码名称

| group_id | encoding_name | 底层 tiktoken 常量 |
|---|---|---|
| `o200k_base` | `"o200k_base"` | `tiktoken.get_encoding("o200k_base")` |
| `cl100k_base` | `"cl100k_base"` | `tiktoken.get_encoding("cl100k_base")` |

> 注意：tiktoken 3.0+ 已将内置词表与安装包分离，改为首次使用下载，但仍是纯 Python 操作，无需额外库。

#### 4.1.3 count_tokens 实现

```python
def count_tokens(self, text: str) -> int:
    if not self._available:
        raise InitializationError(
            self._group_id,
            "TiktokenTokenizer not initialized. Call initialize() first.",
        )
    if not text:  # 空字符串
        return 0
    return len(self._encoding.encode(text))
```

#### 4.1.4 当 tiktoken 未安装时的行为

| 场景 | available | count_tokens() | 前端展示 |
|---|---|---|---|
| tiktoken 未安装 | `False` | 抛出 `InitializationError` | "分词器暂不可用" + 安装引导 |
| tiktoken 已安装但编码名不存在 | `False` | 抛出 `InitializationError` | "分词器配置异常，请联系开发者" |

> 注意：`POST /api/tokenize` 在遇到 `available=False` 时会返回 `available=false` 的 TokenizeResult 并附带错误信息，不会使整个请求失败。参见 [第 11 章降级与回退](#11-降级与回退)。

#### 4.1.5 测试参考值

| 输入 | o200k_base | cl100k_base |
|---|---|---|
| `"Hello world"` | 2 | 2 |
| `""` | 0 | 0 |
| `"a"` | 1 | 1 |
| `"你好世界"` | 4 | 4 |
| `" "`（单个空格） | 1 | 1 |

### 4.2 HfTokenizer

**文件**: `src/token_calculator/tokenizers/_hf.py`

#### 4.2.1 初始化流程

```
HfTokenizer.__init__(group_id, repo_id)
  │
  ├── 设置 self._group_id = group_id
  ├── 设置 self._repo_id = repo_id
  ├── 设置 self._available = False
  ├── 设置 self._tokenizer = None
  └── 注意：此时不加载 transformers

HfTokenizer.initialize()
  │
  ├── 1. 幂等检查：如果 self._available 已为 True，直接返回
  │
  ├── 2. 尝试 from transformers import AutoTokenizer
  │      │
  │      ├── 成功 → 继续
  │      └── ImportError → self._available = False
  │                        logging.warning("[tokenizer:{group_id}] transformers not installed")
  │                        return
  │
  ├── 3. 尝试 AutoTokenizer.from_pretrained(
  │         self._repo_id,
  │         use_fast=True,       # 使用 Rust 加速的分词器
  │         trust_remote_code=True,  # GLM 等模型需要
  │      )
  │      │
  │      ├── 成功 → self._tokenizer = tokenizer
  │      │          self._available = True
  │      │
  │      ├── OSError (网络/缓存) → self._available = False
  │      │   logging.error("[tokenizer:{group_id}] Failed to load tokenizer from {repo_id}")
  │      │
  │      └── 其他异常 → self._available = False
  │                     logging.exception("[tokenizer:{group_id}] Unexpected error")
  │
  └── 4. 初始化完成
```

#### 4.2.2 group_id 到 repo_id 的映射

| group_id | repo_id | 需要 HF 认证？ | 模型文件大小 |
|---|---|---|---|
| `llama3` | `meta-llama/Llama-3.1-8B` | 是（接受许可协议） | ~2-5 MB (tokenizer.json) |
| `qwen` | `Qwen/Qwen2.5-7B` | 否（公开） | ~5-10 MB |
| `deepseek_v4` | `deepseek-ai/DeepSeek-V3` | 否（公开） | ~5-10 MB |
| `glm` | `THUDM/glm-4-9b` | 否（公开） | ~2-5 MB |

#### 4.2.3 关于 use_fast=True

所有 HfTokenizer 实例均设置 `use_fast=True`，使用 HuggingFace 的 Rust 加速分词器（TokenizerFast 子类）。原因：

- 性能：fast tokenizer 比纯 Python 实现快 5-10 倍
- 无 PyTorch 依赖：fast tokenizer 仅需要 `tokenizers` 库（transformers 的依赖），不需要 PyTorch 或 TensorFlow
- 文件兼容：tokenizer.json 同时被 fast 和 slow tokenizer 支持

> **风险澄清**：`use_fast=True` 并不需要 PyTorch。HuggingFace 的 "fast" 分词器基于 `tokenizers` 库（Rust 绑定），与深度学习框架无关。这是常见的误解，已通过 transformers 文档确认。

#### 4.2.4 门控模型（Gated Model）处理

`llama3` 分组对应的 `meta-llama/Llama-3.1-8B` 是门控模型，需要用户登录 HuggingFace 并接受许可协议。

**处理策略**：

1. 首次尝试 `from_pretrained()` 时，transformers 会自动检查缓存。
2. 如果用户未登录且未接受许可，transformers 会抛出 `OSError`，HfTokenizer 捕获后：
   - `available = False`
   - 日志输出指引：`"To access meta-llama/Llama-3.1-8B, run: huggingface-cli login and accept the license at https://huggingface.co/meta-llama/Llama-3.1-8B"`
3. 如果用户已登录并接受许可，transformers 会自动下载 tokenizer.json 到缓存目录。
4. 两次初始化之间失败实例会被缓存，不会重复尝试下载。

**在下载脚本中的处理**：参考 [第 9 章模型文件下载策略](#9-模型文件下载策略)。

#### 4.2.5 缓存行为

- 缓存目录：`~/.cache/huggingface/hub/`（由 transformers 管理）
- 缓存不可用时：完全离线可用（如果已缓存）；首次使用需要网络
- 缓存清除：由用户通过 `rm -rf ~/.cache/huggingface/hub/` 或 `HF_HOME` 环境变量控制

#### 4.2.6 测试参考值

以下为使用对应 tokenizer 对已知文本的精确 token 数参考值（验证用）：

| 输入 | llama3 | qwen | deepseek_v4 | glm |
|---|---|---|---|---|
| `"Hello world"` | 待实测 | 待实测 | 待实测 | 待实测 |
| `""` | 0 | 0 | 0 | 0 |
| `"你好世界"` | 待实测 | 待实测 | 待实测 | 待实测 |

> **说明**：以上参考值将在 Phase 1B/HfTokenizer 实现后被填入精确值。实施者需在实现后运行一次测试记录实际值。

#### 4.2.7 GLM 模型注意事项

GLM-4-9B 使用 `chatglm` 格式的 tokenizer，需要 `trust_remote_code=True` 来加载自定义分词器代码。HfTokenizer 的 `from_pretrained()` 调用已包含此参数。如果加载失败，确认 transformers 版本 >= 4.48.0（此版本对 GLM 的兼容性较好）。

### 4.3 SentencePieceTokenizer

**文件**: `src/token_calculator/tokenizers/_sentencepiece.py`

#### 4.3.1 初始化流程

```
SentencePieceTokenizer.__init__(group_id, model_name_or_path)
  │
  ├── 设置 self._group_id = group_id
  ├── 设置 self._model_name_or_path = model_name_or_path
  ├── 设置 self._available = False
  ├── 设置 self._processor = None
  └── 注意：此时不加载 sentencepiece

SentencePieceTokenizer.initialize()
  │
  ├── 1. 幂等检查：如果 self._available 已为 True，直接返回
  │
  ├── 2. 尝试 import sentencepiece as spm
  │      │
  │      ├── 成功 → 继续
  │      └── ImportError → self._available = False
  │                        logging.warning("[tokenizer:{group_id}] sentencepiece not installed")
  │                        return
  │
  ├── 3. 解析 .model 文件路径（按优先级）
  │      │
  │      ├── 路径 A: 显式构造函数传入的 path（self._model_name_or_path 是 .model 路径）
  │      │
  │      ├── 路径 B: models/{group_id}/tokenizer.model（项目 models/ 目录）
  │      │
  │      └── 路径 C: 自动从 HuggingFace 下载
  │                     hf_hub_download(
  │                         repo_id=self._hf_repo_id,
  │                         filename="tokenizer.model",
  │                         local_dir=f"models/{group_id}/",
  │                     )
  │                     仅在路径 A 和 B 都失败时触发
  │
  ├── 4. 找到文件 → spm.SentencePieceProcessor()
  │      │
  │      ├── Load 成功 → self._processor = sp
  │      │               self._available = True
  │      │
  │      └── Load 失败 → self._available = False
  │                       logging.error("[tokenizer:{group_id}] Failed to load model file")
  │
  └── 5. 初始化完成
```

#### 4.3.2 模型文件解析顺序（详细）

| 优先级 | 路径 | 触发条件 | 示例 |
|---|---|---|---|
| 1（最高） | `self._model_name_or_path` 直接作为 `.model` 文件路径 | 路径指向一个 `.model` 文件 | `"F:/models/gemma/tokenizer.model"` |
| 2 | `models/{group_id}/tokenizer.model` | 项目内 `models/` 目录 | `"models/gemma/tokenizer.model"` |
| 3 | 自动从 HuggingFace Hub 下载到 `models/{group_id}/` | 路径 1 和 2 都失败；且 `huggingface_hub` 已安装 | 下载 google/gemma-3-4b-it 的 tokenizer.model |

自动下载流程：

```python
def _resolve_model_path(self) -> str | None:
    # 优先级 1: 显式路径
    if self._model_name_or_path and self._model_name_or_path.endswith(".model"):
        path = Path(self._model_name_or_path)
        if path.is_file():
            return str(path)

    # 优先级 2: 项目 models/{group_id}/ 目录
    local_path = Path("models") / self._group_id / "tokenizer.model"
    if local_path.is_file():
        return str(local_path)

    # 优先级 3: 从 HuggingFace 自动下载
    if self._hf_repo_id:
        try:
            from huggingface_hub import hf_hub_download
            download_path = hf_hub_download(
                repo_id=self._hf_repo_id,
                filename="tokenizer.model",
                local_dir=f"models/{self._group_id}",
                local_dir_use_symlinks=False,
            )
            return download_path
        except Exception:
            return None

    return None
```

#### 4.3.3 Gemma 模型映射

| group_id | hf_repo_id | .model 文件在仓库中的路径 | 预期大小 |
|---|---|---|---|
| `gemma` | `google/gemma-3-4b-it` | `tokenizer.model` | ~5-10 MB |

> 注意：`gemma-3-4b-it` 仓库中的 `tokenizer.model` 文件是 SentencePiece 格式，可直接由 `sentencepiece` 库加载。Gemma 3 使用基于 SentencePiece 的 BPE 分词器，与 Gemma 2 相同。

#### 4.3.4 count_tokens 实现

```python
def count_tokens(self, text: str) -> int:
    if not self._available:
        raise InitializationError(...)
    if not text:
        return 0
    tokens = self._processor.encode_as_ids(text)
    return len(tokens)
```

#### 4.3.5 测试参考值

| 输入 | gemma (tokenizer.model from gemma-3-4b-it) |
|---|---|
| `"Hello world"` | 待实测 |
| `""` | 0 |
| `"你好世界"` | 待实测 |

#### 4.3.6 注意事项

- SentencePieceProcessor 的 `encode_as_ids()` 返回整数 ID 列表，与 `encode()` 方法一致
- Gemma 3 分词器在编码时会自动规范化输入（NFKC 标准化），这是 SentencePiece 的默认行为
- SP processor 不添加 BOS/EOS token，除非调用 `encode()` 时指定了 `add_bos=True`。本实现取 `add_bos=False`（与 API 调用行为一致）

### 4.4 MistralTokenizer

**文件**: `src/token_calculator/tokenizers/_mistral.py`

#### 4.4.1 初始化流程

```
MistralTokenizer.__init__(group_id, model_name)
  │
  ├── 设置 self._group_id = group_id
  ├── 设置 self._model_name = model_name
  ├── 设置 self._available = False
  ├── 设置 self._tokenizer = None
  └── 注意：此时不加载 mistral-common

MistralTokenizer.initialize()
  │
  ├── 1. 幂等检查：如果 self._available 已为 True，直接返回
  │
  ├── 2. 尝试 from mistral_common.tokens.tokenizers.mistral import MistralTokenizer as _MistralTok
  │      │
  │      ├── 成功 → 继续
  │      └── ImportError → self._available = False
  │                        logging.warning("[tokenizer:{group_id}] mistral_common not installed")
  │                        return
  │
  ├── 3. 尝试 _MistralTok.from_model(self._model_name)
  │      │
  │      ├── 成功 → self._tokenizer = tokenizer
  │      │          self._available = True
  │      │
  │      └── 失败 → self._available = False
  │                 logging.error("[tokenizer:{group_id}] Failed to load model: {model_name}")
  │
  └── 4. 初始化完成
```

#### 4.4.2 内置模型名称

| group_id | model_name（传给 from_model 的参数） |
|---|---|
| `mistral` | `"mistral-large"` |

> `mistral_common` 库内置了 Mistral Large 的词表文件，`from_model("mistral-large")` 直接使用打包的文件，无需网络下载。该库的内部实现是从安装包的数据目录中加载 `tokenizer.model` 文件（SentencePiece 格式）以及 `mistral_tiktoken` 的额外处理层。

#### 4.4.3 无需网络

`mistral-common` 与 tiktoken 类似：库本身包含了 tokenizer 定义和数据文件。`pip install mistral-common` 后即可离线使用，不需要连接 HuggingFace 或 Mistral AI 服务器。

#### 4.4.4 count_tokens 实现

```python
def count_tokens(self, text: str) -> int:
    if not self._available:
        raise InitializationError(...)
    if not text:
        return 0
    # mistral_common 的 tokenizer.encode() 返回一个 list[list[int]]，
    # 最外层对应 messages 列表。这里取第一个（也是唯一一个）元素。
    encoded = self._tokenizer.encode(text)
    # 注意：encode() 可能需要调用 .tokens 属性或解包
    return len(encoded[0]) if isinstance(encoded[0], list) else len(encoded)
```

> **实施注意**：`mistral_common` 的 API 在不同版本间有变化。实施时应根据实际安装的版本调整。如果 `encode()` 签名复杂，考虑直接使用底层 SentencePiece processor：`self._tokenizer._sp_model.encode_as_ids(text)`。

#### 4.4.5 测试参考值

| 输入 | mistral-large |
|---|---|
| `"Hello world"` | 待实测 |
| `""` | 0 |
| `"你好世界"` | 待实测 |

---

## 5. 分词器配置映射

### 5.1 完整映射表

| group_id | library | class name | encoding/repo_id/model_name | 依赖库 |
|---|---|---|---|---|
| `o200k_base` | tiktoken | TiktokenTokenizer | `encoding="o200k_base"` | tiktoken |
| `cl100k_base` | tiktoken | TiktokenTokenizer | `encoding="cl100k_base"` | tiktoken |
| `llama3` | transformers | HfTokenizer | `repo_id="meta-llama/Llama-3.1-8B"` | transformers |
| `qwen` | transformers | HfTokenizer | `repo_id="Qwen/Qwen2.5-7B"` | transformers |
| `deepseek_v4` | transformers | HfTokenizer | `repo_id="deepseek-ai/DeepSeek-V3"` | transformers |
| `glm` | transformers | HfTokenizer | `repo_id="THUDM/glm-4-9b"` | transformers |
| `gemma` | sentencepiece | SentencePieceTokenizer | `repo_id="google/gemma-3-4b-it"` | sentencepiece, huggingface_hub |
| `mistral` | mistral-common | MistralTokenizer | `model_name="mistral-large"` | mistral-common |

### 5.2 映射常量（注册表内部使用）

以下常量定义在 `_registry.py` 中：

```python
# group_id → (TokenizerClass, init_kwargs)
_TOKENIZER_MAP: dict[str, tuple[type[TokenizerBase], dict[str, str]]] = {
    "o200k_base":   (TiktokenTokenizer,     {"encoding_name": "o200k_base"}),
    "cl100k_base":  (TiktokenTokenizer,     {"encoding_name": "cl100k_base"}),
    "llama3":       (HfTokenizer,           {"repo_id": "meta-llama/Llama-3.1-8B"}),
    "qwen":         (HfTokenizer,           {"repo_id": "Qwen/Qwen2.5-7B"}),
    "deepseek_v4":  (HfTokenizer,           {"repo_id": "deepseek-ai/DeepSeek-V3"}),
    "glm":          (HfTokenizer,           {"repo_id": "THUDM/glm-4-9b"}),
    "gemma":        (SentencePieceTokenizer,{"model_name_or_path": "google/gemma-3-4b-it"}),
    "mistral":      (MistralTokenizer,      {"model_name": "mistral-large"}),
}
```

### 5.3 group_id 到 display_name 的映射

用于 `TokenizerBase.name` 属性的默认值：

```python
_DISPLAY_NAMES: dict[str, str] = {
    "o200k_base":   "OpenAI (o200k_base)",
    "cl100k_base":  "OpenAI Legacy (cl100k_base)",
    "llama3":       "Meta Llama 3",
    "qwen":         "Alibaba Qwen 2.5",
    "deepseek_v4":  "DeepSeek V4",
    "glm":          "Zhipu GLM-4",
    "gemma":        "Google Gemma 3",
    "mistral":      "Mistral AI",
}
```

---

## 6. 分词器注册表

### 6.1 文件位置

`src/token_calculator/tokenizers/_registry.py`

### 6.2 工厂模式 + 懒加载 + 缓存

```
                         TokenizerRegistry（单例模式）
                         ┌──────────────────────────────────────┐
                         │  _cache: dict[str, TokenizerBase]    │
                         │  _init_lock: Lock                    │
                         │                                      │
                         │  get_tokenizer(group_id)             │
                         │  count_tokens_batch(text, groups)    │
                         └──────────────────────────────────────┘
                                    │
                    ┌───────────────┼───────────────────┐
                    ▼               ▼                   ▼
             ┌──────────────┐ ┌──────────────┐   ┌──────────────┐
             │ group_id 1   │ │ group_id 2   │   │ group_id 3   │
             │ TiktokenTok  │ │ HfTokenizer  │   │ MistralTok   │
             │ (cached)     │ │ (cached)     │   │ (cached)     │
             └──────────────┘ └──────────────┘   └──────────────┘
```

**懒加载流程**：

```
调用 get_tokenizer("llama3")
  │
  ├── _cache 中已有 "llama3"？ → 直接从缓存返回
  │
  ├── 缓存未命中：
  │     │
  │     ├── _TOKENIZER_MAP.get("llama3")
  │     │     → (HfTokenizer, {"repo_id": "meta-llama/Llama-3.1-8B"})
  │     │
  │     ├── instance = HfTokenizer(group_id="llama3", **kwargs)
  │     │
  │     ├── instance.initialize()     # 尝试加载
  │     │
  │     └── _cache["llama3"] = instance  # 无论成功/失败，都缓存
  │
  └── 返回 instance
```

### 6.3 缓存策略

| 缓存类别 | 缓存键 | 缓存内容 | 缓存时机 | 缓存失效 |
|---|---|---|---|---|
| Tokenizer 实例 | `group_id` | TokenizerBase 子类实例 | 首次 `get_tokenizer()` | 应用重启（不做动态重载） |
| 失败实例 | `group_id` | available=False 的实例 | `initialize()` 失败后 | 应用重启 |

**关键决策 D2 的实践**：缓存失败实例防止每次请求都重试下载。这意味着：

1. 首次请求 `llama3` 时，如果网络不通，`initialize()` 失败，`available=False`
2. 实例被缓存到 `_cache["llama3"]`
3. 后续所有对 `llama3` 的请求直接返回 `available=False` 的实例
4. 直到应用重启，才会再次尝试初始化

### 6.4 count_tokens_batch 实现

```python
def count_tokens_batch(
    self,
    text: str,
    group_ids: list[str],
) -> dict[str, int]:
    """对同一段文本按多个 group_id 分别计数。

    返回: {group_id: token_count}
    如果某个分词器不可用，该 group_id 对应的值为 -1。
    """
    result: dict[str, int] = {}
    for gid in group_ids:
        tokenizer = self.get_tokenizer(gid)
        if tokenizer is None or not tokenizer.available:
            result[gid] = -1
        else:
            try:
                result[gid] = tokenizer.count_tokens(text)
            except TokenizationError:
                result[gid] = -1
    return result
```

> **关于 D4（非并行）**：8 个分组以内，逐个计数总时间通常 < 1 秒。如果未来分组数量超过 15 或单个 tokenizer 加载时间过长，可升级为 `concurrent.futures.ThreadPoolExecutor`。

### 6.5 单例模式

`TokenizerRegistry` 在模块级别实例化，应用启动时只创建一个注册表：

```python
# 模块底部（_registry.py）
_registry: TokenizerRegistry | None = None


def get_registry() -> TokenizerRegistry:
    """获取全局唯一的 TokenizerRegistry 实例。"""
    global _registry
    if _registry is None:
        _registry = TokenizerRegistry()
    return _registry
```

`_app.py` 通过 `from token_calculator.tokenizers._registry import get_registry` 获取注册表。

### 6.6 与 estimate_tokens() 的互操作

当 tokenizer 不可用时，`_app.py` 应该回退到 `estimate_tokens()`（字符估算法），而不是直接返回错误。回退逻辑见 [第 11 章降级与回退](#11-降级与回退)。

---

## 7. 后端 API 集成

### 7.1 _models.py 变更

**文件**: `src/token_calculator/_models.py`

**变更 1**: TokenizeResult 新增 `char_count` 字段

```python
class TokenizeResult(BaseModel):
    group_id: str
    model_name: str
    tokens: int
    cost_usd: float
    available: bool = True
    char_count: int = 0           # [新增] 输入文本的字符数（每个 result 都带）
```

> **设计说明**：`TokenizeResponse` 已有顶层的 `char_count` 字段。在 `TokenizeResult` 中冗余增加 `char_count` 是为了让前端渲染多模型对比表时无需从父级响应中匹配字符数。前端可直接遍历 `results` 数组渲染表格。

**变更 2**（不需要）注意：当前 `_models.py` 中已有的 `TokenizeRequest`、`TokenizeResponse`、`CompressionResult` 等模型保持不动。

### 7.2 _app.py 变更

**文件**: `src/token_calculator/_app.py`

#### 7.2.1 新增 import

```python
# 在文件顶部新增
from token_calculator.tokenizers._registry import get_registry
from token_calculator.tokenizers._base import TokenizerError, InitializationError
```

#### 7.2.2 修改 POST /api/tokenize

**当前实现**（第 118-139 行）：

```python
@app.post("/api/tokenize", response_model=TokenizeResponse)
def tokenize(request: TokenizeRequest):
    char_count = len(request.text)
    results: list[TokenizeResult] = []

    for group_id in request.group_ids:
        model_name = registry.get_representative(group_id)
        if model_name is None:
            raise HTTPException(
                status_code=404,
                detail=f"Unknown group_id: '{group_id}'. ...",
            )
        tokens = estimate_tokens(request.text)  # ← 替换此行
        pricing = registry.get_pricing(model_name)
        cost = _compute_token_cost(tokens, request.mode, pricing)
        results.append(TokenizeResult(
            group_id=group_id, model_name=model_name,
            tokens=tokens, cost_usd=cost, available=True,
        ))

    return TokenizeResponse(char_count=char_count, results=results)
```

**替换为**：

```python
@app.post("/api/tokenize", response_model=TokenizeResponse)
def tokenize(request: TokenizeRequest):
    char_count = len(request.text)
    results: list[TokenizeResult] = []

    token_registry = get_registry()
    batch_result = token_registry.count_tokens_batch(
        request.text, request.group_ids,
    )

    for group_id in request.group_ids:
        model_name = registry.get_representative(group_id)
        if model_name is None:
            raise HTTPException(
                status_code=404,
                detail=f"Unknown group_id: '{group_id}'. "
                       f"Available: {list(g['group_id'] for g in registry.get_groups())}",
            )

        token_count = batch_result.get(group_id, -1)
        available = token_count >= 0

        # 回退：如果 tokenizer 不可用，使用字符估算法
        if not available:
            token_count = estimate_tokens(request.text)
            available = False

        pricing = registry.get_pricing(model_name)
        cost = _compute_token_cost(token_count, request.mode, pricing)

        results.append(TokenizeResult(
            group_id=group_id,
            model_name=model_name,
            tokens=token_count,
            cost_usd=cost,
            available=available,
            char_count=char_count,
        ))

    return TokenizeResponse(char_count=char_count, results=results)
```

#### 7.2.3 修改 POST /api/compress

**当前实现**（第 145-161 行）：

```python
@app.post("/api/compress", response_model=CompressionResult)
def compress(request: CompressRequest):
    text = request.text
    tokens = estimate_tokens(text)
    return CompressionResult(
        strategy=request.strategy.value,
        original_text=text,
        compressed_text=text,
        original_tokens={"o200k_base": tokens},
        compressed_tokens={"o200k_base": tokens},
        savings={...},
        changes=[],
    )
```

**替换为**：

```python
@app.post("/api/compress", response_model=CompressionResult)
def compress(request: CompressRequest):
    text = request.text
    token_registry = get_registry()

    # 对 o200k_base 和 cl100k_base 做精确计数
    groups_to_count = ["o200k_base", "cl100k_base"]
    batch = token_registry.count_tokens_batch(text, groups_to_count)

    # 如果精确计数不可用，回退到 estimate
    original_tokens = {}
    for gid in groups_to_count:
        count = batch.get(gid, -1)
        if count >= 0:
            original_tokens[gid] = count
        else:
            original_tokens[gid] = estimate_tokens(text)

    return CompressionResult(
        strategy=request.strategy.value,
        original_text=text,
        compressed_text=text,
        original_tokens=original_tokens,
        compressed_tokens=original_tokens,  # 压缩尚未实现
        savings={
            "tokens_saved": 0,
            "percentage": 0.0,
            "estimated_monthly_savings_usd": 0.0,
        },
        changes=[],
    )
```

#### 7.2.4 异常处理（新增）

在 `create_app()` 内部添加全局异常处理器：

```python
@app.exception_handler(TokenizerError)
def tokenizer_error_handler(request, exc: TokenizerError):
    return JSONResponse(
        status_code=503,
        content={
            "error": True,
            "code": "TOKENIZER_UNAVAILABLE",
            "message": str(exc),
            "detail": {"group_id": exc.group_id},
        },
    )
```

### 7.3 测试端到端流程

实施后的请求/响应示例：

```bash
curl -X POST http://localhost:8000/api/tokenize \
  -H "Content-Type: application/json" \
  -d '{"text": "Hello world", "group_ids": ["o200k_base", "llama3"]}'
```

响应：

```json
{
  "char_count": 11,
  "results": [
    {
      "group_id": "o200k_base",
      "model_name": "GPT-5.6 Luna",
      "tokens": 2,
      "cost_usd": 0.000002,
      "available": true,
      "char_count": 11
    },
    {
      "group_id": "llama3",
      "model_name": "Llama 4 Maverick",
      "tokens": 4,
      "cost_usd": 0.00000108,
      "available": true,
      "char_count": 11
    }
  ]
}
```

---

## 8. 前端集成

### 8.1 实时字符预览（保留 estimateTokens）

前端现有的实时预览功能 `estimateTokens()` 基于字符估算法快速刷新 token 估算值，当用户打字时实时显示。此功能应 **保留不动**，因为：

- **响应速度**：`POST /api/tokenize` 涉及网络往返，不适合按键级实时预览
- **精确触达**：只有当用户点击"刷新精确计数"按钮或切换到面板 3 时，才调用 `POST /api/tokenize`
- **相互补充**：估算值提供"感觉"，精确值提供"确认"

### 8.2 在 runCompression 中调用 POST /api/tokenize

当前 `runCompression()` 仅调用 `POST /api/compress`。实施后，应在压缩完成后调用 `POST /api/tokenize` 获取精确 token 数。

```javascript
// 压缩后获取精确 token 数
async function runCompression() {
    const compressResult = await fetch("/api/compress", { ... });

    // [新增] 获取精确 token 计数
    const tokenizeResponse = await fetch("/api/tokenize", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            text: compressResult.compressed_text,
            group_ids: ["o200k_base", "cl100k_base"],
        }),
    });
    const tokenData = await tokenizeResponse.json();

    // 更新 UI 展示
    renderComparisonTable(compressResult, tokenData);
}
```

### 8.3 多模型对比表优化

当前面板 3 的对比表会请求所有 8 个分组。优化点：

1. **默认只请求 o200k_base + cl100k_base**（最常用的两个分组）的速度优化
2. **展开"对比更多模型"时再加载其余分组**
3. **不可用分组的行显示为灰色**（`available=false`），值显示 `"-"` 而非 `"-1"`
4. **显示标注**：如果某个 token 值来自估算而非精确计数，在对应单元格显示 `*` 角标，表尾注明 `"* = 字符估算法（分词器暂不可用）"`

### 8.4 前端数据流变化

```
实施前：
用户打字 → estimateTokens() → 前端本地估算 → 显示估算值

实施后：
用户打字 → estimateTokens() → 前端本地估算 → 显示估算值（实时预览）
                                     ↓
用户点击"精确计数" → POST /api/tokenize → 后端精确计数 → 更新精确值（带 available 标记）
                                     ↓
用户点击"压缩" → POST /api/compress → 后端压缩
                → POST /api/tokenize（压缩后文本）→ 精确计数
                → 前后对比表
```

---

## 9. 模型文件下载策略

### 9.1 下载脚本

**文件**: `scripts/download_tokenizers.sh`

```bash
#!/usr/bin/env bash
# Tokenizer 模型文件批量下载脚本
#
# 用途：预下载所有分词器的模型文件，避免首次使用时的下载延迟。
# 运行此脚本后，所有 tokenizer 文件将被缓存到本地，支持离线使用。
#
# 用法: bash scripts/download_tokenizers.sh [--hf-token YOUR_TOKEN]
#
# 选项：
#   --hf-token     HuggingFace 访问令牌（下载门控模型时需要）

set -euo pipefail

MODELS_DIR="models"
HF_TOKEN=""

# 解析参数
while [[ $# -gt 0 ]]; do
    case $1 in
        --hf-token) HF_TOKEN="$2"; shift 2 ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

echo "=== Downloading tokenizer model files ==="
echo ""

# ---------- Gemma (SentencePiece) ----------
echo "[1/1] Gemma (google/gemma-3-4b-it) → models/gemma/"
mkdir -p models/gemma
python3 -c "
from huggingface_hub import hf_hub_download
path = hf_hub_download(
    repo_id='google/gemma-3-4b-it',
    filename='tokenizer.model',
    local_dir='models/gemma',
    local_dir_use_symlinks=False,
)
print(f'  Downloaded to: {path}')
"

echo ""
echo "=== Done ==="
echo "HuggingFace tokenizers will be auto-cached on first use via transformers."
```

> 注意：HuggingFace transformers 分组的 tokenizer 不需要此脚本主动下载，因为 `from_pretrained()` 会在首次使用时自动从 HuggingFace Hub 下载并缓存到 `~/.cache/huggingface/hub/`。

### 9.2 models/ 目录结构

```
models/
├── gemma/
│   └── tokenizer.model     # ~5-10 MB, Gemma 3 SentencePiece 模型文件
└── .gitkeep                # 保持目录在 Git 中
```

### 9.3 HuggingFace 认证

**为什么需要认证**：只有 `llama3` 分组（`meta-llama/Llama-3.1-8B`）是门控模型。

**认证方式**：

```bash
# 方式 1：huggingface-cli login（交互式）
huggingface-cli login

# 方式 2：环境变量（适合 CI/无交互环境）
export HF_TOKEN=hf_your_token_here
```

**如果未认证**：

| 分组 | 影响 | 降级行为 |
|---|---|---|
| llama3 | 无法下载 tokenizer.json | available=false，回退到 estimate_tokens |
| qwen | 无影响（公开仓库） | 正常 |
| deepseek_v4 | 无影响（公开仓库） | 正常 |
| glm | 无影响（公开仓库） | 正常 |
| 其余分组 | 不涉及 HuggingFace | 正常 |

### 9.4 预期文件大小与下载时间

| 文件 | 大小 | 下载时间（典型） | 来源 |
|---|---|---|---|
| `models/gemma/tokenizer.model` | ~5-10 MB | 2-5 秒 | 脚本下载 |
| `~/.cache/huggingface/hub/llama3-tokenizer` | ~2-5 MB | 2-5 秒 | 自动缓存 |
| `~/.cache/huggingface/hub/qwen-tokenizer` | ~5-10 MB | 3-8 秒 | 自动缓存 |
| `~/.cache/huggingface/hub/deepseek-tokenizer` | ~5-10 MB | 3-8 秒 | 自动缓存 |
| `~/.cache/huggingface/hub/glm-tokenizer` | ~2-5 MB | 2-5 秒 | 自动缓存 |
| tiktoken 内置词表 | 与应用安装包集成 | 0（无需下载） | pip install |
| mistral-common 内置词表 | 与应用安装包集成 | 0（无需下载） | pip install |

### 9.5 下载状态检查

启动时（在 `create_app()` 中）可快速检查关键文件是否存在，避免运行时才发现缺失：

```python
def _check_tokenizer_files():
    """启动时检查关键模型文件是否存在（仅检查，不加载）。"""
    issues = []
    if not Path("models/gemma/tokenizer.model").is_file():
        issues.append("Gemma: models/gemma/tokenizer.model not found")
    if issues:
        logger.warning("Tokenizer model files missing. Run scripts/download_tokenizers.sh")
        for issue in issues:
            logger.warning(f"  - {issue}")
```

---

## 10. 依赖管理

### 10.1 pyproject.toml 变更

```toml
[project]
dependencies = [
    "fastapi>=0.110",
]

[project.optional-dependencies]
server = ["uvicorn>=0.29"]

# [新增] 分词器依赖组
tokenizers-tiktoken = [
    "tiktoken>=0.7",
]
tokenizers-transformers = [
    "transformers>=4.48",
]
tokenizers-sentencepiece = [
    "sentencepiece>=0.2",
    "huggingface-hub>=0.24",    # 用于自动下载 .model 文件
]
tokenizers-mistral = [
    "mistral-common>=1.4",
]

# [新增] 全量安装快捷方式
tokenizers-all = [
    "token-calculator[tokenizers-tiktoken]",
    "token-calculator[tokenizers-transformers]",
    "token-calculator[tokenizers-sentencepiece]",
    "token-calculator[tokenizers-mistral]",
]
```

### 10.2 每个依赖的合理性

| 依赖 | 用于 | 大小 | 是否必需 | 替代方案 |
|---|---|---|---|---|
| `tiktoken` | OpenAI 系列分词 | ~2 MB（纯 Python） | 推荐（2 个分组） | 官方库，无替代 |
| `transformers` | HuggingFace 分词器 | ~50 MB（含 tokenizers 库） | 推荐（4 个分组） | 直接使用 tokenizers 库（更低级） |
| `sentencepiece` | Google Gemma 分词 | ~5 MB（C++ 扩展） | 推荐（1 个分组） | transformers 也可加载 SP 模型 |
| `huggingface-hub` | 自动下载 SP .model | ~1 MB（纯 Python） | 推荐 | 手动下载 |
| `mistral-common` | Mistral 分词 | ~10 MB（含内置词表） | 推荐（1 个分组） | 直接使用 sentencepiece |

### 10.3 为什么不需要 PyTorch

**重要澄清**：HfTokenizer 使用 HuggingFace 的 `AutoTokenizer.from_pretrained(..., use_fast=True)`，这只需要 `tokenizers` 库的 Rust 绑定，不需要 PyTorch、TensorFlow 或 Flax。

```
transformers 安装内容：
├── tokenizers（Rust → .whl）     ← 分词器加速需要
├── transformers Python 代码      ← 接口需要
├── PyTorch/TensorFlow/Flax       ← NOT NEEDED（加载模型权重时才需要）
└── 其他辅助库                    ← 部分需要
```

验证方法：

```bash
# 只安装 transformers（不含 PyTorch）
pip install transformers --no-deps
pip install tokenizers

# 测试分词器加载
python -c "
from transformers import AutoTokenizer
tok = AutoTokenizer.from_pretrained('Qwen/Qwen2.5-7B', use_fast=True)
print(tok.encode('Hello world'))
"
# 正常运行，不报 ImportError: torch
```

### 10.4 安装建议

开发者在本地开发时安装全量依赖：

```bash
pip install -e ".[tokenizers-all]"
```

或者只安装需要的分组：

```bash
# 最低依赖（仅 OpenAI 系列）
pip install -e ".[tokenizers-tiktoken]"

# 标准依赖（除 LLM 压缩外全部支持）
pip install -e ".[tokenizers-tiktoken,tokenizers-transformers,tokenizers-mistral]"
```

---

## 11. 降级与回退

### 11.1 降级触发条件

| 条件 | 影响分组 | 表现 |
|---|---|---|
| tiktoken 未安装 | o200k_base, cl100k_base | available=false |
| transformers 未安装 | llama3, qwen, deepseek_v4, glm | available=false |
| sentencepiece 未安装 | gemma | available=false |
| mistral-common 未安装 | mistral | available=false |
| 网络不可用 + 缓存未命中 | HfTokenizer 四个分组 | available=false |
| 门控模型未认证 | llama3 | available=false |
| .model 文件缺失 + 不可下载 | gemma | available=false |

### 11.2 available=false 时的行为层次

```
可用 → 1. 基础依赖已安装
      2. 模型文件已缓存/下载
      3. initialize() 成功

不可用 → A. 依赖缺失
       → B. 文件缺失
       → C. 网络故障
       → D. 认证失败

分层响应：

                     tokenizer.available?
                           │
                    ┌──────┴──────┐
                    ▼              ▼
                  True            False
                    │               │
                    ▼               ▼
            count_tokens()     estimate_tokens()
            （精确计数）         （字符估算法）
                    │               │
                    ▼               ▼
            available=true     available=false
            tokens=N            tokens=estimated
```

### 11.3 前端显示逻辑

| available | JSON 中的值 | 前端显示 |
|---|---|---|
| `true` | `tokens: 42`, `available: true` | "42"（正常绿色数字） |
| `false` | `tokens: 42`, `available: false` | "42 \*"（带灰色角标，table 脚注注明为估算值） |
| `false`（严重降级） | `tokens: -1`, `available: false` | "—"（不可用，灰色） |

### 11.4 估算与精确的对比

| 维度 | estimate_tokens (回退) | count_tokens (精确) |
|---|---|---|
| 算法 | `max(1, int(len(text) * 0.25))` | 使用真实分词器编码 |
| 速度 | < 0.01 ms | < 5 ms（大部分情况） |
| 精度 | 粗估（误差可达 50%+） | 精确 |
| 网络依赖 | 无 | HfTokenizer 首次需要 |
| 依赖 | 无（内置纯 Python） | 需安装对应库 |

### 11.5 回退链路

```
_app.py: tokenize()
  → get_tokenizer(group_id)
    → 实例 available=True？ → 精确计数
    → 实例 available=False？ → 走 estimate_tokens()
```

注意：即使 `available=False`，`_app.py` 仍设置 `available=False` 返回给前端，让前端知道该值是估算而非精确。这比直接返回错误更友好：用户至少看到一个数字。

---

## 12. 测试计划

### 12.1 单元测试

#### 12.1.1 TokenizerBase 基类（test_base.py）

| 测试用例 | 预期 | 优先级 |
|---|---|---|
| 抽象类不能直接实例化 | `TypeError` | P0 |
| 空字符串 count_tokens 返回 0 | `0` | P0 |
| 空字符串 encode 返回空列表 | `[]` | P0 |
| 空列表 decode 返回空字符串 | `""` | P0 |

#### 12.1.2 TiktokenTokenizer（test_tiktoken.py）

| 测试用例 | 预期 | 优先级 |
|---|---|---|
| o200k_base 初始化成功 | `available=True` | P0 |
| cl100k_base 初始化成功 | `available=True` | P0 |
| o200k_base count_tokens("Hello world") | `2` | P0 |
| cl100k_base count_tokens("Hello world") | `2` | P0 |
| o200k_base count_tokens("") | `0` | P0 |
| o200k_base encode 后 decode 往返一致 | `decode(encode(t)) == t` | P0 |
| 前后两次 count_tokens 同一文本返回相同值 | 幂等 | P1 |
| 未知 encoding 名初始化失败 | `available=False` | P1 |

#### 12.1.3 HfTokenizer（test_hf.py）

| 测试用例 | 预期 | 优先级 |
|---|---|---|
| transformers 未安装时 initialize() 设置 available=False | `available=False` | P0 |
| qwen 分组初始化成功（需网络/缓存） | `available=True` | P0 |
| qwen count_tokens("") | `0` | P0 |
| qwen encode 后 decode 往返一致 | `decode(encode(t)) == t` | P1 |
| 调用两次 initialize() 是幂等的 | 第二次为 no-op | P1 |

> 测试门控模型（llama3）需要 HF 认证，CI 中可能需要跳过。使用 `pytest.mark.skipif` 标记。

#### 12.1.4 SentencePieceTokenizer（test_sentencepiece.py）

| 测试用例 | 预期 | 优先级 |
|---|---|---|
| sentencepiece 未安装时 initialize() 设置 available=False | `available=False` | P0 |
| .model 文件存在时初始化成功 | `available=True` | P0 |
| .model 文件不存在时初始化失败 | `available=False` | P1 |
| count_tokens("") | `0` | P0 |
| encode 后 decode 往返一致 | `decode(encode(t)) == t` | P1 |

#### 12.1.5 MistralTokenizer（test_mistral.py）

| 测试用例 | 预期 | 优先级 |
|---|---|---|
| mistral-common 未安装时 initialize() 设置 available=False | `available=False` | P0 |
| mistral-large 初始化成功（本地内置） | `available=True` | P0 |
| count_tokens("") | `0` | P0 |
| encode 后 decode 往返一致 | `decode(encode(t)) == t` | P1 |

#### 12.1.6 TokenizerRegistry（test_registry.py）

| 测试用例 | 预期 | 优先级 |
|---|---|---|
| get_tokenizer 返回正确类型实例 | o200k_base → TiktokenTokenizer | P0 |
| 两次 get_tokenizer 同一 group_id 返回同一个实例 | `is` 比较为 True | P0 |
| count_tokens_batch 返回正确 | 数量与 group_ids 一致 | P0 |
| count_tokens_batch 含未知 group_id | 抛出 KeyError | P1 |
| 未知 group_id | `get_tokenizer()` 返回 None | P0 |
| 不可用分词器返回 -1 | `count_tokens_batch` 中值为 -1 | P1 |

### 12.2 集成测试

#### 12.2.1 API 集成（test_e2e.py）

| 测试用例 | 端点 | 预期 | 优先级 |
|---|---|---|---|
| 请求支持的分词器 | `POST /api/tokenize` | 200, results 含精确 tokens | P0 |
| 请求不可用分词器 | `POST /api/tokenize` | 200, available=false, tokens 使用估算 | P0 |
| 请求空文本 | `POST /api/tokenize` | 422 (Pydantic 校验) | P0 |
| 请求多种模式 | `POST /api/tokenize` | 正常 | P1 |
| 压缩后精确计数 | `POST /api/compress` | 200, original_tokens 含精确值 | P1 |

#### 12.2.2 已知参考值（用于断言验证）

确保 token 计数器返回已知的精确值。以下为部分分组已确认的参考值：

| 文本 | 分组 | 预期 token 数 | 备注 |
|---|---|---|---|
| `"Hello world"` | o200k_base | 2 | 已通过 tiktoken 独立验证 |
| `"Hello world"` | cl100k_base | 2 | 已通过 tiktoken 独立验证 |
| `""` | 任意 | 0 | 统一边界约定 |

其他分组的参考值留空（在实施阶段填入）。

### 12.3 回退测试

| 测试用例 | 模拟条件 | 预期 | 优先级 |
|---|---|---|---|
| tiktoken 未安装 | mock/移除 tiktoken import | o200k_base behave 如 available=false | P1 |
| transformers 未安装 | mock/移除 transformers import | llama3 behave 如 available=false | P1 |
| 网络不可用 | mock from_pretrained 抛 OSError | HfTokenizer available=false | P1 |
| .model 文件缺失 | 删除 models/gemma/ 文件 | gemma available=false | P1 |

### 12.4 测试文件结构

```
tests/
├── tokenizers/
│   ├── __init__.py
│   ├── test_base.py
│   ├── test_tiktoken.py
│   ├── test_hf.py
│   ├── test_sentencepiece.py
│   ├── test_mistral.py
│   └── test_registry.py
├── test_e2e.py          # [修改] 新增 tokenizer 集成测试
└── conftest.py
```

### 12.5 测试运行方式

```bash
# 运行所有 tokenizer 测试
pytest tests/tokenizers/ -v

# 运行特定分组测试
pytest tests/tokenizers/test_tiktoken.py -v

# 运行集成测试
pytest tests/test_e2e.py -v -k "tokenize"

# 跳过需要网络的测试
pytest tests/tokenizers/ -v -m "not network"
```

---

## 13. 实施顺序

### 13.1 阶段划分概览

```
Phase 1A (基础)     Phase 1B (核心)        Phase 1C (集成)       Phase 1D (完善)
──────────────      ──────────────         ──────────────        ──────────────
_tokenizer.py       _hf.py                 _app.py 修改          下载脚本
__init__.py         _sentencepiece.py      _models.py 修改       文档更新
_registry.py        _mistral.py            端到端测试             CI 集成
_tiktoken.py        单元测试
                    test 参考值
```

### 13.2 阶段 1A：基础架构（预计 0.5 天）

**目标**：抽象基类 + 注册表 + tiktoken（最稳定、最无依赖的分组）完成可用。

**文件产出**：
- `_base.py` — TokenizerBase, TokenizerError, InitializationError, TokenizationError
- `__init__.py` — 导出所有公共符号
- `_registry.py` — TokenizerRegistry, 工厂映射, get_registry, 懒加载+缓存
- `_tiktoken.py` — TiktokenTokenizer 实现

**可交付验收条件**：
- [ ] `TiktokenTokenizer("o200k_base").count_tokens("Hello world")` 返回 2
- [ ] `get_registry().count_tokens_batch("Hi", ["o200k_base", "cl100k_base"])` 返回 `{"o200k_base": 1, "cl100k_base": 1}`
- [ ] 空字符串返回 0
- [ ] 单元测试全部通过

**不依赖什么**：本阶段不依赖任何外部网络或文件；tiktoken 纯本地。

### 13.3 阶段 1B：核心实现（预计 1.5 天）

**目标**：HfTokenizer, SentencePieceTokenizer, MistralTokenizer 全部实现并可用。

**文件产出**：
- `_hf.py` — HfTokenizer
- `_sentencepiece.py` — SentencePieceTokenizer
- `_mistral.py` — MistralTokenizer

**子阶段顺序**（可按依赖顺序并行推进）：

1. **MistralTokenizer**（无网络依赖，最干净）
   - 依赖：`pip install mistral-common`
   - 验证：`count_tokens("Hello")` 返回预期值

2. **SentencePieceTokenizer**（需要下载 .model 文件）
   - 依赖：`pip install sentencepiece`, 运行下载脚本或 `huggingface_hub` 自动下载
   - 验证：本地 .model 文件存在时返回精确值

3. **HfTokenizer**（涉及网络和缓存，最复杂）
   - 依赖：`pip install transformers`
   - 先实现公开仓库（qwen, deepseek_v4, glm），最后实现门控模型（llama3）
   - 验证：公开分组离线可用（缓存命中后）

**可交付验收条件**：
- [ ] 所有 8 个分组的 `initialize()` 可通过（或优雅降级）
- [ ] 每个分组至少一个测试参考值已填入测试文件
- [ ] encode-decode 往返一致性验证通过
- [ ] 验证 GLM 的 `trust_remote_code=True` 工作正常
- [ ] Llama 3 门控模型认证失败时优雅降级（不崩溃，不卡死）

### 13.4 阶段 1C：后端集成（预计 0.5 天）

**目标**：API 层替换估算值调用，端到端可用。

**文件产出**：
- 修改 `_app.py`
- 修改 `_models.py`
- 修改 `test_e2e.py`

**关键步骤**：

1. **修改 _models.py** — TokenizeResult 新增 `char_count` 字段
2. **修改 _app.py** — 替换 `estimate_tokens()` 调用为 `count_tokens_batch()`
3. **修改 POST /api/compress** — 集成精确 token 计数
4. **添加全局异常处理器** — TokenizerError → HTTP 503
5. **修改 test_e2e.py** — 增加精确 token 计数的集成测试
6. **手动端到端验证**：

```bash
# 启动服务
uvicorn src.token_calculator._app:create_app --factory

# 验证精确计数
curl -X POST http://localhost:8000/api/tokenize \
  -H "Content-Type: application/json" \
  -d '{"text": "Hello", "group_ids": ["o200k_base"]}'
# 预期: {"char_count":5, "results":[{"group_id":"o200k_base","tokens":1,...}]}
```

**可交付验收条件**：
- [ ] `POST /api/tokenize` 对所有已安装依赖的分组返回精确 token 数
- [ ] `POST /api/tokenize` 对未安装依赖的分组返回 `available=false` + 估算值
- [ ] `POST /api/compress` 的 `original_tokens` 包含精确值
- [ ] API 集成测试全部通过

### 13.5 阶段 1D：完善（预计 0.5 天）

**目标**：下载脚本、文档、CI 集成。

**文件产出**：
- `scripts/download_tokenizers.sh`
- 修改 `pyproject.toml`
- 修改 `docs/modules/tokenizer-layer/README.md`

**关键步骤**：

1. **下载脚本** — 完整测试下载流程，包括门控模型认证指引
2. **pyproject.toml** — 添加依赖组，重构现有依赖声明
3. **README.md 更新** — 对齐设计文档与最终实施
4. **CI 集成** — 在 CI 中添加 tokenizer 测试步骤（跳过需要网络/认证的测试）

**可交付验收条件**：
- [ ] `bash scripts/download_tokenizers.sh` 成功下载所有模型文件
- [ ] 离线环境（已缓存）所有可用分组正常工作
- [ ] `pip install -e ".[tokenizers-all]"` 一次性安装所有依赖
- [ ] 设计文档已更新，与代码实现一致
- [ ] CI 中 tokenizer 测试通过

### 13.6 阶段依赖关系图

```
Phase 1A (基础)
  │
  ├──→ Phase 1B.1 (MistralTokenizer)  ──→ Phase 1C (后端集成)
  │                                          │
  ├──→ Phase 1B.2 (SentencePieceTokenizer) ──┤    Phase 1D (完善)
  │                                          │       │
  └──→ Phase 1B.3 (HfTokenizer) ────────────┘       │
                                                     │
              Phase 1C (集成) ───────────────────────┘
```

### 13.7 可立即交付的部分

**Phase 1A 可以立刻开始实施**，因为它只依赖：

- Python 标准库（abc, logging, typing）
- tiktoken（纯 Python，无外部依赖）

不需要等待其他模块或基础设施。

### 13.8 风险与缓解措施

| 风险 | 概率 | 影响 | 缓解措施 |
|---|---|---|---|
| HuggingFace 门控模型认证导致首次用户体验差 | 中 | 中 | 提供清晰的 CLI 指引 + 优雅降级到估算 |
| sentencepiece C++ 扩展在某些环境编译失败 | 低 | 高 | 回退到 transformers 加载 SP 模型（可能） |
| mistral-common API 版本变化 | 中 | 中 | 在测试中冻结 mistral-common 版本，实施前确认 API 签名 |
| transformers 自动安装 PyTorch（虽然不需要） | 中 | 低 | pyproject.toml 严格限制依赖为 transformers 无 PyTorch |
| 缓存膨胀：8 个 tokenizer 同时加载 > 500 MB | 低 | 中 | 懒加载 + 按需初始化；在 README 中标注内存需求 |

---

### 13.9 Gemma 组暂缓

**状态**: 暂缓（DEFERRED）

**原因**: google/gemma-3-4b-it 是 gated HuggingFace 仓库，需要 Google 审核访问申请。
所有非 gated 替代方案均不可用。

**当前行为**: 自动降级为 len*0.25 字符估算。API 返回 available=false。

**恢复条件**: Google 审核通过后，运行 python scripts/download_tokenizers.py 即可。
代码无需任何修改。

**预计时间**: 1-3 个工作日（取决于 Google 审核速度）

---

## 附录 A：实施清单

### A.1 开发者检查清单

```
[ ] 理解设计文档 (tokenizer-layer/README.md)
[ ] 理解模型注册表数据 (_pricing.py)
[ ] 完成 Phase 1A: 基础架构
    [ ] _base.py (TokenizerBase, 异常类)
    [ ] __init__.py (公共符号导出)
    [ ] _registry.py (工厂+缓存+批量接口)
    [ ] _tiktoken.py (TiktokenTokenizer)
    [ ] 测试全部通过
[ ] 完成 Phase 1B: 核心实现
    [ ] _mistral.py (MistralTokenizer)
    [ ] _sentencepiece.py (SentencePieceTokenizer)
    [ ] _hf.py (HfTokenizer)
    [ ] 测试全部通过
[ ] 完成 Phase 1C: 后端集成
    [ ] _models.py 新增 char_count
    [ ] _app.py 替换 estimate_tokens 调用
    [ ] 端到端测试通过
[ ] 完成 Phase 1D: 完善
    [ ] scripts/download_tokenizers.sh
    [ ] pyproject.toml 依赖组
    [ ] README.md 更新
    [ ] CI 集成
```

### A.2 已确认的测试参考值

| 文本 | 分组 | 预期 token | 实施后标注 |
|---|---|---|---|
| `""` | 所有 | 0 | 约定 |
| `"Hello world"` | o200k_base | 2 | 已验证 |
| `"Hello world"` | cl100k_base | 2 | 已验证 |

> 其余参考值待实施时填入。

---

## 实施状态 (2026-07-07)

| 阶段 | 状态 |
|------|------|
| Phase 1A (TokenizerBase + TiktokenTokenizer + Registry) | ✅ 完成 |
| Phase 1B (HfTokenizer + SentencePiece + Mistral) | ✅ 完成 |
| Phase 1C (API集成: /api/tokenize, /api/compress) | ✅ 完成 |
| Phase 1D (下载脚本 + 验证) | ✅ 完成 |
| Gemma (google/gemma-3-4b-it) | 🔶 暂缓 — Google审核中 |
