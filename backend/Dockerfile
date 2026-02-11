FROM python:3.11-slim

# 安装 uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

WORKDIR /app

# 利用缓存层优化
COPY pyproject.toml uv.lock ./

# 安装依赖。注意：在 Docker 中我们通常不需要 venv，但 uv run 会自动处理
# --frozen 确保锁定版本，--no-dev 排除开发依赖
RUN uv sync --frozen --no-dev

COPY . .

EXPOSE 8000

# 使用 uv run 确保在正确的同步环境下运行
CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]