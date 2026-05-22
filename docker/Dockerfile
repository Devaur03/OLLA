FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install CPU version of PyTorch to avoid massive ~3GB CUDA downloads
RUN pip install --no-cache-dir torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code. Config comes from environment variables (not a
# committed .env file) — keeps secrets out of the image and the build robust.
COPY app/ ./app/
COPY mcp_server/ ./mcp_server/
COPY cli.py ./cli.py

EXPOSE 8000

# Run with 4 workers for production
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
