# 本地 AI 服务镜像（Qwen3-VL-4B，端口 8000）
#
# ⚠️ **本文件未经实跑验证**：本机 Docker 引擎起不来（缺 WSL2 所需的 Windows 功能，
# 诊断与启用步骤见 docker-compose.yml 顶部）。
#
# 这个服务是**可选**的：不起来的话后端会走 DB 里配置的远程 Provider
# （如 ModelScope），或退回"AI 暂不可用"的降级路径，其余功能不受影响。
#
# 模型权重不入镜像：AI/Qwen3-VL-4B-Instruct 在 .gitignore 里（约 8GB），
# compose 用只读挂载把它挂进容器。所以**跑这个服务的前提是宿主机上已下载好权重**。
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        libgl1 libglib2.0-0 curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app.py .
EXPOSE 8000
CMD ["python", "app.py"]
