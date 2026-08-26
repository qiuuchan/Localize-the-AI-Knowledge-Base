# KB-AI v1.5.1 · 后端多阶段构建(包含 v1.5.0 hotfix)
# 目的:把 FastAPI backend 从 host 进程迁入 docker compose
# v1.5.1 hotfix:
#   - CPU-only torch(14.2GB → ~1.5GB):pip install --index-url pytorch cpu wheels
#   - Linux PowerShell(~150MB):backend/api/health.py 调 ps_runner 需 pwsh
# 基础镜像:python:3.12-slim(与 .python-version 锁定的 3.12.6 兼容)
# 范式来源:v1.4.0 spec §2.2 伪代码示例
# 边界:不解决 Dify 1.5GB / 冷启动 5-10min(上游问题);见 docs/backend-container.md §1

# === Stage 1: builder ===
# 把 backend/requirements.txt 装成 wheels,验证 pip cache + layer 复用
# v1.5.1 hotfix:--index-url=pytorch-cpu(主)+ --extra-index-url=pypi(补充)
#   这样 fastapi/uvicorn 从 PyPI 拿,torch 从 PyTorch CPU 索引拿(CPU-only)
FROM python:3.12-slim AS builder
WORKDIR /build
COPY backend/requirements.txt backend/requirements.txt
RUN pip wheel --wheel-dir=/wheels \
    --index-url https://download.pytorch.org/whl/cpu \
    --extra-index-url https://pypi.org/simple \
    -r backend/requirements.txt

# === Stage 2: runtime ===
# 从 wheels 离线安装 + 拷贝 backend 源码,最终镜像仅含运行所需
FROM python:3.12-slim
WORKDIR /app

# 系统依赖
# - curl:healthcheck 用
# - sqlite3:ps/sqlite 子进程兼容
# - libicuXX:PowerShell Linux 运行时需要(版本随 Debian 变;bookworm=72, trixie=74)
# - wget + ca-certificates:下载 PowerShell tarball 用
# libicu 自动检测:apt-cache search 输出 "包名 - 描述" 格式,先取第一列(包名)
RUN apt-get update && \
    LIBICU_PKG=$(apt-cache search '^libicu7[0-9]' 2>/dev/null | head -1 | awk '{print $1}') && \
    echo "Detected libicu package: ${LIBICU_PKG}" && \
    apt-get install -y --no-install-recommends \
        curl sqlite3 wget ca-certificates "${LIBICU_PKG}" && \
    rm -rf /var/lib/apt/lists/*

# 安装 PowerShell(Linux 7.4 LTS,从 GitHub release 直链下载 tarball,无需 repo)
# 替代方案:apt 装 powershell 包(需 Microsoft 官方 repo,在受限网络下不可靠)
# 参考:https://learn.microsoft.com/en-us/powershell/scripting/install/install-other-linux
# 版本锁定:7.4.0(LTS 首版,最大概率 GitHub release 仍存在;若失效可手动 bump)
ARG PWSH_VERSION=7.4.0
RUN mkdir -p /opt/microsoft/powershell/7 && \
    wget -q "https://github.com/PowerShell/PowerShell/releases/download/v${PWSH_VERSION}/powershell-${PWSH_VERSION}-linux-x64.tar.gz" -O /tmp/pwsh.tar.gz && \
    ls -la /tmp/pwsh.tar.gz && \
    tar xzf /tmp/pwsh.tar.gz -C /opt/microsoft/powershell/7 && \
    chmod +x /opt/microsoft/powershell/7/pwsh && \
    ln -s /opt/microsoft/powershell/7/pwsh /usr/local/bin/pwsh && \
    pwsh --version && \
    rm /tmp/pwsh.tar.gz

# 离线装依赖(从 builder stage 拉 wheels)
# v1.5.1 hotfix:wheels 已含 CPU torch(由 builder stage 用 pytorch-cpu 索引装)
# runtime 仅 --no-index --find-links 即可,不需 extra-index-url
COPY --from=builder /wheels /wheels
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-index --find-links=/wheels \
    -r /app/backend/requirements.txt && \
    rm -rf /wheels

# 拷贝 backend 源码
COPY backend/ /app/backend/

# 健康检查端点(/api/health)
HEALTHCHECK --interval=30s --timeout=5s --retries=3 --start-period=30s \
    CMD curl -fsS http://localhost:8000/api/health || exit 1

# 启动 uvicorn:监听 0.0.0.0:8000(由 compose 端口映射到 127.0.0.1:8000)
# --app-dir /app 让 backend 包导入解析为 /app/backend/main.py
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000", "--app-dir", "/app"]