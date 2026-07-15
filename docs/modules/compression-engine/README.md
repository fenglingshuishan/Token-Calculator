# 语义压缩引擎 (Compression Engine)

> **模块标识**: `compression-engine`  
> **版本**: v2.0  
> **对应项目阶段**: Phase 1 (规则引擎 完整实现；LLM 压缩接口预留)  
> **定位**: Prompt 优化工作站的核心创新模块 — 将原始 Prompt 通过两种压缩策略产出精简文本，最大化保留语义的同时减少 token 消耗

---

## 1. 模块概述

### 1.1 为什么需要压缩引擎

大语言模型的输入长度受限且按 token 计费。用户在编写 Prompt 时通常会带入大量冗余表达（敬语、礼貌前缀、口语填充、重复说明），这些内容既不贡献语义又消耗 token 配额。语义压缩引擎的目标是在**不损失核心语义**的前提下，系统性地移除冗余内容。

### 1.2 设计目标

| 目标 | 说明 |
|---|---|
| **语义保真** | 压缩后不丢失任何关键指令、约束条件、示例、输出格式要求 |
| **多策略覆盖** | 提供规则引擎（本地毫秒级）和 LLM 智能压缩（语义级改写）两种策略 |
| **强度可调** | 每策略支持 light / medium / aggressive 三级强度 |
| **变更可追溯** | 每次压缩产出结构化变更日志，支持前端逐条 diff 展示 |
| **即时代价** | 规则引擎全程本地运行，零 API 调用成本，毫秒级响应 |

### 1.3 核心流程

```
原始 Prompt 文本
     │
     ▼
┌─────────────────────────────────────────────┐
│             语义压缩引擎                       │
│                                               │
│  ┌─────────────┐  ┌──────────┐               │
│  │ 规则引擎     │  │ LLM 压缩 │               │
│  │ (毫秒级)    │  │ (语义级) │               │
│  └─────────────┘  └──────────┘               │
│                                               │
│  产出: 压缩后文本 + 变更日志 changes[]        │
└───────────────────────────────────────────────┘
     │
     ▼
压缩后 Prompt → → 送入 → → 分词器层计量 token 节省
```

---

## 2. 压缩策略体系

### 2.1 两种策略总览

| 维度 | RuleCompressor (规则引擎) | LLMCompressor (LLM 压缩) |
|---|---|---|
| **运行位置** | 本地 | 调用外部 API |
| **响应速度** | 毫秒级 | 秒级（取决于 API 延迟） |
| **是否需要 API Key** | 否 | 是 |
| **语义理解能力** | 无（纯模式匹配） | 强（理解上下文语义） |
| **适用场景** | 快速清除冗余/口语/敬语 | 高质量语义级压缩 |
| **Phase 1 状态** | 完整实现 | 接口预留，需配置 API key 方可使用 |

### 2.2 何时用哪种策略

```
用户输入类型                   推荐策略
────────────────────────────────────────────────────
单段中/英文 Prompt (较简短)    → 规则引擎 (light/medium)
单段长 Prompt (>500 token)     → 规则引擎 (aggressive) 或 LLM 压缩
需要最大程度保留语义的场景      → LLM 压缩 (低温度)
需要即时响应、零成本           → 规则引擎 (任意级别)
```

### 2.3 优缺点对比

| 策略 | 优点 | 缺点 |
|---|---|---|
| 规则引擎 | 零延迟、零成本、100% 可预测、结果确定 | 无语义理解、无法处理隐式冗余、规则需持续维护 |
| LLM 压缩 | 压缩质量最高、能理解上下文语义、改写流畅 | 需要 API key、有成本、有延迟、结果非确定 |

---

## 3. CompressorBase 接口

### 3.1 抽象方法

所有压缩器继承统一抽象接口，对外暴露一个核心方法：

- **`compress(request) -> result`**: 接收压缩请求，返回压缩结果

其中 `request` 和 `result` 遵循以下数据结构定义。

### 3.2 请求数据结构 (CompressionRequest)

| 字段 | 类型 | 必填 | 适用策略 | 说明 |
|---|---|---|---|---|
| `text` | string | 是 | 全部 | 待压缩的原始文本 |
| `strategy` | enum | 是 | 全部 | `"rule"` / `"llm"` |
| `level` | enum | 否 (默认 `"medium"`) | 全部 | `"light"` / `"medium"` / `"aggressive"` |
| `target_ratio` | float | 否 | 仅 `llm` | 目标压缩率，例如 `0.4` 表示减少 40% token |
| `llm_config` | object | 否 | 仅 `llm` | LLM 配置，详见第5节 |

**请求示例 (rule, medium):**

```json
{
  "text": "能否请您帮我看一下这个数据集的分析结果？因为我觉得它里面可能有一些异常值需要处理。",
  "strategy": "rule",
  "level": "medium"
}
```

### 3.3 响应数据结构 (CompressionResult)

| 字段 | 类型 | 说明 |
|---|---|---|
| `original_text` | string | 原始文本（回传） |
| `compressed_text` | string | 压缩后文本 |
| `strategy` | string | 实际使用的策略 |
| `level` | string | 实际使用的强度级别 |
| `changes` | array | 变更日志数组，每项描述一次替换操作 |
| `stats` | object | 压缩统计信息 |

**`stats` 子字段:**

| 字段 | 类型 | 说明 |
|---|---|---|
| `original_chars` | int | 原始字符数 |
| `compressed_chars` | int | 压缩后字符数 |
| `original_tokens_estimate` | int | 基于模型注册表默认分词器的预估原始 token 数 |
| `compressed_tokens_estimate` | int | 基于同一分词器的预估压缩后 token 数 |
| `operations_count` | int | 变更操作数量 (changes 数组长度) |

**响应示例:**

```json
{
  "original_text": "能否请您帮我看一下这个数据集的分析结果？",
  "compressed_text": "看此数据集的分析结果",
  "strategy": "rule",
  "level": "medium",
  "changes": [
    {"rule_id": "polite_prefix", "original": "能否请您帮我看一下", "replaced": "看", "position": [0, 9]},
    {"rule_id": "filler_cn", "original": "这个", "replaced": "此", "position": [9, 11]}
  ],
  "stats": {
    "original_chars": 18,
    "compressed_chars": 8,
    "original_tokens_estimate": 12,
    "compressed_tokens_estimate": 4,
    "operations_count": 2
  }
}
```

### 3.4 两种压缩器各自的接口变体

| 压缩器 | compress() 内部行为 |
|---|---|
| `RuleCompressor` | 按 level 选择规则集合，逐规则匹配替换，收集 changes |
| `LLMCompressor` | 请求外部 LLM API，回传结果；无 API key 时返回原文 + 提示信息 |

---

## 4. 规则引擎详细设计

### 4.1 规则引擎工作流程

```
原始文本
   │
   ▼
┌─────────────────────────────────┐
│  1. 代码块保护                  │
│     识别 ```fence``` 并暂存     │
└─────────────────────────────────┘
   │
   ▼
┌─────────────────────────────────┐
│  2. 按强度级别加载规则列表      │
│     Level 1: 基础规则集         │
│     Level 2: + 中级规则集       │
│     Level 3: + 高级规则集       │
└─────────────────────────────────┘
   │
   ▼
┌─────────────────────────────────┐
│  3. 逐条规则匹配 + 替换         │
│     每条规则生成一条 change     │
└─────────────────────────────────┘
   │
   ▼
┌─────────────────────────────────┐
│  4. 恢复代码块内容              │
│  5. 输出压缩后文本 + changes[]  │
└─────────────────────────────────┘
```

### 4.2 规则总览

规则引擎共维护 **32 条规则**，分为三组：中文规则 15 条、英文规则 12 条、通用规则 5 条。每条规则具有以下属性：

| 属性 | 说明 |
|---|---|
| `rule_id` | 规则唯一标识，如 `redundant_honorific` |
| `category` | 规则分组：`cn` / `en` / `universal` |
| `pattern` | 匹配模式（正则或字符串模式） |
| `replacement` | 替换内容（空字符串 = 删除） |
| `min_level` | 该规则生效的最低强度级别：`light` / `medium` / `aggressive` |
| `description` | 规则说明 |

### 4.3 中文规则（15 条）

每条规则标注其 `min_level`：L1 = light, L2 = medium, L3 = aggressive。

| # | rule_id | 说明 | 匹配模式描述 | 替换 | Before | After | 级别 |
|---|---|---|---|---|---|---|---|
| 1 | `cn_redundant_honorific` | 冗余敬语：去除中文敬语中的"请"、"麻烦"等 | 匹配 `请(帮我\|你)\|麻烦你(帮我)\|劳烦` 等模式 | 删除或保留核心动词 | "请你帮我分析一下" | "分析" | L3 |
| 2 | `cn_polite_prefix` | 礼貌前缀：去除"能否"、"可以"、"能麻烦您"等 | 匹配 `能否(请您)?\|可以(帮\|告诉)\|能麻烦(您\|你)` | 删除 | "能否请您帮我" | "帮我" | L3 |
| 3 | `cn_redundant_modifier` | 冗余修饰词：去掉"非常"、"十分"、"特别"、"极其"等程度修饰 | 匹配 `(非常\|十分\|特别\|极其\|相当\|很)` | 删除 | "非常重要" | "重要" | L2 |
| 4 | `cn_filler_word` | 口语填充词：去除"那个"、"就是说"、"然后呢"、"对吧"、"嗯"、"这个" | 匹配 `那个\|就是说\|然后呢\|对吧\|所以说\|那么\|实际上\|基本上` | 删除 | "那个，就是说，这个数据" | "数据" | L2 |
| 5 | `cn_repeated_punctuation` | 重复标点：合并连续重复标点 | 匹配 `[。！？,!?]{2,}` | 单个标点 | "好的！！" | "好的！" | L1 |
| 6 | `cn_excessive_whitespace` | 多余空白：多个连续空行合并为 2 个 | 匹配 `\n{3,}` | `\n\n` | "a\n\n\nb" | "a\n\nb" | L1 |
| 7 | `cn_redundant_conjunction` | 冗余连词：去除不必要的中文连词 | 匹配 `而且\|并且\|此外\|另外\|同时\|以及` 等（当不连接两个必要子句时） | 删除 | "而且这个数据还包含了" | "数据包含了" | L2 |
| 8 | `cn_duplicate_sentence` | 相同句合并：相邻两句语义相似度 >80% 时保留一句 | 通过编辑距离或 n-gram 重叠判断 | 保留前一句 | "请分析这份数据。我需要分析数据。" | "请分析这份数据。" | L2 |
| 9 | `cn_instruction_merge` | 指令合并：多个简短指令合并为一句 | 匹配连续的 `\n-` 或 `\d\.` 开头的多项，合并为逗号分隔 | 合并 | "- 分析数据\n- 生成报告\n- 发送邮件" | "分析数据、生成报告、发送邮件" | L3 |
| 10 | `cn_example_condense` | 示例收束：多个示例保留 1-2 个代表性示例 | 检测"例如/比如/譬如"后的列举项，截断至 2 项 | 保留前 2 项 + "等" | "例如 A、B、C、D、E" | "例如 A、B 等" | L3 |
| 11 | `cn_question_suffix` | 冗余问尾：去除"对不对"、"好不好"、"可以吗"等确认问句 | 匹配 `对不对\|好不好\|可以吗\|行不行\|是不是\|对吧` | 删除 | "帮我分析这个，好不好？" | "帮我分析这个。" | L2 |
| 12 | `cn_superlative` | 冗余最高级：去除"最"类表达（非必需处） | 匹配 `最好\|最优秀\|最佳\|最合适` | 替换为更中性表达或删除 | "这是最好的方案" | "这是优选方案" | L3 |
| 13 | `cn_metadiscourse` | 元话语删除：去除"我想说的是"、"需要指出的是"、"值得注意的是" | 匹配 `我想说的是\|需要指出的是\|值得注意的是\|值得一提的是\|大家都知道` | 删除 | "我想说的是，这个数据有问题" | "这个数据有问题" | L2 |
| 14 | `cn_self_correction` | 自我修正：去除"不对"、"说错了"、"更正一下"后面的重复 | 匹配 `不对\|说错了\|更正一下\|哦不对` 后的重复内容 | 仅保留修正后内容 | "帮我分析--不对，帮我总结这个" | "帮我总结这个" | L2 |
| 15 | `cn_hedging` | 模糊限定词：去除"可能"、"大概"、"似乎"（当非必要时） | 匹配 `可能\|大概\|似乎\|也许\|说不定\|或许\|基本上` | 删除（指令句中） | "你大概需要分析以下数据" | "分析以下数据" | L3 |

### 4.4 英文规则（12 条）

| # | rule_id | 说明 | 匹配模式描述 | 替换 | Before | After | 级别 |
|---|---|---|---|---|---|---|---|
| 1 | `en_polite_request` | 礼貌请求：去除 "Could you please"、"Would you mind" 等 | 匹配 `(C\|c)ould you (please )?\|(W\|w)ould you (please )?\|(W\|w)ould you mind` | 删除，保留后面的动词 | "Could you please help" | "Help" | L3 |
| 2 | `en_redundant_prefix` | 冗余前缀：去除 "I would like you to"、"I want you to" 等 | 匹配 `I (would like you to\|want you to\|need you to\|\'d like you to)` | 删除，保留后面动词 | "I want you to analyze" | "Analyze" | L3 |
| 3 | `en_filler_phrase` | 填充短语：删除 "basically"、"essentially"、"actually"、"really"、"honestly" | 匹配 `\b(basically\|essentially\|actually\|really\|honestly\|literally\|simply\|just)\b` | 删除 | "Basically, we need to" | "We need to" | L2 |
| 4 | `en_redundant_question` | 冗余问句：将 "Can you tell me" 类问题转为直接请求 | 匹配 `Can you tell me (.*?)\?\|Could you tell me (.*?)\?` | `$1?` | "Can you tell me the price?" | "Price?" | L3 |
| 5 | `en_unnecessary_article` | 定冠词省略：在列表项和非必要位置去除 "the" | 匹配 `\bthe\b`（当后接可数复数或抽象概念时） | 删除 | "Analyze the data, the trends, and the outliers" | "Analyze data, trends, and outliers" | L2 |
| 6 | `en_multiple_spaces` | 多余空格：合并连续空格 | 匹配 `\s{2,}`（行内） | 单个空格 | "Analyze  this  data" | "Analyze this data" | L1 |
| 7 | `en_redundant_modifier` | 冗余修饰词：去除 "very"、"extremely"、"incredibly" 等 | 匹配 `\b(very\|extremely\|incredibly\|absolutely\|highly\|quite\|rather)\b` | 删除 | "very important" | "important" | L2 |
| 8 | `en_self_reference` | 自我引用：去除 "I think"、"I believe"、"In my opinion" | 匹配 `I (think\|believe\|feel\|guess)\b\|In my (opinion\|view)\b\|It seems to me that` | 删除 | "I think this approach works" | "This approach works" | L2 |
| 9 | `en_repetition` | 重复词/句：去除相邻重复的单词或短语 | 匹配相邻 token 的重叠 | 保留一份 | "Please analyze, analyze the data" | "Please analyze the data" | L1 |
| 10 | `en_hedging` | 模糊词：删除 "may"、"might"、"perhaps"（指令句中） | 匹配 `\b(may\|might\|perhaps\|probably\|possibly)\b`（祈使句语境） | 删除 | "You may want to analyze" | "Analyze" | L3 |
| 11 | `en_there_is` | "There is/are" 转直接表达 | 匹配 `There (is\|are) (a\|an\|the)? (.+?) that\|which` | `$3` | "There are several issues that need attention" | "Several issues need attention" | L2 |
| 12 | `en_instruction_merge` | 指令合并：合并多个 `\n-` 或 `\d.` 简短指令 | 检测连续列表项 | 合并为逗号分隔 | "- Analyze data\n- Generate report\n- Send email" | "Analyze data, generate report, send email" | L3 |

### 4.5 通用规则（5 条）

| # | rule_id | 说明 | 匹配/处理方式 | Before | After | 级别 |
|---|---|---|---|---|---|---|
| 1 | `univ_whitespace_clean` | 空白清理：合并连续空行、移除全角空格、统一行尾空白 | 匹配 `\n{3,}` → `\n\n`；移除 `[ \t]+$`；全角空格 → 半角 | "a\n\n\n\nb" | "a\n\nb" | L1 |
| 2 | `univ_markdown_preserve` | Markdown 结构保持：识别标题、列表、表格、引用块等，不做结构破坏 | 对 `^#{1,6}\s` / `^\|.*\|$` / `^>\s` 开头的行跳过压缩 | 标题/表格/引用跳过规则匹配 | (保持不变) | L1 |
| 3 | `univ_code_block_protect` | 代码块保护：将 ` ``` ` 围栏内的内容临时抽出，替换为占位符，压缩结束后还原 | 匹配 ` ```[\s\S]*?``` ` 整体，暂存后替换为 `__CODE_BLOCK_N__` | 代码块内容不做任何压缩 | (保持不变) | L1 |
| 4 | `univ_trim_lines` | 行首尾去空白：每行 strip，删除纯空白行（但保留 Markdown 结构所需的空行） | 每行 `^\s+` / `\s+$` 替换 | "  hello  " | "hello" | L1 |
| 5 | `univ_merge_blank_lines` | 重复换行合并：确保文件末尾只有一个换行，段落间最多两个换行 | 文件尾 `\n{3,}$` → `\n\n`；段落间 `\n{3,}` → `\n\n` | "text\n\n\n\nmore" | "text\n\nmore" | L1 |

### 4.6 重要设计决策

1. **代码块优先保护**：在应用任何规则前，先扫描并暂存代码块内容。这是最高优先级操作，防止压缩规则破坏代码结构。
2. **规则顺序**：按照 L1 → L2 → L3 的顺序应用规则，而非按中/英/通用分组。同一级别内的规则按"从保守到激进"排列。
3. **英文规则的中立性**：英文规则默认匹配大小写不敏感（`re.IGNORECASE`），但保留替换后的大小写一致性。
4. **中文规则的边界**：`cn_superlative` 和 `cn_hedging` 在非指令句（如叙事性文字）中会被跳过，仅在明显是指令/要求的上下文中生效。

---

## 5. LLM 压缩设计

### 5.1 Phase 1 状态说明

LLM 压缩模块在 Phase 1 完成**完整的接口设计、prompt 模板、参数体系、配置结构**，但 `compress()` 方法在未配置 API key 时返回原文 + 提示信息。实际调用需要用户提供有效的 LLM API key。

### 5.2 压缩 Prompt 模板

LLM 压缩器调用外部 API 时，向模型发送以下结构的 system prompt + user prompt：

**System Prompt:**

```
You are a prompt compression engine. Your task is to rewrite the following
prompt to be maximally concise while preserving ALL key instructions,
constraints, examples, and required output format.

Rules:
1. Remove all politeness, filler phrases, and redundant explanations
2. Keep all technical requirements, constraints, and format specifications
3. Preserve all examples but condense them to representative ones only
4. If the original contains multi-step instructions, use numbered lists
5. Do NOT change the core meaning or remove any required output fields
6. Output ONLY the compressed prompt, no explanation, no preamble
7. Maintain original language (if Chinese, output Chinese; if English, output English)
```

**User Prompt:**

```
Compression target: achieve at least {target_ratio * 100}% token reduction.

Original prompt:
---
{user_prompt}
---

Compressed prompt:
```

### 5.3 压缩策略参数

| 参数 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `temperature` | float | `0.1` | LLM 温度。低温度 (0.0-0.2) 保证更忠实于原文；高温度 (0.3-0.5) 允许更多改写自由度 |
| `target_ratio` | float | `0.4` | 目标压缩率。例如 0.4 = 将文本压缩至原始 token 的 60%（减少 40%） |
| `preserve_tone` | boolean | `false` | 是否保留原始语气（正式/随意/专业）。`false` 时优先简洁 |
| `aggressive` | boolean | `false` | 激进模式。`true` 时允许合并示例至 1 个、删除次要指令、合并段落 |
| `max_retries` | int | `2` | API 调用失败时的最大重试次数 |
| `timeout` | int | `30` | API 调用超时（秒） |

### 5.4 API 配置项 (llm_config)

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|---|---|---|---|---|
| `provider` | enum | 否 | `"openai"` | LLM 提供商：`"openai"` / `"anthropic"` / `"deepseek"` / `"custom"` |
| `api_key` | string | 否 | `None` | 用户提供的 API key。若为空且后端也未配置 key，返回提示信息 |
| `model` | string | 否 | `"gpt-4o-mini"` | 用于压缩的模型。建议使用小/快模型（如 gpt-4o-mini、claude-haiku）以降低成本和延迟 |
| `api_base` | string | 否 | 各 provider 默认 | 自定义 API 端点（`"custom"` provider 时必填） |
| `max_output_tokens` | int | 否 | `4096` | 压缩输出的最大 token 数 |

### 5.5 错误处理

| 场景 | 行为 |
|---|---|
| 未配置 API key | `compress()` 返回原文 + `changes` 中包含一条 `rule_id: "no_api_key"` 的提示 |
| API 调用超时 | 重试 `max_retries` 次，若仍失败，返回原文 + 提示"LLM API 超时" |
| API 返回空或无效内容 | 同上策略 |
| 压缩后 token 数反而变多 | 自动回退到原文（以 tokenizer 实际计数为准），changes 中记录 `rejected: "compression_expanded"` |
| 速率限制 (429) | 指数退避重试，最长等待 30 秒 |

---

## 6. 上下文压缩设计 — 已取消

> **上下文压缩已取消** — 现代 LLM (GPT-4, Claude 4, Gemini 2.5 等) 均内置上下文压缩能力，无需外部工具介入。


---

## 7. 压缩强度级别

三种强度级别适用于所有压缩策略，各级别定义的是一组规则或行为的集合。

### 7.1 三级定义

```
Level 1 (light) — 轻度压缩
  目标: 仅移除明显冗余的空白和标点
  效果: 平均压缩率 5-15%
  适用: 用户希望最小改动，仅做格式清理

Level 2 (medium) — 中度压缩
  目标: 移除口语填充、冗余修饰词、模糊限定
  效果: 平均压缩率 20-40%
  适用: 大多数场景的默认推荐级别

Level 3 (aggressive) — 重度压缩
  目标: 移除敬语/礼貌/自我引用，合并指令，收束示例
  效果: 平均压缩率 35-55%
  适用: 需要最大程度节省 token 的场景
```

### 7.2 各级别包含的规则集合矩阵

| 规则 | L1 (light) | L2 (medium) | L3 (aggressive) |
|---|---|---|---|
| **通用规则** | | | |
| `univ_whitespace_clean` | ✓ | ✓ | ✓ |
| `univ_markdown_preserve` | ✓ | ✓ | ✓ |
| `univ_code_block_protect` | ✓ | ✓ | ✓ |
| `univ_trim_lines` | ✓ | ✓ | ✓ |
| `univ_merge_blank_lines` | ✓ | ✓ | ✓ |
| **中文规则** | | | |
| `cn_repeated_punctuation` | ✓ | ✓ | ✓ |
| `cn_excessive_whitespace` | ✓ | ✓ | ✓ |
| `cn_repetition` (en) | ✓ | ✓ | ✓ |
| `cn_filler_word` | | ✓ | ✓ |
| `cn_redundant_modifier` | | ✓ | ✓ |
| `cn_redundant_conjunction` | | ✓ | ✓ |
| `cn_duplicate_sentence` | | ✓ | ✓ |
| `cn_question_suffix` | | ✓ | ✓ |
| `cn_metadiscourse` | | ✓ | ✓ |
| `cn_self_correction` | | ✓ | ✓ |
| `cn_redundant_honorific` | | | ✓ |
| `cn_polite_prefix` | | | ✓ |
| `cn_instruction_merge` | | | ✓ |
| `cn_example_condense` | | | ✓ |
| `cn_superlative` | | | ✓ |
| `cn_hedging` | | | ✓ |
| **英文规则** | | | |
| `en_multiple_spaces` | ✓ | ✓ | ✓ |
| `en_redundant_modifier` | | ✓ | ✓ |
| `en_filler_phrase` | | ✓ | ✓ |
| `en_unnecessary_article` | | ✓ | ✓ |
| `en_self_reference` | | ✓ | ✓ |
| `en_there_is` | | ✓ | ✓ |
| `en_polite_request` | | | ✓ |
| `en_redundant_prefix` | | | ✓ |
| `en_redundant_question` | | | ✓ |
| `en_hedging` | | | ✓ |
| `en_instruction_merge` | | | ✓ |

### 7.3 各策略下的级别映射

| 策略 | light | medium | aggressive |
|---|---|---|---|
| 规则引擎 | 仅通用规则 + 重复标点/空格 | L1 规则 + 填充词/修饰词/连词规则 | L2 规则 + 敬语/指令合并/示例收束 |
| LLM 压缩 | temperature=0.1, target_ratio=0.2 | temperature=0.1, target_ratio=0.4 | temperature=0.2, target_ratio=0.6, aggressive=true |

---

## 8. 变更日志格式

### 8.1 changes[] 条目结构

每次压缩操作会产出一个 `changes[]` 数组，数组中每条变更记录描述一次"替换操作"。

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `rule_id` | string | 是 | 触发此变更的规则标识，如 `cn_polite_prefix`。LLM 压缩时为 `"llm_rewrite"` |
| `type` | string | 否 | 变更类型：`"rule"` / `"llm"` |
| `original` | string | 是 | 被替换/删除的原始文本片段 |
| `replaced` | string | 是 | 替换后的文本（空字符串表示删除） |
| `position` | array | 是 | 原始文本中的字符偏移范围 `[start, end]`（左闭右开），用于前端渲染 diff 高亮 |
| `description` | string | 否 | 人类可读的变更说明，如 "去掉了礼貌前缀" |

### 8.2 变更类型枚举

| type | 来源 | 说明 |
|---|---|---|
| `"rule"` | 规则引擎 | 某条规则匹配并执行了替换 |
| `"llm"` | LLM 压缩 | LLM 模型对部分或全部文本进行了改写。当 LLM 输出与原文差异过大时，可用一条 `type:"llm", rule_id:"llm_rewrite"` 记录整体替换 |

### 8.3 position 定位策略

```
原文: "能否请您帮我看一下这个数据集的分析结果？"
       0  1  2  3  4  5  6  7  8  9  10 11 12 13 14 15 16 17 18

变更1: rule_id="cn_polite_prefix"
       original="能否请您帮我看一下" (字符偏移 0-9)
       replaced="看"
       position=[0, 9]

变更2: rule_id="cn_filler_word"
       original="这个" (字符偏移 9-11)
       replaced="此"
       position=[9, 11]
```

**重要规则**: 由于规则是顺序执行的，`position` 偏移始终指向**原始文本**中的位置，而非中间文本。前端渲染 diff 时需要基准到 `original_text`。

### 8.4 前端如何渲染 diff

1. 取 `result.original_text` 作为基准文本
2. 根据 `changes[].position` 计算每个变更在基准文本中的起止位置
3. 在基准文本上叠加标记：
   - 被删除/替换的片段 → 使用删除线 + 红色背景高亮
   - 替换后的新内容 → 在位置处显示插入（绿色背景）或行内标注
4. 在面板 3 的"变更详情"区域，逐条列出 `description` + `original → replaced` 对比

```
面板3 渲染示意:

原文: "能否请您帮我看一下这个数据集的分析结果？"
                         ↓
渲染效果:
  ~~能否请您帮我看一下~~ 看~~这个~~此数据集的分析结果？
  ───────────────────── ─ ──── ─
  红色删除线            绿 红色  绿
```

---

## 9. 与其他模块的关系

### 9.1 依赖关系

```
┌─────────────────────────────────────────────────────────┐
│                    compression-engine                    │
│                                                         │
│  压缩后文本需要    →  依赖 model-registry 获取默认分词器   │
│  stats 中 token 估算  →  以估算压缩前后的 token 数       │
│                                                         │
│  压缩引擎本身不直接    →  由 tokenizer-layer 做精确计量   │
│  做精确 token 计数     →  压缩后再调用分词器              │
└─────────────────────────────────────────────────────────┘
```

### 9.2 → 依赖 [model-registry](../model-registry/README.md)

- **用途**: 压缩引擎在 `stats.original_tokens_estimate` 和 `stats.compressed_tokens_estimate` 中需要估算 token 数
- **交互方式**: 压缩引擎不直接实例化分词器，而是通过 model-registry 获取当前全局默认分词器的 `estimate_tokens(text) -> int` 方法
- **注意点**: 这个估算是近似的，精确计量在压缩完成后由 tokenizer-layer 完成

### 9.3 → 依赖 [tokenizer-layer](../tokenizer-layer/README.md)

- **用途**: 压缩后的文本需要精确的 token 计数和模型级成本计算
- **交互方式**: 前端在收到压缩结果后，将 `compressed_text` 并行发送到 `POST /api/tokenize`（分词器层），获取各模型的精确 token 数
- **数据流**: `compression-engine 产出` → `前端持有` → `调用 tokenizer-layer 获取精确计量` → `前端渲染对比表`

### 9.4 → 被 [api-gateway](../api-gateway/README.md) 调用

- **用途**: 后端 API 网关定义 `POST /api/compress` 端点，接收请求后路由到对应的压缩器
- **交互方式**: api-gateway 从 HTTP 请求中解析 `CompressionRequest`，调用 `compressor.compress(request)`，将 `CompressionResult` 序列化为 JSON 响应
- **错误传播**: 压缩引擎的内部错误（如规则异常、API 调用失败）通过统一的错误类型向上抛出，由 api-gateway 转换为 HTTP 状态码

### 9.5 → 被 [frontend-ui](../frontend-ui/README.md) 使用

- **面板 2"压缩策略"**: 用户选择策略和强度，配置参数（LLM API key 等），点击"一键压缩"触发 API 调用
- **面板 3"对比结果"**: 展示 `compressed_text` 与 `original_text` 的对比，逐条渲染 `changes[]` 变更日志
- **交互反馈**: 压缩过程中前端显示加载动画；压缩失败时策略面板显示错误提示
- **导出/撤销**: 导出直接使用 `compressed_text`；撤销恢复为 `original_text`

---

## 10. 扩展指南

### 10.1 如何添加新的压缩规则

为规则引擎添加一条新规则的完整步骤：

**步骤 1: 确定规则规格**
- 确定规则属于哪一组：中文 / 英文 / 通用
- 编写模式（pattern）和替换（replacement）
- 确定最低适用强度级别（L1 / L2 / L3）
- 准备 3 组 before/after 测试用例

**步骤 2: 定义规则元数据**
- 分配唯一的 `rule_id`，格式为 `{语言前缀}_{描述}`，如 `cn_topic_marker_remove`
- 编写 rule_id 对应的规则属性：`category`、`pattern`、`replacement`、`min_level`、`description`

**步骤 3: 插入规则列表**
- 将新规则插入对应语言组的规则列表末尾（不建议插入中间，因为规则间可能有隐式顺序依赖）
- 更新强度级别矩阵表（第 7.2 节的矩阵）
- 如果规则的 `min_level` 变了，更新对应行的级别标记

**步骤 4: 将规则注册到级别集合**
- 规则引擎内部维护 `LEVEL_RULES` 映射：`light` → [规则列表]、`medium` → [...]、`aggressive` → [...]
- 新规则根据 `min_level` 自动加入对应的级别集合

**步骤 5: 验证**
- 运行 3 组测试用例，确认 before → after 符合预期
- 确认不会破坏代码块保护
- 确认不会产生空文本（删除所有内容的情况应特殊处理）

**示例: 添加一条中文规则**

```
rule_id: cn_topic_marker_remove
category: cn
pattern: "关于(.*?)的(问题|话题|方面)"
replacement: "$1"
min_level: aggressive
description: 移除话题标记词
before: 关于这个数据集的问题
after:  这个数据集
```

### 10.2 如何接入新的 LLM 压缩模型

**步骤 1: 确定 Provider 协议**
- 新 LLM 提供商是否兼容现有的 OpenAI API 格式（`/v1/chat/completions`）？
- 若兼容，只需在 `llm_compressor.py` 的 `PROVIDER_MAP` 中增加一个条目：`provider_name` → `api_base`
- 若不兼容（如有独立的 SDK 或不同接口规范），需要实现新的调用适配器

**步骤 2: 添加 Provider 配置**

```
llm_config.provider 新增枚举值: "new_provider"
llm_config 中对应的默认值:
  - api_base: "https://api.newprovider.com/v1"
  - 建议模型: "new-fast-model"
```

**步骤 3: 实现调用适配器（仅当 API 不兼容时）**
- 适配器接收 `llm_config` + `prompt_template`，返回压缩后文本
- 超时、重试、错误处理的策略继承自第 5.5 节的错误处理策略

**步骤 4: 前端支持**
- 在面板 2 的 LLM 策略配置中，`provider` 下拉框增加新选项
- 如果新模型需要特殊的参数（如 `top_p`、`frequency_penalty`），在配置区动态展开

**步骤 5: 验证**
- 在目标模型上运行压缩测试，对比压缩前后语义保留程度
- 在英文和中文 prompt 上分别验证
- 验证错误处理：无效 API key、超时、速率限制

### 10.3 如何调整压缩强度级别

如果发现某个级别的压缩效果不符合预期，可以调整规则级别归属：

- **上移**（从 L3 移到 L2）：如果规则可以安全地应用在更多场景，将其 `min_level` 降一级
- **下移**（从 L2 移到 L3）：如果规则存在误伤风险（如删除了必要内容），将其 `min_level` 升一级
- **跨语言迁移**：如果一条中文规则有对应的英文版本但效果不同，可单独调整英文版本的级别

### 10.4 ~~如何扩展上下文压缩的摘要策略~~ 已取消

上下文压缩已取消，此章节不适用。

---

## 附录 A: 版本历史

| 版本 | 日期 | 变更说明 |
|---|---|---|
| v2.0 | 2026-07-06 | 从项目设计文档分离为独立模块文档，补充策略对比表、完整的 32 条规则说明、扩展指南 |

---

## 附录 B: 交叉引用索引

| 目标模块 | 文件路径 | 关联内容 |
|---|---|---|
| 模型注册表 | `../model-registry/README.md` | 默认分词器获取 |
| 分词器层 | `../tokenizer-layer/README.md` | 精确 token 计量 |
| API 网关 | `../api-gateway/README.md` | POST /api/compress 端点 |
| 前端 UI | `../frontend-ui/README.md` | 面板 2 策略选择 + 面板 3 变更展示 |
| 项目设计文档 | `../../design-document.md` | 总体架构和 API 定义 |
