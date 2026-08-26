# KB-AI 前端设计简报 · Frontend Design Brief

> **本文件用途**:KB-AI 自有前端的设计启动 brief,所有已知事实、决策、约束、可参考资产的整合。
> **目标读者**:KB-AI 前端设计师(本人,或未来他人)。
> **配套文件**:`KB-AI/AGENTS.md`(AI agent 工作准则)、`.harness/pm/custom-kb-qa-ai/`(PM 全套)、`<private>/architecture-validation-report.md Part 2`(架构先进性评审 + 11 条 TODO)。
> **建立日期**:2026-07-07
> **维护原则**:任何"决策矩阵"或"P0 实现状态"变动后,需同步更新本文件。

---

## 0 · 项目定位

### 0.1 一句话定义
**KB-AI = 本地化的"问 AI 帮你找资料"工具**。面向**餐饮分公司总经理(单用户、非技术)**。把经营文档(Word / PDF / PPT / Excel)喂进 U 盘 AI,问一句经营问题,AI 用 `[1][2]` 脚注引用你的资料原文回答。

### 0.2 用户画像

| 维度 | 特征 |
|---|---|
| 行业 | 餐饮(可扩展其它服务行业) |
| 角色 | 分公司总经理 / 业务负责人 |
| IT 背景 | 弱(像"用微信"一样用工具的程度) |
| 设备 | Windows 10/11 桌面电脑 |
| 工作流 | 把 U 盘插到电脑 → 双击 `start.bat` → 浏览器 → 用 AI |
| 单/多用户 | **单用户**(本地、单机) |
| 语言 | 全程中文 |
| 期望 UX | "答错/瞎答"零容忍 — 重视**可追溯**(引用、来源、原文跳转) |

### 0.3 三句话技术事实
1. **部署形态**:1TB 移动 SSD(卷标 `AIAssistant`)+ Windows 10/11 + Docker Desktop,4 个容器编排
2. **数据治理**:100% 本地、**不加密、零备份**(用户已决策接受风险)
3. **AI 推理**:阿里云百炼 Token Plan 标准 ¥198/月,模型 **Qwen3-Plus 80% + Qwen3.7-Max 20%**(2026-07-01 18:16 PRD 回滚决定;**截至当前 KB-AI 实现仍是单模型 `qwen3.6-plus`,后端尚未追上 PRD 回滚,设计师可按 PRD 锁版方案设计,后端会自动对齐**)

### 0.4 用户决策接受的风险(已在 .harness 与 AGENTS.md 固化)
| 风险 | 影响 | 用户态度 |
|---|---|---|
| U 盘丢失/被盗 | 内部资料外泄 | 接受 |
| U 盘物理损坏 | 数据全丢,无恢复 | 接受 |
| 无加密 | 数据裸存 | 接受 |
| 手动启动 | 每次双击 .bat,60-90s 冷启动 | 接受 |
| 单设备 | 仅限插 U 盘的电脑 | 接受 |
| 必须联网 | AI 推理走云;离线时降级而非崩溃 | 接受 |
| 单用户 | 不支持多账号 / 权限分级 | 接受 |

> **含义:设计师不要做"备份还原""多账号""加密上传""账号找回""审计日志"等 UI。它们不在范围。**

---

## 1 · 产品技术骨架(影响前端设计)

### 1.1 部署形态与容器清单

```
┌──────────────────────────────┐         ┌──────────────────────────────┐
│ 用户 Win 10/11 桌面           │         │ 阿里云百炼 Token Plan ¥198/月 │
│  ┌────────────────────────┐  │    ┌───→│ 文本模型:                     │
│  │ 1TB 移动 SSD (U盘) 卷标 │  │    │    │  Qwen3-Plus (80%)            │
│  │  AIAssistant           │  │    │    │  Qwen3.7-Max (20%, 减半活动) │
│  │  ├─ kb-ai-qdrant       │──┼──┘    │  + Embedding(text-embedding-v3)│
│  │  ├─ kb-ai-mineru       │  │       │  + VL(Qwen3-VL-Max)           │
│  │  ├─ kb-ai-dify-api     │  │       └──────────────────────────────┘
│  │  └─ kb-ai-dify-worker  │  │
│  │  + scripts/  (17.ps1)  │  │       ┌──────────────────────────────┐
│  └────────────────────────┘  │       │ Tavily / Bing (websearch 降级)│
└──────────────────────────────┘       └──────────────────────────────┘
        ↓
   浏览器(你设计的前端)→ http://localhost:8080(Dify 临时)或你的新前端
```

**4 容器清单**(`KB-AI/docker-compose.yml:14-152`):

| # | 容器 | 镜像 | 暴露端口 | 角色 |
|---|---|---|---|---|
| 1 | `kb-ai-qdrant` | `qdrant/qdrant:v1.7.0` | 6333 / 6334 | 向量库(HTTP+gRPC)|
| 2 | `kb-ai-mineru` | `opendatalab/mineru:v0.9.1` | 8001 | PDF / Office 解析 |
| 3 | `kb-ai-dify-api` | `langgenius/dify-api:1.0.0` | 8080 | Web UI + REST API(SQLite 模式)|
| 4 | `kb-ai-dify-worker` | `langgenius/dify-api:1.0.0` | 无 | Celery 异步 worker |

### 1.2 主机端脚本层(`KB-AI/scripts/` 17 个 .ps1)

前端不必直接调用这些,但要知道它们存在,因为部分 UI 触发器依赖其状态:

| 脚本 | 职责 | 前端关联 |
|---|---|---|
| `chat.ps1` | RAG 主循环(35 KB,893 行) | 你的 chat 优先前端最终要取代它 |
| `embed-and-ingest.ps1` | 文档 → chunks.jsonl → Qdrant | 资料管理后台不直接调 |
| `parse-doc.ps1` | MinerU 调用 | 资料管理不直接调 |
| `image-prep.ps1` / `batch-images.ps1` | 多模态预处理 / 批量入库 | 图片上传相关 |
| `health-probe.ps1` | 3 端点 ping → `data/health_status.json` | **离线 UX 状态条的数据源** |
| `health-full.ps1` | 综合 1 屏报告 | 不直接 |
| `status-bar.ps1` | 极简状态栏 | **离线/降级色板参考** |
| `disk-alert.ps1` | 容量 5 级告警 | **设置页只读容量** |
| `version.ps1` | 版本/容器/容量总览 | 不直接 |
| `show-help.ps1` | help 输出 | 内嵌 help |
| `setup.ps1` | 交互式引导 | v0.7.1 由 `quickstart.ps1` 重命名,消歧义 |
| `get-usb-root.ps1` | USB 根目录识别(跨平台) | 不直接 |
| `safe-eject.ps1` | 安全弹出 | **关闭确认模态要调它** |
| `websearch.ps1` | Tavily/Bing 降级 | 降级黄条不用直接调 |
| `load-env.ps1` | .env 加载 | 不直接 |
| `seed-sample-data.ps1` | 示例数据种入 | 不直接 |

### 1.3 数据流向(简化)

```
[文档 .docx/.pdf/.pptx/.xlsx/.txt/.md]
        ↓ 拖拽上传至前端
        ↓ 后端调 MinerU(:8001)解析
   cache/parsed/<doc-id>/chunks.jsonl
        ↓ embed-and-ingest
        ↓ 调 Qwen3-Embedding API → 向量(1024 维)
        ↓ 写 Qdrant kb_ai_chunks(Cosine)
                                       ↓
[用户输入问题] ←───────── chat 主页   │
        ↓ Qwen3-Embedding 编码         │
        ↓ Qdrant top-K 检索            │
        ↓ 喂入 prompt                  │
        ↓ Qwen3-Plus / Qwen3.7-Max 生成│
        ↓ SQLite sessions.db 多轮历史  │
[流式渲染 + 脚注引用 + 多媒体呈现]   ←─┘

降级链:知识库未命中 → Tavily → Bing → "网络搜索也未找到,稍后再试"
离线:跳过 Qwen / 检索; 仍可看会话历史 + 知识库列表
```

### 1.4 容量与性能预算

| 项 | 值 | 含义 |
|---|---|---|
| U 盘容量 | 1 TB 总 / ~425 GB 数据 / ~575 GB 余量 | 设计上不假设"无限空间" |
| 5 级容量告警阈值 | 500 / 650 / 750 / 850 / 950 GB | 后端会推 UI;前端用对应色 |
| 冷启动时间 | 60-90s(已开 Docker Desktop)/180-240s(未开) | §D 必须设计进度条 |
| Qdrant 写入批 | MAX_SEGMENT_SIZE_KB=1024 / WAL=32MB / flush 5s | 上传进度可预期但偏慢 |
| Embedding 批 | 10 chunks/批 | 上传大批文档要分段 |
| 检索响应 | top-K ≤ 20(默认 5)、MaxContextChars ≤ 20000 | 结果可能很大,UI 要分段或折叠 |

---

## 2 · "前端"目前在哪儿(关键起点)

### 2.1 当前状态

**KB-AI 目前没有自己的前端**。前端**当前由 Dify 1.0 内置 Web UI 承担**(端口 8080,在 `kb-ai-dify-api` 容器里)。所有交互 — 上传文档、配知识库、聊天、看引用 — 全靠 Dify 自带界面。PowerShell CLI(`chat.ps1`)是另一条仅 CLI 的轻量入口,**没有 Web**。

### 2.2 设计目标(已用户 2026-07-07 决定)
**完全替代 Dify Web UI** —— 直接对接 Qwen API + Qdrant + MinerU,Dify 容器可能保留作为知识库管理后台,新前端是面向用户的 chat-first 界面。

**3 条替代路径**(用户排除的):

| 路径 | 说明 |
|---|---|
| ❌ 共存 | Dify UI 做后台 + 新 chat-only Web UI |
| ❌ 包装 | 新 UI 走 Dify REST API,只换皮 |
| ❌ 浏览器插件 | 给 Dify UI 加注入,非独立 UI |
| ✅ **完全替代**(已选)| 跳出 Dify 容器,自建后端 + 自建 UI |

### 2.3 不动的范围(已锁版)

- ❌ **Dify 容器**:可以保留作为知识库管理后台/文档解析排队,**但不作为面向用户的 UI**
- ❌ **PowerShell 脚本**(17 个):不动,是后端实现的一部分
- ❌ **deps**:`.env.example`、`start.bat`、`stop.bat`、`package.bat`
- ❌ **`dify/knowledge-pipeline.json`**:Dify Web UI 用的备份 JSON,不影响新前端
- ❌ **现有 Dify Web UI**:**只移除面向用户的渲染部分**,Dify 容器后端仍可作为 API endpoint 提供元数据/文档管理服务

---

## 3 · 12 条 P0 需求(给设计师的翻译版)

每条都列:**用户故事 + 前端组件 + 关键 AC 摘要 + 详情文件**。

### 3.1 REQ-1:多格式文档上传与解析
- **用户故事**(原始):我想把 .docx/.pdf/.pptx/.xlsx 文件上传,让 AI 能基于资料回答。
- **前端组件**:
  - 拖拽上传区(支持点击)
  - 上传队列列表(展示文件名 / 大小 / 状态)
  - 单文件 ≤ 200 MB 的限制提示
  - 解析进度条(每文件)
  - 解析失败的错误卡片(保留文件 + 报错原因)
- **关键 AC**:`func-spec-v2.md` REQ-1 全 10 条
- **小坑**:`.pdf` 扫描版要做 OCR(关联 REQ-11),`.doc`/`.xls` 旧版不支撑

### 3.2 REQ-2:分类与标签管理
- **前端组件**:
  - 文档表单:主分类(下拉必填)+ 多标签(chips)
  - 列表筛选:分类、标签、上传时间排序
  - 批量操作:批量移动分类、改标签、删除
  - 分类列表:用户可增删改(扁平一级,**不做嵌套**)
- **关键 AC**:`func-spec-v2.md` REQ-2 全 10 条

### 3.3 REQ-3:RAG 检索对话(核心)
- **前端组件**:
  - 聊天主页主区(chat-first,默认)
  - 每条 AI 回复带 `[1][2]` 角标
  - 点击角标跳原文段(高亮段落位置)
  - top-K 可配置(默认 5)
  - 命中率 80%+(后端验收)
- **JSON 三型**(`chat.ps1:1-30` SYNOPSIS 已写):
  - `{"type":"answer","content":"...","citations":[1,2]}` — 默认
  - `{"type":"clarify","question":"..."}` — 反问(最多 2 轮)
  - `{"type":"multi_choice","options":[...]}` — 出 2-5 选项
- **关键 AC**:`func-spec-v2.md` REQ-3 AC-3.7/3.8/3.9/3.10(双模型路由路径)+ AC-3.x(标准)

### 3.4 REQ-4:AI 主动反问澄清
- **前端组件**:
  - 反问卡片:`type=clarify` 触发时显示蓝色 prompt
  - 跳过按钮:"按我的原问题回答"一键继续
  - 计数器:反问不超过 2 轮(超限自动给答案)
- **关键 AC**:`func-spec-v2.md` REQ-4 全 6 条

### 3.5 REQ-5:AI 主动出多选题
- **前端组件**:
  - 选项按钮组:2-5 个按钮
  - 可点击单选/多选(由 LLM 决定)
  - 用户勾选后自动接回对话上下文
- **关键 AC**:`func-spec-v2.md` REQ-5 全 7 条

### 3.6 REQ-6:多轮对话记忆
- **前端组件**:
  - 抽屉式会话侧栏(默认收起)
  - 会话列表(title 自动生成 + 用户可改)
  - 历史会话可加载(读 SQLite)
  - 新会话按钮
  - 删除会话
  - 50 轮软上限提示(超限 UI 红条提示"记忆开始模糊")
- **后端数据**:`./data/sessions.db` SQLite(messages / sessions 两表)
- **关键 AC**:`func-spec-v2.md` REQ-6 全 6 条

### 3.7 REQ-7:未命中 websearch 降级
- **3 级降级链**(2026-07-01 18:16 回滚到 3 级):
  - L0:Plus(80%)/ Max(20%)直接成功
  - L1:重试 1 次(2s 后)
  - L2:Plus ↔ Max 互切
  - L3:切 Tavily / Bing,标"来源:网络"
  - L3-fail:返回"网络搜索也未找到" + 错误码 503
- **前端组件**:
  - 黄色提示条"已切换到 X 模型"(每次降级触发)
  - 引用角标额外标"来源:网络"(网络结果才加)
  - 用户禁用降级的开关(`-SkipWebsearch` 参数对应 UI)
- **关键 AC**:`func-spec-v2.md` REQ-7 + §B 全 6 条

### 3.8 REQ-8:脚注引用
- **前端组件**(与 REQ-3 强协同):
  - 引用样式:`[1] [2]` 角标
  - 引用元信息:文档名 + 段落位置(如 `[1] 经营手册.pdf §3.2`)
  - 角标点击 → 高亮定位原文段
- **关键 AC**:`func-spec-v2.md` REQ-8 全 5 条

### 3.9 REQ-9:U 盘便携部署 ⭐ 完全重写
- **前端无直接关联**,但要呼应:`Windows-Start.bat` 启动后,前端要自动打开
- **关键 AC**:`func-spec-v2.md` REQ-9 AC-9.6 "浏览器自动开 http://localhost:8080"

### 3.10 REQ-10:极简 UI 风格 ⭐ 强约束
- **设计基线**(已在 0 章落地):
  - 主色 ≤ 2
  - 辅助色 ≤ 2
  - 极简、商务
- **不在前端范围**:`func-spec-v2.md` REQ-10 全 7 条(参考但不抄)

### 3.11 REQ-11:图片理解
- **前端组件**:
  - 图片上传按钮(聊天框右侧)
  - 多图携带(最多 8 张,单张 ≤ 20 MB)
  - 缩略图预览(发送前)
  - 多模态对话:已发图片在历史中可点击放大
- **离线降级**:图片理解需在线,离线时降级提示
- **后端路由**:`Qwen3-VL-Max`(主)+ `Qwen3.7-Plus` 多模态(备,PRD §11.5)
- **关键 AC**:`func-spec-v2.md` REQ-11 全 9 + 2(离线)

### 3.12 REQ-13:无备份(用户决策)
- **前端组件**:**启动横幅提醒** —— 用户首次启动看到"数据无云备份,建议电脑保留副本"
- **关闭流程**:`§C` 安全弹出再次提醒
- **关键 AC**:`func-spec-v2.md` REQ-13 全 6 条(均为验证"无"行为)

---

## 4 · 4 套 UX 章节触发器(必须实现的 UI 元素)

来源:`.harness/pm/custom-kb-qa-ai/func-spec-v2.md` §A/§B/§C/§D(每套 6-7 个 AC)。

### 4.1 §A 离线模式 UX(7 条 AC)
**触发**:网络不可达或阿里云 API 失败(但本地可工作)。

| UI 元素 | 表现 | 触发条件 |
|---|---|---|
| **状态栏** | 🔴 红圆点 + "离线" | `data/health_status.json` 中 qwen 端点 failed |
| **顶部红条** | "离线模式" | 持续显示,不可关闭 |
| **输入框** | 可输入,但 submit 触发 | "AI 暂时不可用" 提示 |
| **历史列表** | 可加载(本地 SQLite)| 离线也不影响 |
| **资料库列表** | 可加载(本地 SQLite)| 离线也不影响 |
| **检索按钮** | 禁用 + 提示 "检索需在线" | 离线 |
| **30s 自动重检** | 网络恢复时状态栏变绿,无操作 | `health-probe` 周期 |

### 4.2 §B API 失败降级 UX(6 条 AC)
**触发**:阿里云 Qwen 调用失败。

**3 级降级链**:
```
L0 成功 → 直接返回(80% Plus / 20% Max 默认)
  ↓ 失败
L1 重试 1 次(2s 后)
  ↓ 仍失败
L2 切到备用模型(Plus ↔ Max 互切)
  ↓ 仍失败
L3 切到 Tavily / Bing websearch
  ↓ 仍失败
返回"网络搜索也未找到" + 503
```

**UI 元素**:
- 🟡 **黄色提示条** "已切换到 X 模型"(每次降级触发,可关闭)
- **引用角标**额外标 "来源:网络"
- **degradation_events** 表记录:query / 模型 / 时间 / 降级原因

### 4.3 §C 安全弹出 UX(7 条 AC)
**触发**:用户尝试关闭 AI / 拔 U 盘 / 系统托盘右键"关闭"。

**模态对话框**:
```
┌──────────────────────────────────────┐
│  确定要关闭 AI Assistant 吗?           │
├──────────────────────────────────────┤
│  关闭后:                              │
│    - Dify 容器优雅停止(10s)           │
│    - 您可以安全弹出 U 盘               │
│    - 下次使用需重新双击 Windows-Start.bat│
│                                       │
│  ⚠️ 重要:                              │
│    - 您当前会话正在处理中(对话已自动保存)│
│    - 数据无云备份,仅在本地 U 盘         │
│                                       │
│  [取消]            [确认关闭]          │
│  [ ] 不再提示(本次会话)               │
└──────────────────────────────────────┘
```

- 确认 → 调 `POST /api/shutdown` → safe-eject.ps1
- 取消 → 关弹窗,Dify 仍跑
- 意外拔 U 盘 → UI 提示 "U 盘意外拔出,数据可能损坏"

### 4.4 §D 冷启动 UX(7 条 AC)
**触发**:`start.bat` 启动时。

**6 段进度条**(终端 → 前端迁移):

```
=================================
     AI Assistant 启动中
=================================
[1/6] U 盘根目录: E:\            ✓
[2/6] Docker Desktop 已就绪       ✓ (4s)
[3/6] Qdrant 启动中...            ✓ (8s)
[4/6] MinerU 启动中...            ✓ (15s)
[5/6] Dify 启动中...              (SQLite 初始化可能慢)
      ████████░░ 80% / 28s
[6/6] Dify Web UI 就绪            ✓ (45s)
=================================
     ✓ 总耗时 60 秒
     访问: http://localhost:8080
```

- 每 5-10s 更新一次
- 任一步 > 60s → "本步骤超过 60s,请检查 docker logs aiassist-{name}"
- 失败不卡死 → 提示后停在等待,Ctrl+C 退出
- 总超时 > 120s → "Pause 已 120s,请检查日志"

> **设计师迁移方案**:当前进度由 `start.bat` 终端打印,前端要实时看到,需要 backend 把进度推到前端(WebSocket / SSE 通道)。

---

## 5 · 你已做出的设计决策(2026-07-07 锁版)

### 5.1 决策矩阵

| # | 维度 | 你的决策 | 备注 |
|---|---|---|---|
| 1 | **品牌调性** | 经典商务黑灰(无现成配色) | 不沿 v1.1 顾问色;也**不**沿 KB-AI 现有 `#F4D35E`(黄);主色板待你定 |
| 2 | **字体组** | v1.1 锁版:`得意黑` + `阿里巴巴普惠体 3.0` + `Playfair Display` + `Inter` + `JetBrains Mono` | 见 `.harness/pm/u-brain-v1.1/arch-v1.1.md` §5.1 |
| 3 | **信息架构** | 顶部 nav + 抽屉式历史 | **不**沿用 Dify 三栏;极简 chat 优先 |
| 4 | **模型路由** | **后端静默调(无 UI)** | 用户不知/不选;最终模型选择由后端决定 |

### 5.2 决策要点

**5.1 决定"经典商务黑灰"** —— 意味着:
- 主色 ≤ 2 个(避免五彩),深灰 + 中性
- 辅助色 ≤ 2 个,暖色系点缀(可选)
- 不要渐变 / 玻璃拟态 / 大色块
- 阴影极轻,边框清晰

**5.2 决定"v1.1 字体组"** —— 注意:
- 来源 `.harness/pm/u-brain-v1.1/arch-v1.1.md` §5.1
- **该节当前被 architecture-validation-report.md Part 1 §3.3 指出过期引用**,字体栈与 PRD v1.1.5 锁版不一致
- **使用前先核对**:直接读 arch-v1.1.md §5.1 最新内容(可能已被修订)
- 中文字体不依赖默认 PingFang / 微软雅黑

**5.3 决定"顶部 nav + 抽屉式历史"** —— 信息架构:
```
顶部 nav(高 56px):[KB-AI 📚] 对话 资料库 设置  ─── [🟢]  [⏻]
顶部之下可选:🔴 离线条 / 🟡 降级黄条
主区域:聊天对话(默认)
左抽屉(默认收起):历史会话列表
```

**5.4 决定"模型路由静默"** —— 前端看不到:
- 用户不会看见"已切换到 Qwen3.7-Max"的明确 UI(降级黄条除外,那是降级提示)
- 用户不会看见模型选择按钮
- §B 3 级降级**仍触发黄条**(那是降级提示,与模型选择不同)

### 5.3 设计令牌空位(待你后续定义)

| Token | 建议起手值 | 状态 |
|---|---|---|
| 主色 | `#1F2937` 商务深灰(建议)| 待拍板 |
| 辅助色 | `#F4D35E` 暖黄(沿用现有 knowledge-pipeline.json) | 待拍板 |
| 强调色(错误/降级/离线)| `#DC2626` 红 | 待拍板 |
| 主背景 | `#FFFFFF` / `#F9FAFB` | 待拍板 |
| 字号阶 | 12 / 14 / 16 / 18 / 24 / 32 / 48 px(7 阶)| 待拍板 |
| 间距阶 | 4 / 8 / 12 / 16 / 24 / 32 / 48 px(4 倍数)| 待拍板 |
| 圆角 | 0 / 4 / 8 / 16 px(偏方正)| 待拍板 |
| 阴影 | 极轻 `0 1px 3px rgba(0,0,0,0.05)` | 待拍板 |

> 后续 token 敲定后,建议落到 `KB-AI/docs/design-tokens.md`(新建)独立维护。

---

## 6 · 设计时不要踩的坑(7 类)

| # | 类别 | 事实 | 前端影响 |
|---|---|---|---|
| 1 | **数据治理** | 不加密、零备份(用户决策)| 不做"加密上传""云备份""自动同步"等 UI |
| 2 | **账号体系** | 单用户、本地 | 不做账号系统、角色、SSO、找回密码 |
| 3 | **模型选择** | 后端静默调 | 不做"模型切换"按钮、不显示当前模型名(降级黄条除外) |
| 4 | **可用性假设** | 必须有离线降级 UX(§A)| 必做顶部状态条 + 输入框降级提示 |
| 5 | **性能假设** | U 盘 + Win + SSD,启动 60-90s,响应有延迟 | 启动进度必做;大量响应要 skeleton loading |
| 6 | **响应式** | Win 10/11 桌面为主,1280-1920 宽 | **不**为移动端做深度适配;大屏也不用 dashboard 重度 |
| 7 | **深色模式** | 没要求;商务基调 | 现 v1 留空,但 token 用 CSS 变量方便后续 |

### 6.1 隐性"不要做"清单

- ❌ **不要做文件加密 UI**(用户已决策不接受)
- ❌ **不要做"登录"页 / "注册"页**
- ❌ **不要做"账户设置"页**
- ❌ **不要做"模型选择"下拉**(除非 PRD 真要,且后端已对齐)
- ❌ **不要做"导入云盘"功能**(OneDrive / Dropbox / 坚果云 等都不接)
- ❌ **不要做"分享链接"功能**(本地工具无外网)
- ❌ **不要做水印 / 版权页**(单用户工具无意义)
- ❌ **不要做移动端 App / 微信小程序**(Win 桌面为主)
- ❌ **不要做大屏 Dashboard / Analytics**(单用户无 KPI 需求)
- ❌ **不要做"Notion 风格"块编辑器**(不适用 RAG)
- ❌ **不要做工作流编排 / 拖拽流程**(单用户线性用)

---

## 7 · 可参考资产地图

### 7.1 品牌语调参考
- **`KB-AI/QUICKSTART.md`** —— 给非技术用户,白话、亲切、像给老板讲课。"**您只需要会装微信,就能装这个**"是核心语调

### 7.2 章节分块参考
- **`KB-AI/docs/m2-usage.md`** —— M2a / M2b / M3 / 错误指南分模块;可在文档/帮助中心沿用

### 7.3 CLI 配色参考
- **`KB-AI/scripts/status-bar.ps1`** —— 🟢 OK / 🔴 FAIL / 🟡 WARN 三态极简,色板语义已经在实战中验证

### 7.4 字体方案
- **`.harness/pm/u-brain-v1.1/arch-v1.1.md` §5.1** —— v1.1 锁版字体组(你已 2026-07-07 选)
- **注意**:Part 1 §3.3 指出 §5.1 当前过期引用,**使用前先 Read 原文核对最新内容**

### 7.5 设计令牌空位
- 设计令牌文件尚未建立,见 §5.3。建议后续把 token 落到 `KB-AI/docs/design-tokens.md`

### 7.6 业务文案样本
- **`KB-AI/scripts/chat.ps1:1-30` SYNOPSIS** —— 列出"招牌菜红烧肉怎么做?"等典型问题文案
- **`KB-AI/dify/knowledge-pipeline.json:77-81` suggested_questions** —— 3 个 sample 问题
- **`KB-AI/.env.example:9` AIAssistant** —— 卷标命名也有"AI Assistant"含义

### 7.7 PRD 已锁的"信息架构参考"
- **Dify Web UI 三栏**(替代前):左:会话列表 / 中:对话 / 右:知识库管理
- **你已选"顶部 nav + 抽屉式历史"**,**不**沿用三栏

---

## 8 · 后端接口契约(等 coder 同步的清单)

| 契约需求 | 来源 | 设计师要做的 UI 假设 |
|---|---|---|
| **HTTP 后端包装 CLI**(chat.ps1 → REST)| 待 coder 同步 | 前端默认 `POST /api/chat` 流式响应 SSE / WebSocket |
| `POST /api/shutdown` → safe-eject.ps1 | §C 模态弹出 | "确认关闭"按钮 |
| WebSocket / SSE 推 start.bat 6 段进度 | §D 冷启动 | "启动中"模态,听实时进度事件 |
| SQLite 增 `degradation_events` 表 | §B API 降级 | "已切换到 X 模型"黄条的"查看详情"链接 |
| 双模型路由(80/20)追上 PRD 回滚决策 | `task-breakdown-v2.md` T-USB-6 | 暂不考虑 UI;后端对齐即可 |
| WEB File API 上传文档 + 后端调 MinerU | REQ-1 | 上传组件 |
| `POST /api/sessions` 创建 / `GET /api/sessions` 列表 / 等 | REQ-6 | 抽屉历史 + 新建会话按钮 |

> **后端契约未定型前,前端可以先以 SSE 流式 + RESTful 假设先行设计(降级处理后端变化)**

---

## 9 · 文档地图 & 资料源头

### 9.1 你做设计的资料源头

| 资源 | 路径 | 类型 |
|---|---|---|
| PRD v0.7 基础 | `<private>/.harness/intake/custom-kb-qa-ai-prd-draft.md` | PM intake 原始需求 |
| PRD 锁版 v2 | `<private>/.harness/pm/custom-kb-qa-ai/prd-v2.md` | PM 锁版终稿 |
| 架构 v2 | `<private>/.harness/pm/custom-kb-qa-ai/arch-v2.md` | 架构 12 节详细 |
| Func-spec v2 | `<private>/.harness/pm/custom-kb-qa-ai/func-spec-v2.md` | **100 个 AC**(你设计的验收依据)|
| Task-breakdown v2 | `<private>/.harness/pm/custom-kb-qa-ai/task-breakdown-v2.md` | 20 ticket / 5-6 周 |
| FINAL-PLAN | `<private>/.harness/pm/custom-kb-qa-ai/FINAL-PLAN.md` | PM 总览 + 决策矩阵 |
| 历史归档(CVM 版)| `<private>/.harness/pm/custom-kb-qa-ai-v06-DEPRECATED/` | 仅参考 v0.4-v0.6 旧版 |
| AI 工作准则 | `<private>/KB-AI/AGENTS.md` | 含你的设计决策 §12 |
| 架构评审 + 11 TODO | `<private>/architecture-validation-report.md` Part 2 §9 | 其中"端口裸绑""无资源限制"是前端绕开点 |
| 用户文档 | `<private>/KB-AI/QUICKSTART.md`、`docs/m2-usage.md`、`docs/safe-eject.md` | 品牌语调参考 |
| 实际代码 | `<private>/KB-AI/`(docker-compose / 17 .ps1 / 10 test) | 实现细节 |

### 9.2 你做设计时的外部依赖

- **字体源**:得意黑 / 阿里巴巴普惠体 3.0 / Playfair Display / Inter / JetBrains Mono —— 自托管或者嵌入 Google Fonts / 国内 CDN 镜像
- **图标库**:`📚` emoji 起步;后续可换 Heroicons / Lucide
- **设计工具**(可选):Figma / Sketch / Penpot;若要轻量,可直接 Markdown / ASCII 出图

---

## 10 · 关键事实速查(用于设计时随手查阅)

```
项目代号         KB-AI(知识库 AI 助手)
用户             餐饮分公司总经理(单用户)
部署             1TB 移动 SSD + Win 10/11 + Docker
容器数           4(Qdrant / MinerU / dify-api / dify-worker)
卷标             AIAssistant(U 盘) / UBrain(U-Brain v1.1 项目)
语言             中文
模型             Qwen3-Plus 80% + Qwen3.7-Max 20%(Token Plan ¥198/月)
Embedding        text-embedding-v3(1024 维 / Cosine)
多模态           Qwen3-VL-Max(主)/ Qwen3.7-Plus 多模态(备)
降级链           L0 成功 / L1 重试 / L2 Plus↔Max / L3 Tavily-Bing / 503
启动时间         60-90s(已开 Docker)/180-240s(未开)
SQLite           单库 + WAL(./data/db.sqlite + ./data/sessions.db)
Qdrant           kb_ai_chunks(Cosine, 1024 维, BATCH_SIZE 32)
MinerU           opendatalab/mineru:v0.9.1(中文 PDF/PPT 解析)
冷启动进度       6 段(根目录 / Docker / Qdrant / MinerU / Dify / UI)
不加密           用户决策接受
不备份           用户决策接受(./data 一旦损坏 = 全丢)
单用户           本地无账号
```

---

## 11 · 变更记录

| 日期 | 变更 | 变更人 | 影响 |
|---|---|---|---|
| 2026-07-07 | 初版建档(详细版)| 用户 + AI 协作 | 落地 12 条 P0 + 4 套 UX 章节 + 4 决策 + 7 项不要做 + 9 类资料源 |
| 2026-07-07 | 新增 §5.3 设计令牌空位 + §10 速查 | AI 协作 | 后续 token 落地有指引 |
| 待定 | 设计令牌最终值敲定,落到 `docs/design-tokens.md` | 用户 | UI 主色 / 字号阶 落地 |
| 待定 | 后端接口契约完善(§8)后,补充 endpoint 列表与签名 | 用户 + coder | 前端 API 调用层设计依据 |
