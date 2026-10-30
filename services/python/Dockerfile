FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app
COPY services/python /app/services/python
RUN pip install /app/services/python
COPY skills /app/skills
COPY config /app/config
COPY data/knowledge /app/data/knowledge

ENV AGENTFLOW_SKILLS_DIR=/app/skills \
    AGENTFLOW_MCP_CONFIG=/app/config/mcp_servers.json

EXPOSE 8000
CMD ["uvicorn", "agentflow.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
