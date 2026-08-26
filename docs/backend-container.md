# KB-AI · 后端容器化(v1.5.0)

> **本文档目的**:记录 v1.5.0 把 FastAPI backend 从 host 进程迁入 docker compose 的设计决策 + 当前架构边界 + 未来扩展指引。
> **配套版本**:KB-AI v1.5.0(2026-07-22)
> **维护**:本文档随 docker-compose.yml / docker/backend/Dockerfile / start.bat / stop.bat 变更同步更新

---

## 1. 当前架构(v1.5.0)

### 1.1 容器组成(5 个)

| Service | 类型 | Image Tag | 备注 |
|---|---|---|---|
| qdrant | 官方 | `qdrant/qdrant:v1.7.0` | 锁版 |
| dify-api | 官方 | `langgenius/dify-api:1.0.0` | 锁版 |
| dify-worker | 官方 | `langgenius/dify-api:1.0.0` | 锁版 |
| dify-db-init | **本地构建(v1.4.0+)** | `kb-ai/dify-db-init:local` ← `alpine:3.19` 多阶段 | 已存在 |
| **kb-ai-backend** | **本地构建(v1.5.0+)** | **`kb-ai/backend:local` ← `python:3.12-slim` 多阶段** | **新增** |

**重要边界**:**v1.5.0 仅把后端迁入容器**,Dify 1.5GB 镜像体积 + 冷启动 5-10min **均未改变**(上游问题,我们用官方预构建镜像)。

### 1.2 host 直跑组件(v1.5.0+)

- **MinerU 解析服务**:`backend/mineru_server.py`(host 端 Python 进程,v0.7.1 部署裁剪推迟,镜像源不可用)
- 前端 `frontend/dist/` 由 backend 容器挂载(替代 host 静态挂载)

### 1.3 边界声明(必读)

**v1.5.0 解决的 + 不解决的**:

| 项 | 状态 | 说明 |
|---|---|---|
| 后端从 host 进程迁入 docker compose | ✅ 解决 | 5 service 统一编排 |
| Dify 1.5GB 镜像体积 | ❌ 未解 | 上游镜像本体,我们不重构建 |
| 冷启动 5-10min | ❌ 未解 | Docker Hub 国内拉取 + Dify cold start,需改 daemon.json |
| MinerU 容器化 | ❌ 未解 | v0.7.1 推迟(镜像源不可匿名 pull),候选 v1.6.0 |
| backend/.venv 不再需要 | ✅ 解决 | Dockerfile 直接 `pip install`(wheels) |
| backend `.env` 注入方式 | ✅ 不变 | compose env_from 自动从 `.env` 读 |

---

## 2. v1.5.0 后端 Dockerfile 范式应用

### 2.1 多阶段构建

文件位置:`docker/backend/Dockerfile`(35 行)

```dockerfile
# Stage 1: builder - pip wheel 装依赖
FROM python:3.12-slim AS builder
WORKDIR /build
COPY backend/requirements.txt backend/requirements.txt
RUN pip wheel --wheel-dir=/wheels -r backend/requirements.txt

# Stage 2: runtime - 离线安装 + 源码
FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends curl sqlite3 && rm -rf /var/lib/apt/lists/*
COPY --from=builder /wheels /wheels
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-index --find-links=/wheels -r /app/backend/requirements.txt && rm -rf /wheels
COPY backend/ /app/backend/
HEALTHCHECK --interval=30s --timeout=5s --retries=3 --start-period=20s \
    CMD curl -fsS http://localhost:8000/api/health || exit 1
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000", "--app-dir", "/app"]
```

### 2.2 镜像体积预算

| 组件 | 体积 | 备注 |
|---|---|---|
| python:3.12-slim | ~120MB | Debian 12 slim 基础 |
| 7 deps(fastapi / uvicorn / sse-starlette / pydantic / python-multipart / sentence-transformers)| ~200-250MB | sentence-transformers 含 PyTorch,占大头 |
| backend 源码 | ~5MB | api/ + core/ + main.py + mineru_server.py |
| 系统依赖(curl + sqlite3)| ~10MB | healthcheck + 子进程兼容 |
| **总计** | **≤ 400MB** | **目标 ≤ 350MB** |

**说明**:sentence-transformers 是最大头(~150MB PyTorch 运行时);后续若不需要本地 embedding 模型可换轻量方案。

### 2.3 与 v1.4.0 dify-db-init 的异同

| 维度 | v1.4.0 dify-db-init | v1.5.0 kb-ai-backend |
|---|---|---|
| Base image | alpine:3.19 | python:3.12-slim |
| Builder stage | apk add sqlite | pip wheel -r requirements.txt |
| Runtime stage | (共享 apk) | 离线装 wheels + 拷贝源码 |
| HEALTHCHECK | 无 | `curl /api/health` |
| 镜像大小 | ≤ 15MB | ≤ 400MB |
| 共享数据卷 | `/data`(SQLite WAL init)| `./data /vectors /cache /logs /tmp /frontend/dist` |
| 端口 | 无 | `127.0.0.1:8000:8000` |
| 复杂度 | 一次性 init 任务 | 长跑 FastAPI 服务 |

---

## 3. compose 集成

### 3.1 kb-ai-backend service 关键字段

```yaml
kb-ai-backend:
  build:
    context: .
    dockerfile: docker/backend/Dockerfile
  image: kb-ai/backend:local   # 自定义 tag,避免与 python:3.12-slim 冲突
  container_name: kb-ai-backend
  restart: unless-stopped
  ports:
    - "127.0.0.1:8000:8000"
  volumes:
    - ./data:/data
    - ./vectors:/vectors
    - ./cache:/cache
    - ./logs:/logs
    - ./tmp:/tmp
    - ./frontend/dist:/app/frontend/dist:ro
  environment:
    ALIYUN_BAILIAN_API_KEY: ${ALIYUN_BAILIAN_API_KEY}
    TAVILY_API_KEY: ${TAVILY_API_KEY:-}
    BING_SEARCH_API_KEY: ${BING_SEARCH_API_KEY:-}
    KB_AI_ROOT: /data
    DEPLOY_ENV: production
    LOG_LEVEL: INFO
  healthcheck:
    test: ["CMD", "curl", "-fsS", "http://localhost:8000/api/health"]
    interval: 30s
    timeout: 5s
    retries: 3
    start_period: 20s
  mem_limit: 1g
  mem_reservation: 512m
  cpus: "1.0"
  pids_limit: 200
  networks:
    - kb-ai-net
  depends_on:
    qdrant:
      condition: service_healthy
    dify-api:
      condition: service_healthy
```

### 3.2 数据卷与网络

- **数据卷全部回 U 盘根**:与 v0.7.1 风格一致(相对路径挂载),保证 U 盘拔插后数据完整
- **frontend/dist 只读挂载**:容器内 `/app/frontend/dist`,FastAPI `app.mount("/", StaticFiles(...))` 仍生效
- **kb-ai-net 网络**:与 qdrant / dify-api 互通,backend 可访问 `qdrant:6333` 和 `dify-api:5001`(容器内服务名)
- **127.0.0.1:8000 仅 loopback**:与 v0.7.1 安全加固一致,避免 LAN/公网裸暴露

### 3.3 启动序列(v1.5.0)

```
docker compose up -d         (start.bat 第 4 步)
  ├─ qdrant         (image: qdrant:1.7.0, 官方)
  ├─ dify-api       (image: langgenius/dify-api:1.0.0, 官方)
  ├─ dify-worker    (image: langgenius/dify-api:1.0.0, 官方)
  ├─ dify-db-init   (build: ./docker/dify-db-init, v1.4.0+ 本地)
  └─ kb-ai-backend  (build: ./docker/backend, v1.5.0+ 本地) ← NEW
        ├─ depends_on: qdrant (service_healthy)
        └─ depends_on: dify-api (service_healthy)

start.bat 第 6 步(幂等)
  └─ docker compose up -d kb-ai-backend    (no-op 若已 up)

start.bat 第 7 步(等待 API 就绪)
  └─ 探测 http://localhost:8000/api/health(由 compose port 转发)

host 端 start.bat 第 6 步末段(向后兼容)
  └─ 拉起 MinerU python 进程(host, 不在容器化范围)
```

---

## 4. start.bat / stop.bat 重接

### 4.1 改动点

| 文件 | 步骤 | v1.4.0 | v1.5.0 |
|---|---|---|---|
| start.bat | 第 6 步 | `pwsh scripts\start-backend.ps1` | `docker compose up -d kb-ai-backend` |
| stop.bat | 第 1 步 | `pwsh scripts\stop-backend.ps1` | `docker compose stop kb-ai-backend` |

**MinerU 逻辑保留**(start.bat 第 6 步末段 + stop.bat 第 1 步末段),host 进程路径不变。

### 4.2 scripts\start-backend.ps1 / stop-backend.ps1 保留作为 fallback

**不删除**这两个 ps1 文件,理由:

- 用户可手动跑 `pwsh -File scripts\start-backend.ps1 -Port 8000` 排查 backend 问题
- 容器化路径失败时(failure scenario),host 进程路径仍可工作
- 工具链一致性:不破坏既有调用方

### 4.3 MinerU 不在容器化范围

**决策**:v1.5.0 不容器化 MinerU。

理由:

1. v0.7.1 已明确 MinerU 官方镜像源(opendatalab/mineru)不可匿名 pull
2. compose 文件头注释明确推迟到"找到可匿名 pull 的 MinerU 镜像后"
3. MinerU 容器化属 v1.6.0+ 候选

**host MinerU 进程保留**(start.bat 第 6 步末段 + stop.bat 第 1 步末段)。

---

## 5. 不在 v1.5.0 范围

- **Dify 1.5GB 镜像体积**(上游)
- **冷启动 5-10min**(上游 + Docker Hub 国内拉取)
- **MinerU 容器化**(v0.7.1 推迟)
- **远程 CI**(`known-limitations §5 #1b`,无 git remote,等上 GitHub)
- **COS 异地备份**(`known-limitations §4 #5`,用户决策)
- **PRD P1/P2**(REQ-12/14/15/16/17,本版本不动)
- **Pester 测试 for cost-alert.ps1**(`known-limitations §6 #E`,ROI 太低,候选 v1.6.0)
- **PRD 项目外文件同步**(`<private>/.harness/intake/...`,v1.3.0 延期;v1.5.0 不动)

---

## 6. 未来扩展(v1.6.0+)

| 项 | 候选版本 | 说明 |
|---|---|---|
| MinerU 容器化 | v1.6.0 | 若 MinerU 镜像可获取(private registry / 官方开放匿名 pull) |
| 远程 CI | v1.6.0 | 上 GitHub 后加 `.github/workflows/test.yml`(test_backend_container.py 已就绪) |
| REQ-15 多用户 | v1.7.0+ | 多 kb-ai-backend 实例 + 负载均衡(容器化是基础) |
| 跨平台支持 | v1.7.0+ | Linux/macOS 用户无需 PS;后端已在 Docker,前端可独立部署 |
| 云部署 | 视用户决策 | 当前 U 盘单机部署(用户决策 REQ-9) |

---

*本文档由 v1.5.0 spec §1.3 拆解产出,锁定后变更需经 maintainer 批准。*