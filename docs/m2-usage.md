# KB-AI · M2a 用法说明(给非技术用户)

> **文档版本**:v1.0 · 2026-07-01 · 配套 M2a 核心 MVP 阶段 1
> **目标读者**:餐饮分公司老总 / 业务负责人(非 IT 背景)
> **预计阅读**:5 分钟上手

---

## 这是什么?

M2a 是一个 **"问 AI,它帮你找资料原文"** 的本地工具链。你问一句经营问题,它会:

1. 在你 U 盘里的资料中检索最相关的 5 段
2. 用 Qwen3.6-Plus 模型根据这些资料生成答案
3. 每条结论后面带 `[1] [2]` 角标引用,末尾列出"参考资料"

数据全部在你 U 盘上,只有"向阿里云发一句话问 AI"这一步会上网。

---

## 30 秒入门(三个脚本)

### 第 1 步:确认 .env 已填好阿里云百炼 API Key

打开 U 盘根目录 → 用记事本打开 `.env` → 找到 `ALIYUN_BAILIAN_API_KEY=...` 这一行,把你的 Key 粘进去(以 `sk-` 开头)。

> **没填 Key?** 你可以打开命令行跑 `powershell -File .harness\intake\test-api-key.ps1`(环境变量 `$env:ALIYUN_KEY` 临时设 key)先测试一下 Key 是否有效。

### 第 2 步:启动 Dify + Qdrant(如果还没起)

双击 `start.bat`。等 60-90 秒,浏览器自动打开 `http://localhost:8080`。看到 Dify 登录页就说明启动成功。

### 第 3 步:放示例资料 + 跑通

把一个或多个 `.docx` / `.pdf` / `.pptx` / `.xlsx` 文件拖进 `data\samples\` 文件夹。

然后在 U 盘根目录打开 PowerShell(在文件夹空白处按住 Shift + 右键 → "在此处打开 PowerShell 窗口"),跑:

```powershell
pwsh -File scripts\seed-sample-data.ps1
```

它会自动:

- 把示例数据(如果 `data\samples\` 是空的)生成一份"餐饮经营手册"
- 解析 → 切分 → 向量化 → 写入 Qdrant
- 跑一个示例问答演示

跑完后看屏幕输出,应该看到 "示例数据 seed 完成"。

### 第 4 步:开始问问题

```powershell
pwsh -File scripts\chat.ps1 -Question "招牌菜红烧肉怎么做?" -Collection "kb_ai_chunks"
```

回答会带 `[1]` `[2]` 角标,屏幕下半部分显示"参考资料"清单(文档名 + 段落位置)。

---

## 三个脚本分别做什么?

| 脚本 | 何时用 | 做什么 |
|---|---|---|
| `scripts\parse-doc.ps1` | 你想手动解析一个文件 | 把 `.docx/.pdf/.pptx/.xlsx` 切成 markdown 段落,写入 `cache\parsed\<doc-id>\chunks.jsonl` |
| `scripts\embed-and-ingest.ps1` | 你想手动把已切分的 chunks 入库 | 调阿里云 Qwen3-Embedding 把文本变成向量,批量写入 Qdrant(默认 `kb_ai_chunks` collection) |
| `scripts\chat.ps1` | 你想直接问 AI | 把你的问题 → 向量化 → Qdrant 检索 top-5 → Qwen3.6-Plus 生成 + 加脚注引用 |
| `scripts\seed-sample-data.ps1` | 首次部署 / 验证流程 | 一键跑通"放示例 → 解析 → 入库 → 演示问答" |

> 平时用:有 `chat.ps1` 就够;资料更新用 `parse-doc` + `embed-and-ingest`;新机器部署用 `seed-sample-data`。

---

## 关键前提(必看)

### 1. 阿里云百炼 API Key 必须填

`.env` 文件里 `ALIYUN_BAILIAN_API_KEY=sk-...` 必须是真实有效的 Key(不是 `sk-PLEASE-FILL-IN-...` 占位符)。

**没填 = 跑不通。**脚本会在第一步就报错退出。

### 2. 单模型:Qwen3.6-Plus

M2a 锁版决策:只用 Qwen3.6-Plus,**不**自动切到 Qwen3.7-Max,**不**支持图片理解,**不**支持 websearch 降级。这些功能留给 M2b / M3。

### 3. 容器要先起来

跑任何脚本前,Docker Desktop 必须开,Qdrant 容器必须 healthy(否则 `chat.ps1` 会说"Qdrant 不可达")。`start.bat` 会帮你起。

### 4. Windows 10/11

只测试 Windows;macOS / Linux 理论上可跑但没测试,出问题请回 Windows。

---

## 常见错误

| 报错 | 原因 | 修复 |
|---|---|---|
| `ALIYUN_BAILIAN_API_KEY 未填` | `.env` 里还是占位符 | 记事本打开 `.env`,把 `sk-PLEASE-FILL-IN-...` 换成你的真实 Key |
| `Qdrant 不可达` | docker compose 没起 / 端口被占用 | 双击 `start.bat` 重启;检查端口 6333 没被其他程序占 |
| `Embedding 调用失败(401)` | Key 错或失效 | 重新去阿里云百炼控制台拿 Key |
| `Embedding 调用失败(404)` | 模型 id 错 | 检查脚本里 `text-embedding-v3` 是不是被改过 |
| `找不到 pandoc / python` | 解析 .docx 或 .pptx 需要外部工具 | 安装 pandoc(https://pandoc.org/)和 Python 3.10+;PDF / PPTX 优先走 MinerU 容器 |

---

## 下一步

- 想加 **多轮对话记忆**(问第 2 句时 AI 记得前面聊的)?等 M2b。
- 想加 **图片理解**(上传店面照片问"这个摆盘对不对?")?等 M3。
- 想加 **自动从网搜索补资料**(资料里没有时去网上找)?等 M2b。

现在 M2a 已经能让您把资料喂进去、提问并拿到带脚注的回答,这是 MVP 的核心闭环。

---

# M2b · 多轮对话记忆 + 反问/出题 + websearch 降级 + 离线 UX

> **文档版本**:v2.0 · 2026-07-01 · 配套 M2b 阶段(在 M2a 单轮基础上升级)
> **目标读者**:餐饮分公司老总 / 业务负责人(非 IT 背景)
> **预计阅读**:3 分钟上手

## 这是什么?

M2b 在 M2a 单轮 RAG 基础上加了 4 个能力:

1. **多轮对话记忆** — AI 记得你前面聊过的(同会话内,最多 50 轮)
2. **AI 反问/出题** — 你问题写得不清楚时,AI 会反问 1 轮(最多 2 轮);或者出 2-5 个选项给你勾
3. **知识库未命中 → 自动 websearch** — 资料里没找到时,自动去网上找(标注"来源:网络")
4. **离线 UX** — 断网时 AI 提示"暂时不可用",但本地知识库检索仍可用

数据全部在你 U 盘上,只有"问 AI"和"搜网络"这两步会上网。

## 三个新脚本

| 脚本 | 何时用 | 做什么 |
|---|---|---|
| `scripts\chat.ps1` (带 `-SessionId`) | 你想多轮对话 | 用 `-SessionId` 参数;首次不传自动生成 UUID,后续传相同 ID 续接 |
| `scripts\health-probe.ps1` | 系统/手动跑 | 探测 Qwen + Tavily + Bing 是否在线;写 `./data/health_status.json` |
| `scripts\websearch.ps1` | 内部调用(用户通常不直接用) | Tavily → Bing → 失败返回 null;chat.ps1 自动调用 |

## 用法 · 三种模式

### 模式 1:单轮(M2a 旧用法,仍然兼容)

```powershell
pwsh -File scripts\chat.ps1 -Question "招牌菜红烧肉怎么做?" -Collection "kb_ai_chunks"
```

行为:和 M2a 完全一样 — 不带 session,不带记忆。

### 模式 2:多轮对话(自动建会话)

```powershell
# 第 1 次:问 Q3 营收怎么样
pwsh -File scripts\chat.ps1 -SessionId "" -Question "Q3 营收怎么样?"
# 输出末尾会显示 SessionId=<uuid>,复制它

# 第 2 次:继续追问
pwsh -File scripts\chat.ps1 -SessionId "<上面那个 uuid>" -Question "具体下滑多少?"
# AI 记得你刚才问了 Q3 营收
```

或者用 `chat.ps1 -SessionId` 参数自动管(下次升级会包成菜单式 UI)。

### 模式 3:自动 websearch 兜底

```powershell
# 知识库里没有的资料(比如行业最新动态)
pwsh -File scripts\chat.ps1 -Question "2026 年餐饮行业最新趋势是什么?"
# 内部:top-K 全 < 0.6 → 自动调 Tavily/Bing → 返回 + 标"来源:网络"
```

如果不想用自动 websearch,加 `-SkipWebsearch` 参数。

### 离线模式(断网时)

正常情况下 `health-probe.ps1` 由系统调度每 30s 跑一次,写到 `./data/health_status.json`。
如果 `chat.ps1` 启动时读到 `online=false`,会:

- 跳过 Qwen 调用(避免超时)
- 返回本地缓存的 chunks(数据在 U 盘,不依赖网络)
- 提示 "AI 暂时不可用,知识库检索仍可用"

## .env 新增两项(M2b 才需要)

```
TAVILY_API_KEY=tvly-PLEASE-FILL-IN    # 留空 = 跳过 Tavily,只走 Bing
BING_SEARCH_API_KEY=PLEASE-FILL-IN    # 留空 = 都跳过,AI 兜底"暂不可用"
```

> **没填?** 也能用 — 知识库命中时一切正常;只有命中不到 + 自动 websearch 才受影响。

## 三种回答类型(JSON 输出)

`chat.ps1` 现在支持 3 种回答类型(LLM 通过 prompt 自决定):

```json
{"type": "answer",        "content": "...", "citations": [1, 2]}
{"type": "clarify",       "question": "我在尝试理解 X,你是不是想 Y?"}
{"type": "multi_choice",  "options": ["选项 A", "选项 B", "选项 C"]}
```

- **answer**:普通带脚注的回答(默认)
- **clarify**:反问(最多 2 轮,LLM 自决定)
- **multi_choice**:出 2-5 个选项让你勾

前端(Dify / Web UI)解析 `type` 字段决定渲染哪种 UI。

## 关键约束(M2b 锁版决策)

- ✅ 单模型 **Qwen3.6-Plus**(不是 Qwen3.7 Max)
- ✅ 多轮记忆用 **SQLite**(`./data/sessions.db`),**不在 Qdrant**
- ✅ 50 轮软上限(超过仍继续但不严格记住)
- ✅ 反问由 LLM 自决定(通过 prompt 约束,**不**硬编码规则)
- ✅ websearch 降级链:Tavily → Bing → AI 暂时不可用(单一 LLM + 双 websearch)
- ❌ 不做图片理解(Qwen3.6-Plus 不含 VL,M3 处理)
- ❌ 不做 80/20 双模型路由
- ❌ 不做长期记忆(跨会话记忆用户偏好)

## 常见错误

| 报错 | 原因 | 修复 |
|---|---|---|
| `python 未安装` | SQLite 操作依赖 python(已在 parse-doc.ps1 文档列为依赖) | 安装 Python 3.10+,确保 `python` 在 PATH |
| `ALIYUN_BAILIAN_API_KEY 未填` | .env 里还是占位符 | 编辑 `.env`,把 `sk-PLEASE-FILL-IN-...` 换成真实 Key |
| `AI 暂时不可用` | 健康检查显示 OFFLINE | 检查网络;跑 `pwsh scripts\health-probe.ps1` 看状态 |
| `sqlite exec 失败` | sessions.db 锁 / 磁盘满 | 删除 `data\sessions.db` 重试;或检查 U 盘空间 |
| 引用全是"来源:网络" | 知识库没匹配上(可能问题太新/太具体) | 把资料喂进 `data\samples\` 重新嵌入;或调低阈值 |

## 下一步

- 想加 **图片理解**(上传店面照片问"这个摆盘对不对?")?等 M3。
- 想加 **Dify UI 集成**(反问/出题按钮渲染)?等 M3 前后端集成。
- 想加 **更智能的 websearch 过滤**(可信度评分)?M2c+ 阶段。

---

**文档维护**:coder-m2b-ux · 配合 M2b 实施
**反馈**:有 bug 或改进建议请记到 `logs/` 目录,或联系实施工程师。