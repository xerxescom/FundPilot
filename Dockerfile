FROM python:3.13-slim

# 固定版本 uv，依赖用 uv.lock 冻结安装（与本地/CI 完全一致）
COPY --from=ghcr.io/astral-sh/uv:0.12.9 /uv /uvx /bin/

# 可选：网络受限时用镜像源加速构建，例如
#   docker compose --env-file .env.docker build --build-arg ... 或设置 DOCKER_UV_INDEX_URL
ARG UV_INDEX_URL=""
ENV UV_DEFAULT_INDEX=${UV_INDEX_URL:-https://pypi.org/simple}

WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"

# 先只拷贝依赖清单，充分利用层缓存
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./alembic.ini
COPY scripts ./scripts
RUN uv sync --frozen --no-dev

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
