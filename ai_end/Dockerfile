ARG BASE_IMAGE=docker.1ms.run/python:3.11-slim
FROM ${BASE_IMAGE}

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV UV_PROJECT_ENVIRONMENT=/opt/venv
ENV UV_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple

WORKDIR /app

RUN set -eux; \
    if ! pip install --no-cache-dir uv -i https://pypi.tuna.tsinghua.edu.cn/simple; then \
        if ! pip install --no-cache-dir uv -i https://mirrors.aliyun.com/pypi/simple/; then \
            pip install --no-cache-dir uv; \
        fi; \
    fi

COPY pyproject.toml uv.lock README.md /app/
RUN set -eux; \
    if ! uv sync --frozen --no-dev --no-install-project --extra di; then \
        if ! UV_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/ uv sync --frozen --no-dev --no-install-project --extra di; then \
            UV_INDEX_URL=https://pypi.org/simple uv sync --frozen --no-dev --no-install-project --extra di; \
        fi; \
    fi

COPY . /app

EXPOSE 8000
