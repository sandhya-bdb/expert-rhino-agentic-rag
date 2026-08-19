FROM python:3.12-slim

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Set up user with UID 1000 (required for Hugging Face Spaces)
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user
ENV PATH=/home/user/.local/bin:$PATH

# Set working directory
WORKDIR /home/user/app

# Copy dependency files
COPY --chown=user:user pyproject.toml uv.lock ./

# Install python dependencies
RUN uv sync --frozen

# Pre-cache the uvx MCP servers inside the image
RUN uvx --with "mcp<2" mcp-server-fetch --help && uvx mcp-server-qdrant --help

COPY --chown=user:user app.py ./
COPY --chown=user:user styles.py ./
COPY --chown=user:user src/ ./src/
COPY --chown=user:user static/ ./static/
COPY --chown=user:user knowledge/ ./knowledge/

# Disable python stdout buffering
ENV PYTHONUNBUFFERED=1
ENV PORT=7860

# Run FastAPI app via uvicorn reading PORT dynamically from environment
CMD ["sh", "-c", "/home/user/app/.venv/bin/uvicorn app:app --host 0.0.0.0 --port $PORT"]
