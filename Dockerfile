FROM python:3.12-slim AS builder

WORKDIR /build
COPY pyproject.toml README.md README.zh-CN.md LICENSE ./
COPY src/ ./src/
COPY frontend/ ./frontend/
RUN python -m pip install --no-cache-dir build \
    && python -m build --wheel --outdir /wheels \
    && python -m pip install --no-cache-dir /wheels/*.whl \
    && python -c "import tiktoken; tiktoken.get_encoding('o200k_base'); tiktoken.get_encoding('cl100k_base')"

FROM python:3.12-slim AS runtime

LABEL org.opencontainers.image.source="https://github.com/fenglingshuishan/Token-Calculator" \
      org.opencontainers.image.description="Archived Prompt Economics Workbench" \
      org.opencontainers.image.licenses="ISC"

RUN groupadd --system app && useradd --system --gid app --home-dir /app app
WORKDIR /app
COPY --from=builder /wheels/*.whl /tmp/
RUN python -m pip install --no-cache-dir /tmp/*.whl && rm -f /tmp/*.whl
COPY --from=builder /tmp/data-gym-cache/ /opt/token-calculator/tiktoken-cache/
ENV TIKTOKEN_CACHE_DIR=/opt/token-calculator/tiktoken-cache

USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)" || exit 1

ENTRYPOINT ["token-calculator"]
CMD ["--host", "0.0.0.0", "--port", "8000", "--no-browser"]
