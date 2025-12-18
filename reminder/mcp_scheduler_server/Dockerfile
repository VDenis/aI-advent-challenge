 FROM python:3.11-slim

 WORKDIR /app

 ENV PYTHONUNBUFFERED=1 \
     PIP_DISABLE_PIP_VERSION_CHECK=on \
     TASKS_FILE=/app/data/tasks.json

RUN pip install --no-cache-dir poetry==1.8.3

COPY pyproject.toml ./pyproject.toml

RUN poetry config virtualenvs.create false \
 && poetry install --only main --no-root --no-interaction --no-ansi

COPY mcp_scheduler_server /app/mcp_scheduler_server
COPY data /app/data

 EXPOSE 8000

 CMD ["poetry", "run", "python", "-m", "mcp_scheduler_server.app"]
