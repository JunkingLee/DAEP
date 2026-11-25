FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 DAEP_DB_PATH=/data/daep.db
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY alembic.ini ./alembic.ini
COPY alembic ./alembic
COPY app ./app
COPY daep_mcp ./daep_mcp
COPY daep_worker ./daep_worker
COPY daep_agent_bridge ./daep_agent_bridge
COPY deploy/postgres ./deploy/postgres
COPY web ./web
RUN addgroup --system daep && adduser --system --ingroup daep daep && mkdir -p /data && chown -R daep:daep /data
USER daep
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/readyz', timeout=3)" || exit 1
CMD ["uvicorn","app.main:app","--host","0.0.0.0","--port","8000"]
