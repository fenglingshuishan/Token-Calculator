FROM python:3.11-slim AS builder
WORKDIR /app
COPY pyproject.toml .
RUN pip install --no-cache-dir ".[all]"

FROM python:3.11-slim
RUN groupadd -r app && useradd -r -g app -d /app -s /bin/false app
WORKDIR /app
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
COPY src/ ./src/
COPY frontend/ ./frontend/
COPY run.py .
RUN pip install --no-cache-dir -e .
RUN chown -R app:app /app
USER app
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1
EXPOSE 8000
CMD ["python", "run.py"]
