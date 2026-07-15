# Token Calculator — 已归档的 Prompt 成本工作台

[English](README.md) · [归档原因](docs/ARCHIVE.md) · [更新记录](CHANGELOG.md)

> **已归档，仅做维护性保存。** 本仓库是冻结的参考实现。项目提供可复现的
> 发行封装，但没有持续开发路线，不应被视为受支持的生产服务。

Token Calculator 是一个本地 FastAPI Web 应用，用于 Token 计数、保守的
Prompt 清理、可选的 LLM 压缩和回本实验。归档版本面向可能在未来运营自建
Agent/API 网关的开发者；只有这类开发者能够观察完整请求和提供商 usage。

它**不是** Codex、Claude Code、Gemini CLI 等托管 Agent 的成本优化器。这些
产品会组装本工具无法查看的隐藏指令、工具、历史和运行时上下文。缩短用户输入
不能证明 Agent 的总费用下降。

## 包含的功能

- 使用 `tiktoken` 精确计算 `o200k_base` 和 `cl100k_base`。
- 可选 Hugging Face tokenizer；资源不可用时明确标记为估算。
- 保守的本地清理，保护代码块、URL、列表结构、数字、JSON 字段、标题和模板变量。
- 可选的 OpenAI 兼容 LLM 压缩，提供商失败不会被伪装成本地结果。
- 计算压缩成本、毛节省、净节省和回本次数。
- FastAPI 接口和本地浏览器界面。
- wheel/sdist、Docker/Compose 和独立可执行文件构建方案。

## 重要限制

1. 结构检查不能证明语义等价，仍然必须人工审核并运行任务级评测。
2. 内置模型价格只是带日期的快照，任何财务结论都应重新核对官网价格。
3. 缓存经济模型是简化模型，未覆盖所有提供商的写入价格、TTL、前缀门槛和
   长上下文分级价格。
4. 第三方 tokenizer 映射可能落后于模型更新。“精确”表示对所选 tokenizer
   资源精确，不保证与另一个托管模型别名完全一致。
5. LLM 压缩模式会把 Prompt 发送给所配置的提供商，并产生额外费用。
6. 不要把这个已归档服务直接暴露到公网。

参见[归档说明](docs/ARCHIVE.md)和[安全说明](SECURITY.md)。

## 快速开始

### 预编译独立程序

前往仓库的 [Releases](https://github.com/fenglingshuishan/Token-Calculator/releases)
页面，下载 Linux、Windows 或 macOS 对应的压缩包。解压后运行
`token-calculator`（Windows 为 `token-calculator.exe`），然后打开
<http://127.0.0.1:8000>。

独立程序包含核心 OpenAI tokenizer，但有意排除了体积较大的可选 Hugging Face
tokenizer。

### Docker Compose

```bash
docker compose up --build -d
```

打开 <http://127.0.0.1:8000>。停止服务：

```bash
docker compose down
```

### Docker

```bash
docker build -t token-calculator:3.0.0-archive .
docker run --rm --read-only --tmpfs /tmp -p 8000:8000 \
  token-calculator:3.0.0-archive
```

### Python wheel 或源码包

从 Releases 下载 `.whl` 后执行：

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install token_calculator-3.0.0-py3-none-any.whl
token-calculator
```

也可以使用模块入口：

```bash
python -m token_calculator
```

### 源码运行

```bash
git clone https://github.com/fenglingshuishan/Token-Calculator.git
cd Token-Calculator
python -m venv .venv
. .venv/bin/activate
python -m pip install -e .
python run.py
```

Windows PowerShell 的激活命令为 `.venv\Scripts\Activate.ps1`。

## 可选 tokenizer 资源

独立程序压缩包和容器镜像内置 OpenAI `tiktoken` 词表。wheel/源码安装会在首次
明确准备后将其保存在 tiktoken 本地缓存中；可使用界面的 tokenizer 准备操作，
或首次以 `TOKEN_CALC_ALLOW_DOWNLOAD=1` 启动。如需归档版本中的第三方 tokenizer
适配器，再安装可选依赖：

```bash
python -m pip install -e '.[tokenizers]'
python scripts/download_tokenizers.py
```

Tokenizer 下载可能很大，并且需要访问上游模型仓库。资源缺失时，系统会回退到
带明确标签的语言感知估算。

## 命令行参数

```text
token-calculator [--host HOST] [--port PORT] [--no-browser] [--debug]
token-calculator --version
```

对应环境变量：

- `APP_HOST`：监听地址，默认 `127.0.0.1`；
- `APP_PORT`：HTTP 端口，默认 `8000`。

## API

交互式 OpenAPI 文档位于 <http://127.0.0.1:8000/docs>。

| 方法 | 路径 | 用途 |
|---|---|---|
| `GET` | `/health` | 运行版本和能力 |
| `GET` | `/api/models` | 模型分组、价格快照与来源 |
| `GET` | `/api/tokenizers/status` | 本地 tokenizer 状态 |
| `POST` | `/api/tokenizers/prepare` | 准备可选 tokenizer 资源 |
| `POST` | `/api/tokenize` | 计算输入、输出或缓存 Token |
| `POST` | `/api/compress` | 本地清理或可选 LLM 压缩 |
| `POST` | `/api/cost-simulate` | 比较不同模型的场景成本 |
| `POST` | `/api/export` | 导出纯文本、Markdown 或 JSON |

示例：

```bash
curl -s http://127.0.0.1:8000/api/tokenize \
  -H 'content-type: application/json' \
  -d '{"text":"你好，世界","group_ids":["o200k_base"],"mode":"input"}'
```

## 作为 Python 组件嵌入

```python
from token_calculator import create_app

# 仅 API；如需界面可传入静态文件目录。
app = create_app(static_dir=None)
```

包还导出了 `PricingRegistry`、`RuleCompressor`、`LLMCompressor`、
`CostSimulator` 和 Token 计数辅助函数。这些接口被冻结保存，不承诺继续兼容演进。

## 构建和验证

```bash
python -m pip install -e '.[dev,build]'
pytest
npm test
python -m build
python -c "import tiktoken; tiktoken.get_encoding('o200k_base'); tiktoken.get_encoding('cl100k_base')"
pyinstaller --clean --noconfirm token-calculator.spec
docker build -t token-calculator:test .
```

发布工作流会构建：

- Python wheel 和源码包；
- Linux x86-64 独立程序；
- Windows x86-64 独立程序；
- macOS arm64 独立程序；
- GitHub Container Registry 镜像。

## 仓库结构

```text
frontend/                  浏览器界面
src/token_calculator/      Python 包和 FastAPI 应用
tests/                     单元、API 和可选浏览器测试
scripts/                   Tokenizer 准备脚本
docs/                      历史架构与归档原因
.github/workflows/         CI 和标签发行封装
Dockerfile                 可复现容器构建
docker-compose.yml         本地容器部署
token-calculator.spec      独立可执行程序构建配置
```

## 发布策略

`3.0.0` 是最终归档基线。维护者可以为关键的封装或安全修正临时解除归档，但不
承诺功能开发、价格数据持续更新或支持响应时间。

## 许可证

[ISC](LICENSE)
