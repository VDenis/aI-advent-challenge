 FROM python:3.11-slim

 WORKDIR /app

 ENV PYTHONUNBUFFERED=1 \
     PIP_DISABLE_PIP_VERSION_CHECK=on

 RUN pip install --no-cache-dir poetry==1.8.3

 COPY pyproject.toml ./pyproject.toml

 RUN poetry config virtualenvs.create false \
  && poetry install --only main --no-root --no-interaction --no-ansi

 COPY console_agent /app/console_agent

 CMD ["poetry", "run", "python", "-m", "console_agent.app"]
