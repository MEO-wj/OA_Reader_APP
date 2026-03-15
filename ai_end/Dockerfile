FROM python:3.11-slim

WORKDIR /app

# 安装 uv
RUN pip install uv

# 复制依赖文件（构建上下文需为仓库根目录）
COPY ai_end/pyproject.toml ai_end/uv.lock ./ai_end/

# 使用 uv 安装依赖
WORKDIR /app/ai_end
RUN uv sync --frozen --no-dev

# 复制应用与共享 backend 代码
WORKDIR /app
COPY ai_end ./ai_end
COPY backend ./backend

# 暴露端口
WORKDIR /app/ai_end
EXPOSE 4421

# 启动命令
CMD ["uv", "run", "gunicorn", "--bind", "0.0.0.0:4421", "--workers", "2", "--timeout", "120", "app:app"]
