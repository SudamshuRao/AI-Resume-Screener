FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source into /app/agents/ so "agents.main" is importable
COPY . /app/agents/

CMD ["sh", "-c", "uvicorn agents.main:app --host 0.0.0.0 --port ${PORT:-8001}"]