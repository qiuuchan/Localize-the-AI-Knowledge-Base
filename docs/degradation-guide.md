# KB-AI · 降级与故障自愈手册

> **怎么用**:遇到 🟡 / 🔴 状态条或 AI 回答异常时,按本手册对应章节排查。
> **配套**:`docs/troubleshooting.md` 覆盖通用故障(端口冲突 / Docker 启动失败等);本文档**专门聚焦降级场景**(系统部分功能失效但仍可工作)。
> **状态条语义**:🟢 在线 / 🟡 降级 / 🔴 离线 / ⚪ 检测中
> **最新更新**:2026-07-21 · 配套 KB-AI v1.3.0(新增 §"cost-alert 阻断时知识库检索仍可用"场景)

## 1. 降级场景一览

| 触发条件 | 现象 | 自动降级行为 | 用户感知 |
|---|---|---|---|
| 知识库召回为空 | AI 不知道 | 自动 websearch 兜底,标注"来源:网络" | 🟡 顶部状态条:「已换用备用方式为您查找」 |
| Qwen 3.6-Plus 失败 | 路由失败 | L0→L1→L2→L3 自动降级(改用 Max 或备用) | 🟡 短暂降级条 |
| Qwen 全部重试失败 | AI 调用失败 | SSE `error` 事件,前端展示 | 🔴 顶部状态条:「AI 调用失败」 |
| Qdrant 容器挂 | 检索整体失败 | 降级到 keyword-only 或报错 | 🟡/🔴 视严重度 |
| MinerU 服务挂 | PDF/PPT 无法解析 | `.txt` `.md` 仍可上传(plain reader) | 🟡 上传时报错"PDF 解析失败" |
| Tavily/Bing 欠费 | websearch 失败 | 直接返回"知识库没找到",不联网 | 🟡 不影响主功能 |
| Embedding API 超时 | 入库失败 | 上传任务标记 failed,前端显示 | 🟡 单文档失败,其它继续 |
| 一小时前开始的处理任务 | 进程已崩 | 启动时自检,标记 failed + 写 degradation_events | 🟢 用户无感,后台修复 |

## 2. 降级状态如何查看

### 2.1 顶部状态条(最快)

对话页顶部,实时显示:
- **🟢 在线**:无任何降级
- **🟡 降级**:有降级事件但核心功能可用
- **🔴 离线**:核心功能不可用

### 2.2 Dashboard 24h 降级聚合(精细)

`http://localhost:8000/` → 顶 nav「系统」→ "24h 降级事件"卡片:

按组件聚合的条形图,各 component 取值:
- **LLM**:模型调用失败 / 切换备用
- **Embedding**:向量化失败
- **Qdrant**:向量数据库操作失败
- **Reranker**:重排模型失败(自动降级到 RRF 顺序)
- **Retrieval**:整体检索失败
- **Vector / Keyword**:单腿失败
- **Websearch**:联网搜索失败
- **Processing**:启动自检发现的孤儿任务

### 2.3 degradation_events 表(原始)

```sql
sqlite3 data/db.sqlite "SELECT component, COUNT(*) FROM degradation_events WHERE created_at >= datetime('now', '-24 hours') GROUP BY component"
```

## 3. 常见降级场景的处理

### 3.1 🟡 顶部状态条:「已换用备用方式为您查找」

**原因**:知识库未召回任何文档,自动触发了 websearch。
**是否需要修**:**不需要**。这是设计行为。
**怎么办**:
1. 看 AI 回答是否标注「来源:网络」(区分知识库回答 vs 联网回答)
2. 如果回答错了,点开回答下方的引用角标 → 看是知识库来源还是网络来源
3. 若频繁出现,可能是知识库文档不足 → 用关键词搜索 KnowledgePage 检查文档数

### 3.2 🔴 顶部状态条:「AI 调用失败」

**原因**:Qwen 模型 L0→L1→L2→L3 4 级重试全部失败。
**常见触发**:
- 阿里云百炼 API key 失效或欠费
- 网络断开 / 阿里云端点不可达
- 罕见:模型服务故障

**怎么办**:
1. 看 Dashboard degradation 卡 → component=LLM 的事件数
2. **首先**:访问 https://bailian.console.aliyun.com/ 检查账号余额 / API key 状态
3. **其次**:跑 `pwsh -File scripts\health-probe.ps1` 看 3 端点可达性
4. **最后**:若阿里云 OK 但 KB-AI 仍报错,跑 `pwsh -File scripts\health-full.ps1` 把整屏截图发给工程师

### 3.3 🟡 状态条:「网络连接断了，AI 暂时回答不了」

**原因**:完全离线 → 所有降级路径失效。
**还能做什么**:
- ✅ **翻历史对话**:`左滑抽屉` 按钮 → 历史会话可读
- ✅ **翻本地资料**:`资料库` 页 → 浏览已入库文档
- ❌ 新对话 / 新检索 / 上传 — 全部不可用

**恢复**:联网后会自动恢复;无需手动操作。

### 3.4 🟡 上传报错"PDF/PPT 解析失败"

**原因**:MinerU 服务挂了。
**怎么办**:
1. 看顶 nav「系统」→ "端点健康"卡片 → 检查 mineru 端点
2. **重启 MinerU**:`stop.bat` → `start.bat`(会重新拉起 mineru)
3. **临时方案**:在 MinerU 恢复前,可上传 `.txt` `.md` `.docx` 文件(走 plain reader)
4. **不影响**:已入库的 PDF 仍可检索

### 3.5 🟡 上传任务卡显示"入库校验异常"

**原因**:`data/db.sqlite` 写入失败(权限/磁盘满/U 盘拔出)。
**怎么办**:
1. 检查 U 盘是否还插着(`我的电脑` 看 AIAssistant 卷标)
2. 检查磁盘空间:`pwsh -File scripts\disk-alert.ps1` → 5 级告警
3. 若磁盘满:**删除 `vectors\.deleted\`** 目录(Qdrant 待 GC 的点)

### 3.6 🟢 偶尔出现一条降级事件

**原因**:阿里云端点偶发抖动;L0→L1 自动切换成功。
**需要修吗**:**不需要**,自动降级就是为这种场景设计的。

## 4. 降级开关(给高级用户)

`.env` 文件中:
```ini
# 关闭自动 websearch 降级(强制只用知识库)
SKIP_WEBSEARCH=1

# 调高/调低 websearch 触发阈值(默认 0.6)
SCORE_THRESHOLD=0.5

# 关闭重排(加速但牺牲精度)
RERANK_TOP_N=0
```

修改后需 `stop.bat && start.bat` 重启后端生效。

## 5. 降级台账查询(高级 / 工程师)

### 5.1 SQLite 直接查

```bash
sqlite3 data/db.sqlite
> SELECT datetime(created_at), component, source, reason
  FROM degradation_events
  ORDER BY id DESC LIMIT 20;
```

### 5.2 启动时自检

每次启动 `start.bat`,后端会自动跑一次 `recover_orphans()`:
- 扫描 `processing_state WHERE status='processing' AND updated_at < now-600s`
- 标记为 failed + 写一条 `component='Processing'` 的降级事件
- 在 `/api/boot` SSE 的 `orphan_recovery` 阶段可见

## 6. 降级事件 → 后端日志对照

每条降级事件在后端 stdout/stderr 都有对应 logger.warning。日志位置:
- `logs/dify-api/`
- `logs/dify-worker/`

例:`grep "degradation" logs/dify-api/*.log` 可定位具体失败原因。

---

## §7 · cost-alert 阻断时知识库检索仍可用(v1.3.0 新增)

**触发条件**:本月用量 ≥ `.env` 中 `COST_ALERT_THRESHOLDS=block`(默认 ¥1500)。

**现象**:
- `/api/chat` 返回 **HTTP 200**(SSE 连接保持打开),在 SSE 流中 yield `event: error, data: {reason: "monthly_cost_exceeded", month_yuan, threshold, hint}`。**不是** HTTP 503(EventSourceResponse 已启动后无法再抛 HTTPException;前端必须监听 `event: error` 而非依赖 HTTP 状态码)。
- Dashboard 「本月用量」卡片 level=3 红色满格 + 顶部红色告警 banner
- degradation_events 表写入 `component='LLM'` + `reason='cost-alert block: ¥<amount>'`

**降级路径**:
1. **知识库检索仍可用**:用户可在 Dashboard / KnowledgePage 翻历史 / 浏览文档(不依赖 `/api/chat`)
2. **手动调整阈值**:改 `.env` 中 `COST_ALERT_THRESHOLDS` 重新调低 block 阈值,然后跑 `pwsh -File scripts/cost-alert.ps1` 重新 rollup

**恢复**:
- 下月 1 日 UTC 00:00 自动重置(`cost-alert.ps1` 按 UTC 自然月切月,新月份 month_yuan 重算)
- 或手动 `pwsh -File scripts/cost-alert.ps1 -Month "2026-08"`(强制指定月份)
- 或调低 `.env` 阈值后手动 rollup

**诊断**:
```bash
# 看 health_status.json 当前 cost_alert 字段
cat data/health_status.json | python -c "import json,sys; d=json.load(sys.stdin); print(json.dumps(d.get('cost_alert',{}), ensure_ascii=False, indent=2))"

# 看本月 token 用量
wc -l data/cost_log.jsonl  # 总行数 ≈ 总调用次数

# 强制重新 rollup
pwsh -File scripts/cost-alert.ps1
```

**预防**:
- `level=1`(month_yuan ≥ warn)→ Dashboard 黄色提示
- `level=2`(≥ high)→ Dashboard 橙色 banner
- `level=3`(≥ block)→ 阻断 LLM
- 建议:level=2 时联系 maintainer 评估是否调高阈值或暂停使用

---

*本手册覆盖 v1.3.0 已实现的全部降级路径;v1.4 待补:Fallback reasoning(降级时告诉用户具体原因)、Qdrant 离线时的 keyword-only 模式文档。*