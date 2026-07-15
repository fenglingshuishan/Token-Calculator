# Token Calculator — Archived Prompt Economics Workbench

[简体中文](README.zh-CN.md) · [Archive rationale](docs/ARCHIVE.md) · [Changelog](CHANGELOG.md)

> **Archived / maintenance-only.** This repository is a frozen reference
> implementation. It is packaged for reproducible use, but it has no active
> roadmap and should not be treated as a supported production service.

Token Calculator is a local FastAPI web application for token counting,
conservative prompt cleanup, optional LLM-based compression, and break-even
experiments. The archived release is intended for developers who may later
operate their own Agent/API gateway and can observe the complete request and
provider usage data.

It is **not** a cost optimizer for managed agents such as Codex, Claude Code, or
Gemini CLI. Those products assemble hidden instructions, tools, history, and
runtime context that this application cannot inspect. A shorter user message
does not prove a lower total agent cost.

## What is included

- Exact `tiktoken` counting for `o200k_base` and `cl100k_base`.
- Optional Hugging Face tokenizers, with estimates clearly labelled when a
  tokenizer is unavailable.
- Conservative local cleanup that protects code blocks, URLs, list structure,
  numbers, JSON keys, headings, and template variables.
- Optional OpenAI-compatible LLM compression with explicit provider failures.
- Compression-cost, gross-savings, net-savings, and break-even calculations.
- FastAPI endpoints plus a local browser UI.
- Wheel/sdist, Docker/Compose, and standalone executable build recipes.

## Important limitations

1. Structural checks do not prove semantic equivalence. Human review and
   task-level evaluations remain mandatory.
2. Built-in model prices are dated snapshots. Verify provider pricing before
   using any financial result.
3. Cache economics are simplified and do not model every provider's cache
   write price, TTL, prefix threshold, or long-context tier.
4. Third-party tokenizer mappings can lag behind model releases. “Exact” means
   exact for the selected tokenizer asset, not a guarantee about an unrelated
   hosted model alias.
5. The LLM compression mode sends the prompt to the configured provider and
   creates additional cost.
6. Do not expose this archived service directly to the public internet.

See [the archive notice](docs/ARCHIVE.md) and [security policy](SECURITY.md).

## Quick start

### Prebuilt standalone archive

Open the repository's [Releases](https://github.com/fenglingshuishan/Token-Calculator/releases)
page and download the archive for Linux, Windows, or macOS. Extract it, run
`token-calculator` (`token-calculator.exe` on Windows), then open
<http://127.0.0.1:8000>.

The standalone build contains the core OpenAI tokenizers. Large optional Hugging
Face tokenizers are deliberately excluded.

### Docker Compose

```bash
docker compose up --build -d
```

Open <http://127.0.0.1:8000>. Stop it with:

```bash
docker compose down
```

### Docker

```bash
docker build -t token-calculator:3.0.0-archive .
docker run --rm --read-only --tmpfs /tmp -p 8000:8000 \
  token-calculator:3.0.0-archive
```

### Python wheel or source distribution

Download a `.whl` from Releases and run:

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install token_calculator-3.0.0-py3-none-any.whl
token-calculator
```

The equivalent module command is:

```bash
python -m token_calculator
```

### Source checkout

```bash
git clone https://github.com/fenglingshuishan/Token-Calculator.git
cd Token-Calculator
python -m venv .venv
. .venv/bin/activate
python -m pip install -e .
python run.py
```

Windows PowerShell activation is `.venv\Scripts\Activate.ps1`.

## Optional tokenizer assets

The standalone archives and container image embed the OpenAI `tiktoken` tables.
A wheel/source install keeps them in tiktoken's local cache after the first
explicit preparation; use the UI's tokenizer preparation action or start once
with `TOKEN_CALC_ALLOW_DOWNLOAD=1`. Install the optional stack only if you need
the archived third-party tokenizer adapters:

```bash
python -m pip install -e '.[tokenizers]'
python scripts/download_tokenizers.py
```

Tokenizer downloads can be large and require access to their upstream model
repositories. Missing assets fall back to a clearly labelled language-aware
estimate.

## Command-line options

```text
token-calculator [--host HOST] [--port PORT] [--no-browser] [--debug]
token-calculator --version
```

Environment equivalents:

- `APP_HOST` — bind address, default `127.0.0.1`;
- `APP_PORT` — HTTP port, default `8000`.

## API

Interactive OpenAPI documentation is available at <http://127.0.0.1:8000/docs>.

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/health` | Runtime version and capabilities |
| `GET` | `/api/models` | Model groups, price snapshots, and sources |
| `GET` | `/api/tokenizers/status` | Local tokenizer readiness |
| `POST` | `/api/tokenizers/prepare` | Prepare optional tokenizer assets |
| `POST` | `/api/tokenize` | Count input, output, or cached tokens |
| `POST` | `/api/compress` | Local cleanup or optional LLM compression |
| `POST` | `/api/cost-simulate` | Compare scenario costs across models |
| `POST` | `/api/export` | Export plain text, Markdown, or JSON |

Example:

```bash
curl -s http://127.0.0.1:8000/api/tokenize \
  -H 'content-type: application/json' \
  -d '{"text":"Hello, world","group_ids":["o200k_base"],"mode":"input"}'
```

## Python embedding

```python
from token_calculator import create_app

# API-only application; pass a static directory to include the bundled UI.
app = create_app(static_dir=None)
```

The package also exports `PricingRegistry`, `RuleCompressor`, `LLMCompressor`,
`CostSimulator`, and token-counting helpers. These APIs are frozen rather than
guaranteed to evolve compatibly.

## Build and verify

```bash
python -m pip install -e '.[dev,build]'
pytest
npm test
python -m build
python -c "import tiktoken; tiktoken.get_encoding('o200k_base'); tiktoken.get_encoding('cl100k_base')"
pyinstaller --clean --noconfirm token-calculator.spec
docker build -t token-calculator:test .
```

The release workflow builds:

- Python wheel and source distribution;
- Linux x86-64 standalone archive;
- Windows x86-64 standalone archive;
- macOS arm64 standalone archive;
- a GitHub Container Registry image.

## Repository layout

```text
frontend/                  Browser UI
src/token_calculator/      Python package and FastAPI application
tests/                     Unit, API, and optional browser tests
scripts/                   Tokenizer preparation helpers
docs/                      Architecture history and archive rationale
.github/workflows/         CI and tagged-release packaging
Dockerfile                 Reproducible container build
docker-compose.yml         Local container deployment
token-calculator.spec      Standalone executable recipe
```

## Release policy

Version `3.0.0` is the final archived baseline. A maintainer may temporarily
unarchive the repository for a critical packaging or security correction, but
no feature development, provider-price freshness, or support response time is
promised.

## License

[ISC](LICENSE)
