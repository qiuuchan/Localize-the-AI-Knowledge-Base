# KB-AI · Docker 构建范式

> **本文档目的**:记录 v1.4.0 引入的多阶段构建范式 + 当前架构边界 + 未来扩展指引。
> **配套版本**:KB-AI v1.4.0(2026-07-22)
> **维护**:本文档随 docker-compose.yml / Dockerfile / .dockerignore 变更同步更新

---

## 1. 当前架构(v1.4.0)

### 1.1 容器组成

| Service | 类型 | Image Tag | 备注 |
|---|---|---|---|
| qdrant | 官方 | `qdrant/qdrant:v1.7.0` | 锁版 |
| dify-api | 官方 | `langgenius/dify-api:1.0.0` | 锁版 |
| dify-worker | 官方 | `langgenius/dify-api:1.0.0` | 锁版 |
| dify-db-init | **本地构建(v1.4.0+)** | `kb-ai/dify-db-init:local` ← `alpine:3.19` 多阶段 | 新增 |

### 1.2 host 直跑组件(不进容器)

- FastAPI backend:`scripts/start-backend.ps1` 启 `backend/.venv/Scripts/python -m uvicorn`
- MinerU parser:`backend/mineru_server.py`(host 端 Python 进程)
- Frontend:`frontend/dist/` 由 FastAPI 挂载到 `:8000`

### 1.3 边界声明(必读)

**当前架构无可"多步优化"的源码**:

- backend / frontend / mineru 全部 host 直跑,**无 Dockerfile 可构建**
- 1.5GB 镜像体积来自 `langgenius/dify-api:1.0.0` 官方镜像本体,我们无法减小
- 冷启动 5-10min 的真正瓶颈是 **Docker Hub 国内拉镜像延迟**(改 `~/.docker/daemon.json` 的 `registry-mirrors` 可缓解,非本文档范围);dify-api 内部 cold start 需改 Dify 1.0 启动逻辑,我们也无源码
- v1.4.0 **不解决**以上任何一项;仅落地多阶段构建**范式样本** + `.dockerignore` 范本 + 本文档

---

## 2. v1.4.0 范式样本

### 2.1 dify-db-init 多阶段 Dockerfile

文件位置:`docker/dify-db-init/Dockerfile`(16 行, post-fix `c8f5b83`)

```dockerfile
FROM alpine:3.19 AS builder
RUN apk add --no-cache sqlite

FROM alpine:3.19
RUN apk add --no-cache sqlite
```

**功能等价性(v1.4.0 post-review fix)**:`dify-db-init` runtime 阶段保留 `RUN apk add --no-cache sqlite`,确保 sqlite3 二进制 + 共享库(libreadline.so.8 / libsqlite3.so.0 / libncurses 等)同时装入。多阶段 builder 阶段用作 paradigm 演示 + cache 复用验证;runtime `apk add` 是功能性必需,不能省略。

**compose 集成**:见 `docker-compose.yml` dify-db-init service:
```yaml
dify-db-init:
  build:
    context: ./docker/dify-db-init
    dockerfile: Dockerfile
  image: kb-ai/dify-db-init:local
  # ... 其余字段不变
```

### 2.2 未来扩展路径(backend 容器化,伪代码示例)

> ⚠️ **非 v1.4.0 范围**;以下为示意,等用户决策后再实施。

```dockerfile
# 伪代码,展示未来 backend Dockerfile 结构(不实现)
FROM python:3.12-slim AS builder
WORKDIR /app
COPY backend/requirements.txt .
RUN pip wheel --wheel-dir=/wheels -r requirements.txt

FROM python:3.12-slim AS runtime
WORKDIR /app
COPY --from=builder /wheels /wheels
COPY backend/requirements.txt .
RUN pip install --no-index --find-links=/wheels -r requirements.txt
COPY backend/ .
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**关键收益**(若未来实施):

- requirements 变更 → 只重建 builder + runtime 的 wheel install 两层,复用源代码 layer(qualitative: 加速日常依赖更新)
- builder stage 装 pip 构建工具, runtime stage 仅含 wheel 缓存 + 应用代码(qualitative: 减小最终镜像体积)
- 应用源代码 layer 在依赖不变时可完全命中缓存(qualitative: 加速常规迭代)

---

## 3. `.dockerignore` 范本

根 `.dockerignore` 已就位(2026-07-22 落),关键排除规则:

| 模式 | 排除目标 |
|---|---|
| `data/` / `vectors/` / `cache/` / `logs/` / `tmp/` | 运行时数据卷 |
| `backend/.venv/` / `frontend/node_modules/` | 虚拟环境 |
| `frontend/dist/` | 已构建的前端产物 |
| `.env` / `.env.example` / `.env.local` | 凭据(绝不能进镜像) |
| `*.sqlite` / `*.gz` / `*.zip` / `*.tar` / `*.log` | 大文件 |
| `*.md` 默认 + `README.md` / `QUICKSTART.md` 显式保留 | 文档 |

完整内容见仓库根 `.dockerignore`。

---

## 4. 不在 v1.4.0 范围(明确推迟)

- 1.5GB 镜像体积优化(需改 Dify 1.0 源码或换 registry mirror)
- 冷启动 5-10min 加速(需改 Dify 1.0 启动逻辑或配置 `~/.docker/daemon.json` 的 `registry-mirrors`)
- backend / frontend 容器化(见 §2.2 扩展路径,等用户决策)
- COS 异地备份(`known-limitations.md §4 #5`,用户决策)
- 远程 CI(`§4 #1b`,无 git remote)
- Pester 测试(`§6 #E`,为单一脚本建立框架 ROI 太低,推 v1.4.0+ 候选)

---

## 5. 参考

- spec:`docs/superpowers/specs/2026-07-22-v1.4-dockerfile-paradigm-design.md`
- plan:`docs/superpowers/plans/2026-07-22-v1.4-dockerfile-paradigm.md`
- Dockerfile 多步构建 TODO:`docs/known-limitations.md §4 #3`(v1.4.0 关闭)
