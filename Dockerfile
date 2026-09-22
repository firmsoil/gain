# ==============================================================================
# Multi-stage Dockerfile for GAIN (GitHub AI Intelligence Network)
# Python 3.12, Distroless/Minimal hardened runtime with non-root security context
# ==============================================================================

# ------------------------------------------------------------------------------
# Stage 1: Build & Package Wheel
# ------------------------------------------------------------------------------
FROM python:3.12-slim AS builder

WORKDIR /build

# Install compilation prerequisites if native extensions are needed
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv for fast, deterministic dependency resolution
COPY --from=ghcr.io/astral-sh/uv:0.6.14 /uv /uvx /bin/

# Copy project specifications
COPY pyproject.toml README.md ./
COPY src/ ./src/

# Build wheel package and export production dependencies
RUN uv build --wheel --out-dir /build/dist && \
    uv pip compile pyproject.toml --output-file /build/requirements.txt

# Create self-contained target directory with production wheels
RUN pip install --no-cache-dir --prefix=/install -r /build/requirements.txt && \
    pip install --no-cache-dir --prefix=/install --no-deps /build/dist/*.whl

# ------------------------------------------------------------------------------
# Stage 2: Hardened Production Runtime
# ------------------------------------------------------------------------------
FROM python:3.12-slim AS runtime

LABEL org.opencontainers.image.title="GAIN — GitHub AI Intelligence Network" \
      org.opencontainers.image.description="Enterprise engineering-flow analytics for GitHub repositories" \
      org.opencontainers.image.version="0.1.0" \
      org.opencontainers.image.source="https://github.com/firmsoil/gain" \
      org.opencontainers.image.licenses="Apache-2.0"

# Security: Install ca-certificates and curl for health probes; remove package cache
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
    && rm -rf /var/lib/apt/lists/* \
    && rm -rf /var/cache/apt/*

# Security: Create non-root user and group
ENV GAIN_USER=gain \
    GAIN_UID=10001 \
    GAIN_GID=10001

RUN groupadd --gid ${GAIN_GID} ${GAIN_USER} && \
    useradd --uid ${GAIN_UID} --gid ${GAIN_GID} --create-home --home-dir /app --shell /usr/sbin/nologin ${GAIN_USER}

# Copy installed Python packages from builder
COPY --from=builder /install /usr/local

WORKDIR /app

# Create default data directories and set permissions for gain user
RUN mkdir -p /app/data/raw /app/data/canonical /app/data/output /app/data/checkpoints && \
    chown -R ${GAIN_USER}:${GAIN_USER} /app

# Environment defaults
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    GAIN_ENVIRONMENT=production \
    GAIN_DATA_DIR=/app/data \
    GAIN_RAW_DIR=/app/data/raw \
    GAIN_CANONICAL_DIR=/app/data/canonical \
    GAIN_OUTPUT_DIR=/app/data/output \
    PATH="/usr/local/bin:/app/.local/bin:${PATH}"

# Switch to non-root user
USER ${GAIN_USER}

# Default port for GAIN MCP Streamable HTTP transport
EXPOSE 8000

# Container healthcheck: tests HTTP /healthz if port 8000 is listening, otherwise verifies CLI config-check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://127.0.0.1:8000/healthz 2>/dev/null || gain config-check >/dev/null 2>&1 || exit 1

# Default CLI entrypoint
ENTRYPOINT ["gain"]
CMD ["--help"]
