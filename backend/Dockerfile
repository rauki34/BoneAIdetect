# 后端镜像（Flask + Celery worker 共用）
#
# ⚠️ **本文件未经实跑验证**：本机 Docker 引擎起不来（缺 WSL2 所需的 Windows
# 功能，见 docker-compose.yml 顶部的诊断与启用步骤）。语法与编排结构已用真正的
# compose 解析器校验过（`docker compose config` 零警告），但没有真正 build 起来过。
# 引擎就绪后请按 docker-compose.yml 顶部的步骤跑一次，再把这一段删掉。
#
# 体积提醒：requirements.txt 里有 torch/torchvision/ultralytics，镜像约 5-7 GB。
# 只要 CPU 推理时可用 --build-arg TORCH_INDEX_URL=... 换成 CPU 版 torch，
# 能省下大半（代价是没有 GPU 加速）。
FROM python:3.11-slim

ARG TORCH_INDEX_URL=""

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

# libgl1 / libglib2.0-0：opencv（ultralytics 依赖）在 slim 镜像里缺这两个
# 共享库会报 "libGL.so.1: cannot open shared object file"
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgl1 libglib2.0-0 curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app/backend

# 依赖单独一层：代码改了不必重装 5 GB 依赖
COPY requirements.txt .
RUN if [ -n "$TORCH_INDEX_URL" ]; then \
        pip install --index-url "$TORCH_INDEX_URL" torch torchvision; \
    fi \
    && pip install -r requirements.txt

COPY . .

# 语料与上传目录随镜像进来，但运行期会被 compose 的 volume 覆盖 ——
# 语料（knowledge/corpus）是**随仓库提交**的，所以镜像里有它是有意义的
# （不用 volume 也能跑）。
EXPOSE 5000

# 默认起后端；celery 服务在 compose 里覆盖 command。
# 用 `python -m` 而不是裸 gunicorn：与 scripts/flask.sh 的说明一致 ——
# 保证 sys.path 里有 backend/ 本身。
CMD ["python", "app.py"]
