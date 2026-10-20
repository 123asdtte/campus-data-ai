FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt .
COPY wheels ./wheels

# 两种安装方式，按网络环境自动选择：
#   1. 存在本地 wheel（wheels/*.whl）时离线安装，适用于容器无法直连 PyPI 的环境；
#   2. 否则回退到 PIP_INDEX_URL 指定的源（内网可改为学校镜像）。
ARG PIP_INDEX_URL=https://pypi.org/simple
RUN if ls ./wheels/*.whl >/dev/null 2>&1; then \
        echo "installing from local wheels"; \
        pip install --no-index --find-links=./wheels -r requirements.txt; \
    else \
        echo "installing from ${PIP_INDEX_URL}"; \
        pip install --index-url "${PIP_INDEX_URL}" -r requirements.txt; \
    fi

COPY app ./app
COPY scripts ./scripts

RUN mkdir -p /data/uploads \
    && useradd --create-home --shell /usr/sbin/nologin appuser \
    && chown -R appuser:appuser /app /data

USER appuser

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
