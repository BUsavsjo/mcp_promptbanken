FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=utf-8 \
    PYTHONUTF8=1 \
    MCP_HOST=0.0.0.0 \
    MCP_PORT=8000

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY server ./server
COPY prompts ./prompts
COPY skills.json ./skills.json

RUN adduser --disabled-password --gecos "" --uid 10001 appuser \
    && chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

CMD ["python", "-m", "server.http_server"]
