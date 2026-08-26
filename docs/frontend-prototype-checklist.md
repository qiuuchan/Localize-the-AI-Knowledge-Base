# KB-AI 前端原型优化检查清单 & Coder 接口契约

> **用途**：前端原型开发 / 复核时的唯一检查表，以及前后端对接时的接口契约。  
> **设计唯一真相源**：`design-system/MASTER.md` v1.4（任何视觉/Token/组件冲突以 MASTER.md 为准）。  
> **角色边界**：按 `AGENTS.md §12.5`，前端设计与实现由用户主导；本文件由 AI 辅助整理，用于**复核偏差**和**coder 对接**。

---

## 0. 当前状态快照

| 项 | 状态 |
|---|---|
| 已安装 skills | `frontend-design`、`tailwind-design-system`（本地安装至 `E:/.agents/skills/`） |
| 项目前端原型 | **尚未发现** `.html/.tsx/.jsx/.vue/.svelte` 等原型文件 |
| 技术栈 | React 18 + TypeScript + Vite + **Tailwind CSS v3** + shadcn/ui + Lucide React |
| 后端 API 版本 | `v0.8.0` |
| API 前缀 | `/api/*` |

---

## 1. 设计基线（不可偏离）

### 1.1 品牌调性

- **Industrial + Swiss**：像一台可靠的商用设备，干净、稳定、可核验，但不冰冷。
- **主色 ≤ 2**：`#1F2937` 商务深灰、`#111827` 纯黑。
- **辅助色 ≤ 2**：`#F4D35E` 暖黄（仅功能性温度提示）、`#D97706` 琥珀（警告/降级）。
- **背景**：`#F5F0E8` 米白（L=0.88，8h 不刺眼）。
- **视觉记忆点**：极致黑白灰中的一抹暖黄 = 餐饮行业的温度感。

### 1.2 字体栈

| 用途 | 字体 |
|---|---|
| 中文标题 | 得意黑（Smiley Sans） |
| 中文正文 | 阿里巴巴普惠体 3.0 |
| 英文标题 | Playfair Display |
| 英文正文 | Inter |
| 代码 / 角标 / 时间戳 | JetBrains Mono |

### 1.3 信息架构

```text
┌─────────────────────────────────────────────────────────────┐
│ [BookOpen] KB-AI   对话   资料库   设置    [●在线] [Power] │  ← 顶部 nav (56px)
├─────────────────────────────────────────────────────────────┤
│ [离线/降级状态条，仅在非在线时显示]                           │
├──────────┬──────────────────────────────────────────────────┤
│          │                                                  │
│  抽屉     │              主对话区（chat-first）              │
│ (320px)  │                                                  │
│  会话历史 │  ┌────────────────────────┐                    │
│          │  │ 用户: 问题内容          │  ← 右侧            │
│ [+] 新建 │  └────────────────────────┘                    │
│ 会话 1   │                                                  │
│ 会话 2   │  ┌────────────────────────┐                    │
│ 会话 3   │  │ KB-AI: 回答内容 [1][2]  │  ← 左侧            │
│          │  └────────────────────────┘                    │
│          │                                                  │
│          │         ┌──────────────────────────┐          │
│          │         │ [Paperclip] 问 AI 经营问题... [Send] │  ← 底部输入区
│          │         └──────────────────────────┘          │
└──────────┴──────────────────────────────────────────────────┘
```

---

## 2. 前端原型优化检查清单

### 2.1 视觉与品牌（按 `frontend-design` skill 原则）

- [ ] 是否基于 `MASTER.md §4` 的 CSS 变量建立 Token？
- [ ] 是否存在"通用 AI 美学"痕迹：紫白渐变、蓝紫渐变、玻璃拟态、Dashboard 大屏、营销式大数字？
- [ ] 暖黄 `#F4D35E` 是否**只**用于功能性提示（新消息、完成、引用 hover、降级提醒），而非装饰背景？
- [ ] 是否避免使用 emoji 作为结构性图标，全部使用 Lucide React SVG？
- [ ] 是否避免使用 Inter/Roboto/Arial 等默认字体作为中文标题或正文？
- [ ] 是否有一个"可被记住"的标志性元素（如引用角标 `[1]` 的工业编号感），同时保持整体克制？

### 2.2 组件规范

- [ ] **按钮**：`primary / secondary / outline / ghost / destructive / link` 6 个变体齐全，尺寸 `sm/default/lg/icon` 符合 §10.1。
- [ ] **聊天输入框**：按 §10.2 特殊规范实现，容器圆角 `radius-lg` (16px)，支持多行，左侧附件 + 右侧发送。
- [ ] **消息气泡**：用户消息靠右、`primary` 背景白字；AI 消息靠左、`background-secondary` 背景；最大宽 75% / 768px。
- [ ] **引用角标**：`[1]` `[2]` 为 `font-mono` + `text-xs` (12px) + `info` 蓝色，hover 下划线，点击可跳原文。
- [ ] **模态框**：宽 480/640px，圆角 16px，`shadow-xl` + 45% 黑遮罩，支持 ESC / 点击遮罩 / 关闭按钮。
- [ ] **抽屉**：左侧滑入，宽 320px，头部 56px 与 nav 同高，列表项 stagger 30ms。
- [ ] **进度条**：冷启动用暖黄填充，上传用主色，错误/成功/降级语义色正确。
- [ ] **开关**：44×24px 轨道，滑块 20px，开态 `primary` 背景。

### 2.3 布局与响应式

- [ ] 顶部 nav 固定顶部，`h-14` (56px)，`z-index: 50`，无阴影，底部 1px 半透明白线分隔。
- [ ] 主内容区桌面优先，目标断点 `xl` (1280px)，主区 75% 居中最大 1200px。
- [ ] 抽屉默认收起，点击历史按钮或 nav "对话" 滑出。
- [ ] 底部输入区 `sticky` 或 `fixed` 底部，始终可见。
- [ ] **不做**：移动端底部导航、汉堡菜单、PWA 适配、深色模式 v1。

### 2.4 动效规范

- [ ] 动画仅使用 `transform` + `opacity`，不动画 `width/height/top/left/margin/padding`。
- [ ] 时长以 150-300ms 为主，复杂模态 400ms。
- [ ] 缓动使用 `var(--easing-default)` / `enter` / `exit` / `emphasis`，**无 bounce / elastic 默认反馈**。
- [ ] 支持 `@media (prefers-reduced-motion: reduce)` 降级。
- [ ] 消息流式输出：字符直接出现，不逐字 fade；末尾光标 `animate-pulse`。

### 2.5 无障碍

- [ ] 所有可交互元素有可见焦点环：`outline: 2px solid var(--primary)` + `outline-offset: 2px`。
- [ ] 正文/按钮/链接对比度 ≥ 4.5:1（AA），大文字 ≥ 3:1。
- [ ] 模态框打开时 **Focus Trap**，关闭后焦点返回触发元素。
- [ ] 聊天消息流 `role="log" aria-live="polite"`。
- [ ] 图标-only 按钮必须带 `aria-label`。
- [ ] 使用 `rem` 单位，支持浏览器字体缩放（200% 不崩溃）。

### 2.6 文案语气

- [ ] 是否"给老板讲课"：直接、亲切、可执行？
- [ ] 是否避免暴露模型名（如 `qwen3.6-plus`）、容器名、`docker logs`、英文错误码？
- [ ] 错误提示是否说明**影响** + **下一步**？
- [ ] 离线说"网络连接断了，AI 暂时回答不了"，降级说"已换用备用方式为您查找"。

### 2.7 反模式清单（必须杜绝）

- [ ] 无模型选择 UI / 模型参数调节。
- [ ] 无登录页、注册页、找回密码、账户设置、角色管理。
- [ ] 无 Dashboard / Analytics / 数据可视化图表。
- [ ] 无工作流编排 / 拖拽流程。
- [ ] 无水印 / 版权页 / 分享链接 / 云盘导入。
- [ ] 无"数据安全"宣传页 / 加密上传 UI / 云备份按钮。

---

## 3. Coder 接口契约

### 3.1 基础信息

- **API 基础地址**：`http://localhost:8080/api`（最终由 `DIFY_PORT` 决定，默认 8080）。
- **CORS**：已配置 `allow_origins=["*"]`，前端本地开发可直接调用。
- **静态文件**：后端 `backend/main.py` 会挂载 `backend/static/` 为根路径静态服务；前端生产构建产物应输出至此。

### 3.2 接口总览

| 方法 | 路径 | 说明 | 请求 / 响应要点 |
|---|---|---|---|
| GET | `/api` | 服务根信息 | `{name, version, root}` |
| GET | `/api/health` | 健康探针 | 调用 `health-probe.ps1 -OutputJson` |
| GET | `/api/status` | 综合状态 | `{scannedAt, version, capacity, health, errors}` |
| GET | `/api/sessions` | 会话列表 | `limit`, `offset` |
| POST | `/api/sessions` | 创建会话 | `{title?}` → `{session_id}` |
| GET | `/api/sessions/{id}/messages` | 获取消息 | `limit`, `offset` |
| POST | `/api/sessions/{id}/messages` | 保存消息 | `{role, content}` |
| POST | `/api/chat` | **SSE 聊天** | 见 §3.3 |
| POST | `/api/boot` | **SSE 启动进度** | 见 §3.4 |
| POST | `/api/shutdown` | 安全弹出 | `{success, exit_code, message}` |

### 3.3 Chat SSE（核心）

**请求** `POST /api/chat`（`Content-Type: application/json`）：

```json
{
  "question": "string",           // 必填，1-10000 字符
  "session_id": "string?",        // 可选，不传则后端新建
  "image_paths": ["string"],      // 可选，多模态图片路径
  "top_k": 5,                     // 默认 5，范围 1-20
  "skip_websearch": false,        // 是否跳过网络搜索降级
  "max_tokens": 2000,             // 默认 2000，范围 100-8000
  "model_name": "string?",        // 覆盖主模型
  "model_name_max": "string?",    // 覆盖 Max 模型
  "disable_model_routing": false, // 强制单模型
  "model_routing_keywords": "string?" // 覆盖复杂关键词
}
```

**SSE 事件流**：

| event | data 结构 | 含义 |
|---|---|---|
| `status` | `{"message": "正在检索知识库..."}` | 状态提示 |
| `answer` | 完整 answer JSON | 最终回答 |
| `error` | `{"message": "...", "detail": "..."}` | 调用失败 |

**answer JSON 关键字段**：

```json
{
  "content": "回答文本",
  "citations": [{"doc": "...", "chunk_idx": 0, "text": "..."}],
  "citations_idx": [0, 1],
  "session_id": "uuid",
  "model": "qwen3.6-plus",
  "model_reason": "default",
  "web_source": null
}
```

- `model_reason` 取值：`default` / `complex_keyword` / `fallback_*`。
- 若 `model_reason` 以 `fallback` 开头 → 触发模型降级，UI 显示黄条。
- 若 `web_source` 非空 → 触发 websearch 降级，UI 显示黄条。

### 3.4 Boot SSE（冷启动进度）

**请求** `POST /api/boot`

**SSE 事件流**：

| event | data 字段 | 说明 |
|---|---|---|
| `progress` | `{stage, message, percent, done, error}` | 阶段进度 |
| `error` | `{"message": "启动进度流超时"}` | 超时 |

**阶段顺序**：

```text
root      → 已定位 U 盘根目录        10%
docker    → Docker Desktop 已就绪     20%
compose   → 容器已启动，等待服务就绪   30%
qdrant    → Qdrant 已就绪             45%
dify      → Dify Web UI 已就绪        70%
worker    → dify-worker 已就绪        85%
ready     → KB-AI 启动完成           100%
```

### 3.5 后端状态 → UI 映射

| 后端信号 | 前端表现 |
|---|---|
| `/api/health` 全绿 | 顶部 nav 显示绿点 + "在线" |
| `/api/health` 部分失败 | 显示黄条："已换用备用方式为您查找" |
| `/api/health` 全失败 / 503 | 显示红条："网络连接断了，AI 暂时回答不了。您仍然可以查看历史对话和本地资料。" |
| `answer.model_reason` 以 `fallback` 开头 | 显示黄条："已换用备用方式为您查找" |
| `answer.web_source` 非空 | 显示黄条："已换用备用方式为您查找，回答可能来自公开网络" |

---

## 4. Tailwind v3 vs v4 说明

- 已安装 skill `tailwind-design-system` 针对 **Tailwind CSS v4**（CSS-first `@theme`）。
- 本项目 `MASTER.md §1.4` 明确锁定 **Tailwind CSS v3**（`tailwind.config.js` + `theme.extend`）。
- 前端实现时**以 v3 为准**，不要直接照搬 skill 中的 `@theme` / `@import "tailwindcss"` 语法。
- 若未来要升级到 Tailwind v4，需要同步重写 `tailwind.config.js` 并更新 MASTER.md。

---

## 5. 推荐下一步

1. **用户创建首个原型**：可用 HTML / React / Figma 任选，重点先把 **聊天主页 + 顶部 nav + 抽屉 + 底部输入区** 跑通。
2. **AI 复核**：把原型文件路径发给我，我逐条对照本清单 + MASTER.md 挑偏差。
3. **前后端联调**：
   - 先调通 `POST /api/chat` SSE 流式回答；
   - 再调 `POST /api/boot` 冷启动进度；
   - 最后调 `POST /api/shutdown` 安全弹出。
4. **回归测试**：跑 `tests/test_model_routing.ps1` 和 `tests/integration/api/test_api.py` 确认后端行为稳定。

---

*本文件由 Kimi Code 于 2026-07-13 整理，基于 `design-system/MASTER.md` v1.4 与后端 `backend/api/*.py` 当前实现。*
