# Reranker service for Probe
# Supports Qwen3-Reranker and zerank-2 models

FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY main.py .

# Default port
ENV PORT=8083

EXPOSE ${PORT}

CMD ["python", "main.py"]
