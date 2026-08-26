# KB-AI · 故障排查手册(Troubleshooting)

> **怎么用**:先按"现象"找到条目 → 跑诊断命令 → 按步骤修复。
> **拿不准时**:跑 `powershell -File scripts\health-full.ps1`,把整屏截图发给工程师(可定位约 80% 问题)。
> 用户向精简版见 `QUICKSTART.md` §6;本文档覆盖更全,含工程师级恢复流程。

---

## 1. 启动失败

### 1.1 Docker Desktop 未运行
- **现象**:双击 `start.bat` 后卡住或报错 `error during connect` / `pipe/dockerDesktopLinuxEngine`
- **修复**:启动 Docker Desktop,等鲸鱼图标变稳定(约 30 秒)→ 重跑 `start.bat`

### 1.2 端口被占用(8000 / 8080 / 6333)
- **现象**:`docker compose up` 报 `port is already allocated`,或后端启动报 `address already in use`
- **诊断**:
  ```powershell
  netstat -ano | findstr ":8000 :8080 :6333"
  ```
- **修复**:关掉占用进程;Dify 端口冲突可在 `.env` 改 `DIFY_PORT=8081`

### 1.3 首次启动特别慢
- **正常**:首次拉取 Docker 镜像约 1.5 GB,需 5-10 分钟;之后每次 30-60 秒。

### 1.4 后端起来了但 http://localhost:8000 没页面
- **原因**:`frontend/dist/` 构建产物缺失(后端仅在 dist 存在时托管前端,见 `backend/main.py` 尾部)
- **修复**:
  ```bash
  cd frontend && npm install && npm run build
  ```
  再重启后端(`scripts\start-backend.ps1`)。

---

## 2. 配置问题

### 2.1 AI 回答"未配置 API Key"或调用失败
- **诊断**:`.env` 里仍是占位符 `sk-PLEASE-FILL-IN-*`
- **修复**:打开 `.env`,把 `ALIYUN_BAILIAN_API_KEY` 换成真实 Key(`sk-` 开头,申请见 QUICKSTART §2),保存后重试。**不需要重启容器**(每次调用实时读)。

### 2.2 不确定 Key 是否生效
- **诊断**:
  ```powershell
  powershell -File scripts\health-probe.ps1
  ```
  Qwen 是 critical 端点:不可达即整体 OFFLINE;Tavily/Bing 是 optional(只影响联网搜索降级)。

---

## 3. AI 服务异常

### 3.1 OFFLINE(AI 暂不可用)
- **诊断**:能否浏览器打开 https://bailian.console.aliyun.com/(判断本机网络)
- **修复**:网络通但仍 OFFLINE → 等 60 秒重试(限流);持续失败 → 检查阿里云百炼账户额度/欠费

### 3.2 联网搜索不生效
- **现象**:回答里没有最新网络信息
- **原因**:websearch 走 Tavily → Bing 降级链,两个 Key 都是 optional;未填或免费额度(1000 次/月)用尽时自动跳过,属**设计内降级**而非故障
- **诊断**:查 `data\db.sqlite` 的 `degradation_events` 表(记录每次降级事件)

---

## 4. 检索/回答质量问题

### 4.1 回答"找不到相关资料"但文档明明已上传
- **诊断**(工程师):用检索调试端点看全链路哪一环为空:
  ```
  GET http://127.0.0.1:8000/api/debug/retrieval?q=你的问题
  ```
  依次看:关键词命中数 / 向量召回数 / RRF 融合后 / 重排后。
- **常见原因与修复**:
  | 原因 | 修复 |
  |---|---|
  | 文档解析了但没 embed 入库 | 跑 `scripts\embed-and-ingest.ps1` |
  | embedding 模型变更导致向量不一致 | 调 `/api/knowledge/reembed` 重建 |
  | 阈值过滤(score < 0.6) | 换问法;阈值 0.6 为统一决策,勿擅自调低 |

### 4.2 批量入库有失败文件
- **修复**:跑 `scripts\reprocess-failed.ps1`(或 `process-remaining.ps1`),失败清单在 `tmp\batch-parse-status.json`

### 4.3 检索/聊天请求长时间无响应(首次启用或换机后)
- **现象**:chat 或 `/api/debug/retrieval` 请求挂起数分钟无返回(2026-07-17 实测)
- **原因**:Cross-Encoder 重排模型 `BAAI/bge-reranker-base`(~400MB)未缓存,首次使用时实时从 HuggingFace 下载;国内网络直连 `huggingface.co` 会**挂起而非报错**,而 `backend/core/rag/reranker.py` 的优雅降级只兜"加载失败"、兜不住"加载卡住"
- **诊断**:请求加 `rerank_top_n=0` 参数(跳过重排)若秒回,即可确认是重排模型问题:
  ```
  curl "http://127.0.0.1:8000/api/debug/retrieval?question=test&rerank_top_n=0"
  ```
- **修复**(二选一):
  1. **镜像下载**(推荐):设 `HF_ENDPOINT=https://hf-mirror.com` 重启后端,发一次检索请求触发下载,完成后模型缓存在 `%USERPROFILE%\.cache\huggingface`,之后秒级加载
  2. **暂跳重排**:评测/排障时用 `rerank_top_n=0`(检索主链路不受影响,仅少精排)
- **根治建议**(待做):reranker 加载加超时/线程隔离,或启动时预检模型缓存、缺失则禁用重排并写 `degradation_events`

---

## 5. 数据损坏与恢复(最高危)

### 5.1 未跑 stop.bat 直接拔盘 → 下次启动报 SQLite 错误
- **现象**:`database disk image is malformed` / 后端起不来 / 会话历史空白
- **恢复步骤**(用 stop.bat 的自动备份):
  1. 在电脑硬盘打开 `%USERPROFILE%\KB-AI-Backup\`
  2. 找最新的 `kbai-backup-yyyyMMdd-HHmmss.zip`,解压
  3. 把解压出的 `data\` 和 `vectors\` 拷回 U 盘根目录**覆盖**
  4. 重跑 `start.bat`
- **说明**:备份含 `db.sqlite-wal`,SQLite 启动时会自动 replay,最多丢最后一次对话
- **预防**:永远先 `stop.bat` 再拔盘;`stop.bat` 会自动备份(保留最近 7 份)

### 5.2 备份目录想换位置
- 在 `.env` 加 `KBAI_BACKUP_DIR=D:\backups\kbai`,或手动跑:
  ```powershell
  powershell -File scripts\backup.ps1 -BackupDir 'D:\backups\kbai' -Keep 14
  ```
- **注意**:备份到同一块 U 盘没有意义(盘坏 = 备份同归于尽),脚本对此有守卫告警

### 5.3 建议:每季度做一次恢复演练
- 按 §5.1 步骤实际走一遍,确认 zip 能解、拷回能启动。**未验证过的备份等于没有备份**。

---

## 6. 容量告警

- **诊断**:`powershell -File scripts\disk-alert.ps1`
- **等级**:0 绿(正常)→ 1-2 黄(建议清理)→ 3+ 红(禁止新增文档)
- **清理顺序**:`tmp\` 临时文件 → `logs\` 旧日志 → `data\uploads\` 已入库的原始文件(确认 vectors 已建后可清)

---

## 7. 工程师自检清单

```powershell
# 1. 一屏健康度(版本/容器/AI/容量/数据)
powershell -File scripts\health-full.ps1
# 2. 全部命令速查
powershell -File scripts\show-help.ps1
# 3. mock 回归(无需 Docker)
pwsh -File tests\e2e_test.ps1
# 4. 后端单测
backend/.venv/Scripts/python -m pytest tests/unit/ -v
# 5. 容器实况
docker compose ps
# 6. 日志
#    logs\mineru_server.log · logs\dify-api\ · logs\dify-worker\
```

---

*最后更新:2026-07-17(v0.8.6,随 G5 文档批新增)*
