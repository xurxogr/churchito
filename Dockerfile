# syntax=docker/dockerfile:1

# Multi-stage build for smaller final image
# Build with: docker build --build-arg PYTHON_VERSION=3.13 .
ARG PYTHON_VERSION=3.13

# Build stage
FROM python:${PYTHON_VERSION}-slim AS builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Create virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy pyproject.toml and version file for dependency installation
COPY pyproject.toml .
COPY discord_bot/__init__.py discord_bot/__init__.py
COPY discord_bot/__version__.py discord_bot/__version__.py

# Install dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir . && \
    # Strip debug symbols to reduce image size
    find /opt/venv -name "*.so" -exec strip --strip-debug {} \; 2>/dev/null || true

# Runtime stage
ARG PYTHON_VERSION=3.13
FROM python:${PYTHON_VERSION}-slim AS runtime

# Build-time git information (passed during docker build)
ARG GIT_COMMIT_HASH=unknown
ARG GIT_COMMIT_SHORT_HASH=unknown
ARG GIT_COMMIT_DATE=unknown
ARG GIT_DIRTY=unknown

WORKDIR /app

# Install runtime dependencies for PostgreSQL
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Create non-root user
RUN useradd --create-home --shell /bin/bash botuser

# Copy application code
COPY --chown=botuser:botuser . .

# Create entry point scripts (deps already installed)
RUN pip install --no-cache-dir --no-deps .

# Write git info to file for runtime access
RUN echo "GIT_COMMIT_HASH=${GIT_COMMIT_HASH}" > /app/.git_info && \
    echo "GIT_COMMIT_SHORT_HASH=${GIT_COMMIT_SHORT_HASH}" >> /app/.git_info && \
    echo "GIT_COMMIT_DATE=${GIT_COMMIT_DATE}" >> /app/.git_info && \
    echo "GIT_DIRTY=${GIT_DIRTY}" >> /app/.git_info

# Create data directory for SQLite (if used) and logs
RUN mkdir -p /app/data /app/logs && chown -R botuser:botuser /app/data /app/logs

# Add /app to PYTHONPATH
ENV PYTHONPATH=/app

# Switch to non-root user
USER botuser

# Expose web dashboard port
EXPOSE 8000

# Health check for web dashboard
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:8000/health')" || exit 1

# Run the bot
CMD ["python", "-m", "discord_bot"]
