FROM python:3.12-slim

WORKDIR /app
RUN pip install --no-cache-dir uv==0.13.4
COPY pyproject.toml uv.lock README.md ./
COPY src/ ./src/
RUN uv sync --locked --no-dev --no-editable \
    && useradd --create-home --uid 10001 agent

USER agent
ENV AGENT_MODE=demo
EXPOSE 8000
CMD ["/app/.venv/bin/uvicorn", "sample_agent.app:app", "--host", "0.0.0.0", "--port", "8000"]
