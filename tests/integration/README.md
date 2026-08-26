# KB-AI · 集成测试 (tests/integration/)

> v0.7.1 引入 — 对应架构评审 Part 2 §9.2 #6,把测试从 mock-only 升级到真容器。

## 与 tests/test_m\*.ps1 的区别

| 维度 | tests/test_m\*.ps1 | tests/integration/ |
|---|---|---|
| 起容器 | ✗ 纯 mock | ✓ `docker compose up -d --wait` |
| 调 API | ✗ mock 端点 | ✓ 真实 Qwen / Qdrant / Dify |
| 网络 | ✗ 离线 | ✓ 真实 LAN/internet |
| 耗时 | 秒级 | 分钟级(首次含镜像拉取) |
| 触发方式 | `npm test` 类 | 部署后 / CI nightly |

mock 测试适合 PR 阶段拦截回归,integration 测试适合 release 前真实环境验收。

## 当前用例

### smoke-chat.ps1

跑通「docker compose 真起 5 容器 → chat.ps1 调 Qwen → 校验返回非空中文」。

```powershell
# 默认(探测当前脚本 grandparent 为 KB-AI 根)
powershell -File tests/integration/smoke-chat.ps1

# E 盘部署验证
powershell -File tests/integration/smoke-chat.ps1 -RootDir "E:\KB-AI"

# 不自动清理,留容器供人查
powershell -File tests/integration/smoke-chat.ps1 -SkipCleanup

# 调长 compose 超时(冷启动拉镜像)
powershell -File tests/integration/smoke-chat.ps1 -ComposeTimeoutSec 600
```

### hybrid-search.ps1(v0.7.2)

验证 Hybrid Search 全链路:生成测试 chunks → embed-and-ingest 入库(Qdrant + SQLite keyword_index) → chat.ps1 默认 Hybrid 问答 → 断言召回 `menu.md` 且中文未乱码,并对比 `-DisableHybrid` 纯向量模式。

```powershell
# 默认(探测当前脚本 grandparent 为 KB-AI 根;仅依赖 Qdrant)
powershell -File tests/integration/hybrid-search.ps1

# E 盘部署验证
powershell -File tests/integration/hybrid-search.ps1 -RootDir "E:\KB-AI"

# 保留测试 collection 供人工检查
powershell -File tests/integration/hybrid-search.ps1 -SkipCleanup
```

### 退出码

| code | smoke-chat.ps1 | hybrid-search.ps1 |
|---|---|---|
| 0 | 全部通过 | 全部通过 |
| 1 | 前置条件失败(无 Docker / 无 API Key) | 前置条件失败(无 Docker / 无 Key / Qdrant 不可达) |
| 2 | 容器未起 / 不 healthy | embed-and-ingest 入库失败 |
| 3 | chat.ps1 调用失败 / 返回空 / 无中文 | Hybrid 未召回预期 chunk / 中文乱码 |
| 4 | 测试自身崩溃 | 纯向量对比失败 |
| 5 | - | 测试自身崩溃 |

## 前置条件

1. **Docker Desktop 运行中** — `docker version` 不报连接失败。
2. **.env 中 ALIYUN_BAILIAN_API_KEY 是真实 Key** — 不能是 `sk-PLEASE-FILL-IN` 等占位符。
3. **当前机器可达阿里云百炼 API 端点** — 否则 Qwen 调用会失败(限流 / 余额 / 区域不可达)。
4. **足够的磁盘空间** — 5 容器镜像 ~3-4 GB,运行时数据 ~1 GB。

## 设计选择

- **不引入 docker-compose.test.yml**:直接复用根目录 docker-compose.yml,v0.7.1 已加固(127.0.0.1 bind + 资源限制 + SQLite WAL)。
- **不引入 testcontainers 库**:依赖最少的 PowerShell + 原生命令,符合 KB-AI "低依赖、单机"定位。
- **中文断言用 Unicode 范围 `[\u4e00-\u9fff]`**:与 PRD 中"中文为本"对齐,不依赖具体回复内容(避免 LLM 答非所问的脆弱断言)。

## 未来扩展

- ✅ `hybrid-search.ps1`(v0.7.2 已实现) — 验 Qdrant + keyword_index + RRF + LLM 全链路
- `embedding-pipeline.ps1` — 验 parse-doc + embed-and-ingest 真链路(PDF → chunks)
- `rag-retrieval.ps1` — 上传 1 份示例 PDF,验 top-K 检索命中
- `multi-turn.ps1` — 验 SessionId 跨轮记忆 + SQLite sessions.db
- `websearch-fallback.ps1` — top-K 全 < 0.6 → Tavily/Bing 兜底

每个用例独立 .ps1,失败时给出明确退出码定位失败阶段。

## 不在范围内

- **CI 集成**:v0.7.1 暂不引入 GitHub Actions(架构评审 §9.3 #11 标记为低优先级)。
- **回归 mock 测试**:test_m\*.ps1 / e2e_test.ps1 继续保留,作为快速回归。