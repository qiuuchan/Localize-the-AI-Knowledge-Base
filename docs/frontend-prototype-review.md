# KB-AI 前端原型复核报告

> **复核对象**：`backend/static/index.html`  
> **依据**：`design-system/MASTER.md` v1.4 + `docs/frontend-prototype-checklist.md`  
> **复核日期**：2026-07-13  
> **状态**：P0/P1 已修复；抽屉、安全弹出模态已实现；P2/P3 记录待后续处理

---

## 已修复 / 已实现项

| 优先级 | 偏差 / 功能 | 位置 | 修复 / 实现内容 |
|---|---|---|---|
| P0 | 缺少自定义可见焦点环 | CSS | 新增 `:focus-visible { outline: 2px solid var(--primary); outline-offset: 2px; }` |
| P0 | 消息气泡字号 15px，不符合正文 16px | `.message-bubble` | 改为 `font-size: 16px` |
| P0 | 消息气泡最大宽仅 75%，未限制 768px | `.message` | 改为 `max-width: min(75%, 768px)` |
| P0 | 发送按钮圆角为 8px，规范要求 4px | `.send-btn` | 改为 `border-radius: var(--radius-sm)` (4px) |
| P0 | 空状态说明文字 14px，规范要求 16px | `.empty-state p` | 改为 `font-size: 16px` |
| P0 | 空状态缺少行动按钮 | `EmptyState` 组件 | 新增"开始对话"按钮，点击聚焦输入框 |
| P1 | 引用角标字号 11px，规范要求 12px | `.citation` | 改为 `font-size: 12px` |
| P1 | 消息气泡缺少 ARIA 标签 | `MessageBubble` 组件 | 新增 `aria-label="您的消息"` / `"KB-AI 回答"` |
| P1 | 消息气泡使用非规范的不对称圆角 | `.message.user/.assistant .message-bubble` | 移除 `border-bottom-*` 不对称圆角，统一 `radius-md` |
| P1 | 输入框字号 15px，应 16px | `.chat-input` | 改为 `font-size: 16px` |
| 功能 | 抽屉式会话历史 | `Drawer` 组件 | 左侧 320px 抽屉，对接 `/api/sessions`，支持新建/切换会话 |
| 功能 | 安全弹出模态 | `ShutdownModal` 组件 | 替换浏览器 `confirm()`，符合 §15.5 §C 内容结构 |
| 功能 | 会话状态持久化 | `App` 组件 | 首次发送自动创建会话，消息写入 SQLite |

---

## 仍存在的偏差 / 待完善项

| 优先级 | 项 | 说明 | 建议 |
|---|---|---|---|
| P1 | 自定义中文字体未加载 | MASTER.md 要求得意黑（标题）、阿里巴巴普惠体 3.0（正文）；原型仅使用系统后备字体 | npm 恢复后通过 Vite + @chinese-fonts 或本地字体文件加载 |
| P2 | 状态圆点缺少加载动画 | MASTER.md 规定加载中用 `pulse` 动画 | 添加 `.status-dot.loading { animation: pulse 1.5s infinite }` |
| P2 | 冷启动进度模态未实现 | §D 6 段启动进度 | 对接 `/api/boot` SSE |
| P2 | 图片预览浮层未实现 | REQ-11 多模态 | 后续对接 `image_paths` |
| P2 | 附件按钮仅为占位 | 无文件选择、多模态图片上传功能 | 后续对接 `/api/chat` 的 `image_paths` |
| P2 | SSE 解析器较简单 | 仅处理 `event:` + `data:` 相邻行，未覆盖多行 data / retry / id 字段 | FastAPI `EventSourceResponse` 当前输出与此兼容，但生产环境建议用 `eventsource-parser` |
| P3 | 未使用 Tailwind / shadcn/ui | 当前为纯 CSS 内联样式；MASTER.md 指定 Tailwind v3 + shadcn/ui | npm 恢复后迁移为工程化项目 |
| P3 | 仅实现聊天主页 | 资料库页、设置页未实现 | 按 §12.4 页面清单扩展 |

---

## 符合规范项（无需修改）

- ✅ 品牌调性：主色 `#1F2937`、背景 `#F5F0E8`、暖黄 `#F4D35E`
- ✅ 信息架构：顶部 nav + 抽屉 + chat-first 主区 + 底部输入区
- ✅ 顶部 nav 高度 56px、无阴影、底部 1px 白线分隔
- ✅ 抽屉宽度 320px，从左侧滑入，头部 56px 与 nav 同高
- ✅ 状态条仅在离线/降级时显示，文案符合 §3.5
- ✅ 消息气泡定位：用户靠右、AI 靠左
- ✅ 引用角标样式：`font-mono` + 蓝色 + hover 下划线
- ✅ 输入区容器圆角 16px、背景 `#EBE3D2`
- ✅ 安全弹出模态宽度 480px、圆角 16px、`shadow-xl`、45% 黑遮罩
- ✅ 动画仅使用 `transform` / `opacity`，时长 150-300ms
- ✅ 支持 `prefers-reduced-motion: reduce`
- ✅ 无模型选择 UI、无账号系统、无 Dashboard
- ✅ ARIA：nav / main / 抽屉 aside / 消息流 `role="log"` / 图标按钮 `aria-label`
- ✅ 后端接口对接：`/api/health` 轮询、`/api/sessions` CRUD、`/api/chat` SSE、`/api/shutdown`

---

## 下一步建议

1. **用户验收当前原型**：浏览器打开 `http://127.0.0.1:8000/` 验证聊天、抽屉、安全弹出模态。
2. **修复 P1 字体问题**：决定是 CDN 加载中文字体，还是等 npm 恢复后工程化加载。
3. **扩展核心页面**（按优先级）：
   - ① 冷启动进度模态（§D，对接 `/api/boot`）
   - ② 资料库页（上传/文档卡片）
   - ③ 设置页（容量显示、版本信息）
   - ④ 多模态图片上传与预览
