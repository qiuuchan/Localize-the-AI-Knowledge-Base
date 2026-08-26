# KB-AI Design System · MASTER.md

> **Status**: ACTIVE · 唯一设计真相源  
> **项目**: KB-AI — U 盘 AI 助手 (本地化"问 AI 帮你资料")  
> **版本**: v1.4  
> **日期**: 2026-07-07  
> **最后评审**: 2026-07-10  
> **维护者**: maintainer(KB-AI 设计 owner)+ AI 代理辅助修订  
> **技术栈**: React + TypeScript + Vite + Tailwind CSS + shadcn/ui  
> **目标读者**: 前端开发者、UI 设计师、QA  
> **生成依据**: ui-ux-pro-max SKILL.md (99 条 UX 指南、10 优先级规则) + KB-AI 前端设计简报  
> **文件位置**: `KB-AI/design-system/MASTER.md` —— 全局唯一设计真相源。`KB-AI/design/design.md` 已废弃为跳转说明页，不再承载 Token、组件或页面规范。
> **裁决原则**: 所有颜色、字体、间距、圆角、阴影、图标、动效、组件状态、页面级规则、无障碍要求均以本文件为准。

---

## 目录

1. [项目概述](#1-项目概述)
2. [视觉叙事与品牌语气](#2-视觉叙事与品牌语气)
3. [专业感体验准则](#3-专业感体验准则)
4. [色彩系统](#4-色彩系统)
5. [排版系统](#5-排版系统)
6. [间距系统](#6-间距系统)
7. [圆角系统](#7-圆角系统)
8. [阴影系统](#8-阴影系统)
9. [图标系统](#9-图标系统)
10. [组件规范](#10-组件规范)
11. [布局规范](#11-布局规范)
12. [动效规范](#12-动效规范)
13. [无障碍规范](#13-无障碍规范)
14. [反模式清单](#14-反模式清单)
15. [页面级覆盖建议](#15-页面级覆盖建议)

---

## 1. 项目概述

### 1.1 产品定义

**KB-AI = 本地化的"问 AI 帮你找资料"工具**。面向**餐饮分公司总经理**（单用户、非技术背景、弱 IT）。

用户把经营文档（Word / PDF / PPT / Excel）喂进 U 盘 AI，问一句经营问题，AI 用 `[1][2]` 脚注引用用户资料原文回答。部署在 1TB 移动 SSD + Win 10/11 + Docker，浏览器访问 `localhost:8080`。

### 1.2 用户画像

| 维度 | 特征 | 设计影响 |
|---|---|---|
| 行业 | 餐饮（可扩展其它服务行业） | 商务基调，拒绝花哨 |
| 角色 | 分公司总经理 / 业务负责人 | 决策场景，重视可追溯 |
| IT 背景 | 弱（像"用微信"一样简单） | 零学习成本、大按钮、亲切文案 |
| 设备 | Windows 10/11 桌面电脑 | 1280-1920px 桌面优先，不深度适配移动端 |
| 单/多用户 | **单用户**（本地、单机） | 不做账号系统、登录页、权限管理 |
| 语言 | 全程中文 | 中文排版优化、亲切如"给老板讲课" |
| 核心诉求 | "答错/瞎答"零容忍 | 脚注引用、来源跳转、原文高亮 |

### 1.3 设计原则（4 条）

| # | 原则 | 解释 | 落地方式 |
|---|---|---|---|
| **P1** | **经典商务** | 经典商务黑灰，主色≤2，辅助色≤2 | 深灰 + 暖黄点缀，无渐变、无玻璃拟态 |
| **P2** | **极简可触** | 像微信一样简单，弱 IT 用户秒懂 | 顶部 nav + 抽屉 + chat-first，无复杂导航层级 |
| **P3** | **可追溯** | 每句回答都有来源，可跳转原文 | `[1][2]` 脚注角标 + 原文高亮 |
| **P4** | **状态透明** | 离线、降级、冷启动，用户必须知道状态 | 状态条（红/黄/绿）、进度条、模态提示 |

### 1.4 技术栈事实

- **React 18 + TypeScript + Vite** — 构建工具
- **Tailwind CSS v3** — 原子化样式
- **shadcn/ui** — 基础组件（Button、Dialog、Input、Sheet、Switch 等）
- **Lucide React** — 图标库（纯 SVG，无 emoji）
- **CSS 变量** — 设计令牌驱动主题（方便后续暗色模式扩展）

### 1.5 设计系统范围

**涵盖**:
- 全局色彩、排版、间距、圆角、阴影、图标、动画 Token
- 12 个核心组件的完整规范（颜色/尺寸/状态/间距/动画）
- 4 页面布局规范（聊天页、上传页、资料库、设置页）
- 4 套 UX 触发器（§A 离线、§B 降级、§C 安全弹出、§D 冷启动）

**不涵盖**（由项目简报 §6 锁定）:
- 无移动端深度适配（仅基础响应）
- 无暗色模式 v1（Token 用 CSS 变量预留，但首版不实现）
- 无 Dashboard / Analytics / 数据可视化图表
- 无账号系统、登录页、模型选择 UI

---

## 2. 视觉叙事与品牌语气

> 本章合并自原 `design/design.md` 中的视觉叙事与文案语气内容。所有具体 Token、尺寸、组件状态仍以本文件后续章节为准；本章只回答"为什么这样设计"与"该怎么说话"。

### 2.1 视觉方向：Industrial + Swiss

KB-AI 的视觉方向是 **Industrial（工业）+ Swiss（瑞士）** 的克制混合：

- **Industrial（工业）**：诚实、功能至上、无装饰、可见结构。KB-AI 是放在 U 盘里的本地工具，不需要假装成云端 SaaS。
- **Swiss（瑞士）**：网格精确、排版清晰、信息密度受控。它服务的是非技术业务负责人，不是开发者控制台。
- **混合后**：界面像一台可靠的商用设备，干净、稳定、可核验，但不冰冷。

| 工业元素 | 商务映射 | KB-AI 表达 |
|---|---|---|
| 裸露金属 | 无渐变、无装饰 | 纯色块、实边框、少阴影 |
| 功能可见 | 信息透明 | 状态条直接告诉用户在线、离线、降级 |
| 零件编号 | 可追溯 | 引用角标 `[1]` `[2]` 像资料编号，可回到原文 |
| 瑞士网格 | 排版秩序 | 所有组件对齐到统一间距系统 |
| 字体即建筑 | 可信层级 | 标题、正文、数据各司其职，不混用装饰字体 |

### 2.2 视觉记忆点

> **极致黑白灰中的一抹暖黄 = 餐饮行业的温度感。**

KB-AI 看起来应像专业厨房里的商用设备：不锈钢台面、黑白瓷砖、清晰标识，少量暖黄只在真正需要用户注意时出现。

暖黄不是装饰色，而是功能性提示：

- 新回答、完成、引用 hover、降级提醒等关键反馈可以使用暖黄。
- 常规文本、普通容器、无意义装饰不使用暖黄。
- 错误、离线、容量高危使用语义红，不用暖黄稀释风险。

一句话记忆：

> KB-AI 像一台专业厨房里的商用设备——不花哨，但你信任它不会坏。

### 2.3 文案语气规范

所有中文文案遵循 **"给老板讲课"** 原则：直接、亲切、可执行，避免技术栈、模型名、错误码和开发者术语暴露给终端用户。

| 不要说 | 要说 | 场景 |
|---|---|---|
| "系统初始化失败" | "启动时出了点问题，正在重试" | 错误提示 |
| "网络不可达" | "网络连接断了，AI 暂时回答不了" | 离线 |
| "模型降级" | "已换用备用方式为您查找" | 降级 |
| "内存溢出" | "文件太大了，请换个小的试试" | 上传错误 |
| "404 Not Found" | "找不到这个内容，您可能输错了" | 搜索无结果 |
| "Session Timeout" | 不出现；本地单用户无登录态 | 账号相关 |
| "API Rate Limit" | "问得太快了，稍等 2 秒再问" | 限流 |
| "Token 不足" | "本月 AI 使用量快用完了" | 用量告警 |
| "docker logs" | "请重新启动 KB-AI；如果仍失败，请联系维护人员" | 用户可见恢复路径 |

### 2.4 设计原则检查

| 原则 | 检查方式 | 已知限制 |
|---|---|---|
| 诚实 | 离线、降级、冷启动、容量风险必须直接告诉用户 | 不向用户暴露模型名、容器名、日志命令 |
| 秩序 | 网格、字号、间距、组件状态必须统一 | 不为单个页面临时发明 token |
| 温度 | 暖黄只承担功能性情绪出口 | 不把暖黄扩散成装饰背景 |
| 克制 | 动效只表达因果关系，150-300ms 为主 | 不使用 bounce / elastic 作为默认反馈 |
| 信任 | 每个回答能追溯来源，引用可回到原文 | 引用缺失时必须给恢复说明，而非只给技术错误 |
| 亲切 | 文案让非技术老板知道下一步做什么 | 避免开发者术语和英文错误码 |

---

## 3. 专业感体验准则

> KB-AI 的专业感不是炫技，而是让非技术用户持续感到：**系统稳、过程清楚、答案可信、出错有路可走**。任何页面或组件实现，都必须服务这个感受。

### 3.1 专业感定义

| 用户感受 | 界面必须做到 | 禁止做法 |
|---|---|---|
| 稳 | 明确显示当前状态、进度、可用能力 | 空白等待、无限 spinner、突然跳转 |
| 清楚 | 每一步都有用户能懂的中文说明 | 暴露模型名、容器名、日志命令、英文错误码 |
| 可信 | 回答带引用，引用能回到原文 | 只给结论，不给来源 |
| 可控 | 高风险操作有确认和结果反馈 | 删除、关闭、弹出等操作无确认 |
| 可恢复 | 出错时告诉用户下一步怎么做 | 只说失败，不给行动路径 |

### 3.2 启动专业感

冷启动不能只显示空白页或转圈。必须使用分阶段进度，让用户知道系统正在准备什么。

推荐结构：

```text
正在为您启动 KB-AI
1/6 检查 U 盘
2/6 启动知识库
3/6 准备文档检索
4/6 连接 AI 服务
5/6 读取历史会话
6/6 准备完成
```

规则：

- 每一步必须有完成 / 进行中 / 等待 / 失败状态。
- 超过预期时间时，用用户可执行文案解释，例如"这一步花的时间有点久，正在继续重试"。
- 不向终端用户显示 `docker logs`、容器名、端口号等技术排查语。
- 完成后给明确入口："进入 KB-AI"，不要自动跳走到用户不知道的位置。

### 3.3 回答专业感

AI 回复的专业感来自 **可核验**，不是来自像专家一样说话。

必须做到：

- 关键结论尽量绑定引用角标，例如 `[1]` `[2]`。
- 引用点击后显示：文档名、位置、原文片段、返回回答入口。
- 如果本地资料不足，明确说"本地资料里没有找到明确答案"，不要编造。
- 如果启用备用方式，只说"已换用备用方式为您查找"，不要暴露服务商或模型名。

推荐回答结构：

```text
根据《门店运营手册》第 3.2 节，红烧肉备料需要提前 2 小时完成。[1]

来源：
[1] 门店运营手册.pdf · §3.2
```

### 3.4 引用专业感

引用角标是 KB-AI 的信任核心，必须比普通链接更稳定、更清楚。

规则：

- 角标形态保持克制，不做胶囊徽章堆叠，不做大面积高亮。
- hover / focus 时提供清晰反馈；键盘可达。
- 点击引用必须能定位到原文；定位失败时说明原因和下一步。
- 原文高亮使用短暂背景提示，不能遮挡正文。

### 3.5 错误专业感

错误提示必须保护用户信心：承认问题、说明影响、给下一步。

| 场景 | 推荐文案 | 必须提供的行动 |
|---|---|---|
| 离线 | 网络连接断了，AI 暂时回答不了。您仍然可以查看历史对话和本地资料。 | 查看历史 / 稍后重试 |
| 本地资料未命中 | 本地资料里没有找到明确答案。 | 查看相关资料 / 换个问法 |
| 启用备用方式 | 已换用备用方式为您查找，回答可能来自公开信息。 | 查看来源 |
| 上传失败 | 文件没有上传成功，请换个文件或稍后再试。 | 重试 / 移除文件 |
| 启动超时 | 启动花的时间太久，请重新启动 KB-AI；如果仍失败，请联系维护人员。 | 重试 / 联系维护人员 |

禁止：

- `API Error`
- `Qwen timeout`
- `docker logs`
- `500 Internal Server Error`
- `模型降级`

### 3.6 关闭与安全弹出专业感

关闭不是普通网页关闭，而是本地设备工具的安全流程。安全弹出必须明确告诉用户会发生什么。

关闭确认必须包含：

- 当前会话已自动保存。
- AI 服务会安全停止。
- 用户可以安全弹出 U 盘。
- 下次使用需要重新启动 KB-AI。

推荐文案：

```text
确定关闭 KB-AI 吗？

关闭后：
- 当前会话已自动保存
- AI 服务会安全停止
- 您可以安全弹出 U 盘
- 下次使用需要重新启动 KB-AI
```

### 3.7 破坏专业感的行为禁令

- 不用通用 AI 客服头像或机器人头像。
- 不显示模型选择器、当前模型名、供应商名或技术降级链。
- 不用 emoji 作为结构性状态图标。
- 不使用 bounce / elastic / 夸张弹跳动效。
- 不用蓝紫渐变、玻璃拟态、Dashboard 化大屏、营销式大数字。
- 不让用户在关键流程里猜系统是否卡住。
- 不用英文错误码替代中文解释。

### 3.8 验收问题

任何新页面或组件交付前，必须回答：

1. 用户是否知道系统现在在做什么？
2. 用户是否知道答案从哪里来？
3. 用户是否知道出问题后下一步做什么？
4. 高风险操作是否有确认、反馈和恢复路径？
5. 是否暴露了用户不需要理解的技术细节？

---

## 4. 色彩系统

### 4.1 设计理念

基于"经典商务黑灰"基调，**深灰（主色）+ 暖黄（辅助色）**的双色方案。暖黄 `#F4D35E` 点缀在极致黑白灰中，代表餐饮行业的"温度感"——专业但不冰冷。

- **主色 ≤ 2**：深灰 `#1F2937` + 纯黑 `#111827`
- **辅助色 ≤ 2**：暖黄 `#F4D35E` + 琥珀 `#D97706`
- **语义色**：错误红 `#B91C1C`、成功绿 `#166534`、警告琥珀 `#D97706`(离线状态复用错
- **所有颜色使用 CSS 变量**，支持 Tailwind 语义命名，预留暗色模式切换能力

### 4.2 CSS 变量定义（`globals.css`）

```css
:root {
  /* ── 主色 / Primary ── */
  --primary: #1F2937;           /* 商务深灰 */
  --primary-foreground: #FFFFFF; /* 主色上的文字 */
  --primary-hover: #374151;      /* hover 状态 */
  --primary-active: #111827;     /* active/press 状态 */
  --primary-subtle: #EBE3D2;     /* 极浅主色背景（选中项、hover 背景）*/

  /* ── 辅助色 / Secondary (暖黄) ── */
  --secondary: #F4D35E;          /* 暖黄点缀 */
  --secondary-foreground: #1F2937; /* 辅助色上的文字 */
  --secondary-hover: #FDE047;    /* 更亮的 hover */
  --secondary-subtle: #FEF9C3;   /* 极浅黄背景（徽章、提示）*/

  /* ── 背景 / Background ── */
  --background: #F5F0E8;         /* 米白主背景(L=0.88,8h 不刺眼) */
  --background-secondary: #F2EBDE; /* 深米次背景(卡片/抽屉/列表交替) */
  --background-tertiary: #EBE3D2; /* 米灰三级背景(输入框/hover/骨架/进度条) */
  --background-overlay: rgba(0, 0, 0, 0.45); /* 模态遮罩 45% 黑 */

  /* ── 文字 / Text ── */
  --foreground: #111827;         /* 主文字（近黑）*/
  --foreground-secondary: #595E66; /* 次文字(加深,新主背景上过 AA 5.75:1) */
  --foreground-tertiary: #9CA3AF;  /* 三级文字（placeholder、disabled）*/
  --foreground-on-primary: #FFFFFF; /* 深灰背景上的文字 */
  --foreground-on-secondary: #1F2937; /* 暖黄背景上的文字 */

  /* ── 边框 / Border ── */
  --border: #DDD3C0;             /* 暖米色默认边框 */
  --border-subtle: #ECE3D0;      /* 浅米极淡边框(分隔线) */
  --border-strong: #D1D5DB;      /* 强调边框（输入框 focus）*/

  /* ── 语义色 / Semantic ── */
  --error: #B91C1C;              /* 错误(加深,新主背景上过 AA 5.70:1) */
  --error-foreground: #FFFFFF;
  --error-subtle: #FEE2E2;       /* 错误浅背景 */
  --error-border: #FECACA;

  --success: #166534;            /* 成功(加深,新主背景上过 AA 6.29:1) */
  --success-foreground: #FFFFFF;
  --success-subtle: #DCFCE7;     /* 成功浅背景 */
  --success-border: #86EFAC;

  --warning: #D97706;            /* 警告、降级 */
  --warning-foreground: #FFFFFF;
  --warning-subtle: #FEF3C7;    /* 警告浅背景（降级条）*/
  --warning-border: #FCD34D;

  --info: #2563EB;              /* 信息（反问卡片、链接）*/
  --info-foreground: #FFFFFF;
  --info-subtle: #DBEAFE;       /* 信息浅背景 */
  --info-border: #93C5FD;


  /* ── 阴影 / Shadow ── */
  --shadow-sm: 0 1px 2px 0 rgba(0, 0, 0, 0.05);
  --shadow-md: 0 1px 3px 0 rgba(0, 0, 0, 0.08), 0 1px 2px 0 rgba(0, 0, 0, 0.04);
  --shadow-lg: 0 4px 6px -1px rgba(0, 0, 0, 0.08), 0 2px 4px -2px rgba(0, 0, 0, 0.04);
  --shadow-xl: 0 10px 15px -3px rgba(0, 0, 0, 0.08), 0 4px 6px -4px rgba(0, 0, 0, 0.04);
  --shadow-inner: inset 0 2px 4px 0 rgba(0, 0, 0, 0.05);

  /* ── 圆角 / Radius ── */
  --radius-0: 0px;
  --radius-sm: 4px;
  --radius-md: 8px;
  --radius-lg: 16px;

  /* ── 动效 / Animation ── */
  --duration-fast: 150ms;
  --duration-normal: 200ms;
  --duration-slow: 300ms;
  --duration-modal: 400ms;
  --easing-default: cubic-bezier(0.4, 0, 0.2, 1); /* 标准状态过渡 */
  --easing-enter: cubic-bezier(0, 0, 0.2, 1);    /* 进入：柔和减速 */
  --easing-exit: cubic-bezier(0.4, 0, 1, 1);    /* 退出：加速离开 */
  --easing-emphasis: cubic-bezier(0.16, 1, 0.3, 1); /* 克制强调：按钮按压、角标出现，无回弹 */
}

/* ── 暗色模式预留（v1 不实现，但 Token 已就绪）── */
[data-theme="dark"] {
  --background: #111827;
  --background-secondary: #1F2937;
  --background-tertiary: #374151;
  --foreground: #F9FAFB;
  --foreground-secondary: #9CA3AF;
  --foreground-tertiary: #6B7280;
  --border: #374151;
  --border-subtle: #1F2937;
  --border-strong: #4B5563;
  --primary-subtle: #374151;
  --error-subtle: rgba(220, 38, 38, 0.15);
  --warning-subtle: rgba(217, 119, 6, 0.15);
  --success-subtle: rgba(22, 163, 74, 0.15);
  --info-subtle: rgba(37, 99, 235, 0.15);
}
```

### 4.3 Tailwind 语义映射（`tailwind.config.js`）

```js
colors: {
  border: "var(--border)",
  input: "var(--border-strong)",
  ring: "var(--primary)",
  background: "var(--background)",
  foreground: "var(--foreground)",
  primary: {
    DEFAULT: "var(--primary)",
    foreground: "var(--primary-foreground)",
    hover: "var(--primary-hover)",
    active: "var(--primary-active)",
    subtle: "var(--primary-subtle)",
  },
  secondary: {
    DEFAULT: "var(--secondary)",
    foreground: "var(--secondary-foreground)",
    hover: "var(--secondary-hover)",
    subtle: "var(--secondary-subtle)",
  },
  destructive: {
    DEFAULT: "var(--error)",
    foreground: "var(--error-foreground)",
    subtle: "var(--error-subtle)",
    border: "var(--error-border)",
  },
  success: {
    DEFAULT: "var(--success)",
    foreground: "var(--success-foreground)",
    subtle: "var(--success-subtle)",
    border: "var(--success-border)",
  },
  warning: {
    DEFAULT: "var(--warning)",
    foreground: "var(--warning-foreground)",
    subtle: "var(--warning-subtle)",
    border: "var(--warning-border)",
  },
  info: {
    DEFAULT: "var(--info)",
    foreground: "var(--info-foreground)",
    subtle: "var(--info-subtle)",
    border: "var(--info-border)",
  },
  muted: {
    DEFAULT: "var(--background-tertiary)",
    foreground: "var(--foreground-tertiary)",
  },
  accent: {
    DEFAULT: "var(--primary-subtle)",
    foreground: "var(--primary)",
  },
  card: {
    DEFAULT: "var(--background-secondary)",
    foreground: "var(--foreground)",
  },
  popover: {
    DEFAULT: "var(--background)",
    foreground: "var(--foreground)",
  },
}
```

### 4.4 色板速查表

| Token | 色值 | 使用场景 | WCAG 对比度 |
|---|---|---|---|
| `primary` | `#1F2937` | 主按钮、顶部 nav、选中态 | 白底: 12.6:1 ✓ |
| `primary-hover` | `#374151` | 主按钮 hover | 白底: 10.1:1 ✓ |
| `primary-active` | `#111827` | 主按钮 active | 白底: 15.3:1 ✓ |
| `secondary` | `#F4D35E` | 暖黄点缀、新消息徽章、重要标记 | 深灰底: 8.4:1 ✓ |
| `secondary-hover` | `#FDE047` | 辅助色 hover | 深灰底: 7.2:1 ✓ |
| `background` | `#F5F0E8` | 米白主背景(L=0.88 不刺眼) | — |
| `background-secondary` | `#F2EBDE` | 深米次背景(卡片/抽屉/列表交替) | — |
| `background-tertiary` | `#EBE3D2` | 米灰三级背景(输入框/hover/骨架/进度条) | — |
| `foreground` | `#111827` | 主标题、正文 | 白底: 15.3:1 ✓ |
| `foreground-secondary` | `#595E66` | 次文字、说明、时间戳 | 白底: 5.7:
| `foreground-tertiary` | `#9CA3AF` | placeholder、disabled、分
| `border` | `#DDD3C0` | 暖米色默认边框、分隔线 | — |
| `border-strong` | `#D1D5DB` | 输入框 focus、强分隔 | — |
| `error` | `#B91C1C` | 错误、离线状态、删除确认 | 白底: 5.7:1 ✓ |
| `success` | `#166534` | 成功、在线状态、完成 | 白底: 4.6:1 ✓ |
| `warning` | `#D97706` | 降级提示、容量告警 | 白底: 3.2:1 ⚠ (仅用于大面积背景+白字) |
| `info` | `#2563EB` | 反问卡片、链接、提示 | 白底: 5.9:1 ✓ |
| `error` (离线) | `#B91C1C` | 离线状态(共用 `error`,见 §13.3) | 白底: 

---

## 5. 排版系统

### 5.1 字体栈（Font Stack）

```css
/* 标题字体 — 得意黑 (Smiley Sans) */
--font-heading: "Smiley Sans", "Microsoft YaHei", "PingFang SC", sans-serif;

/* 正文字体 — 阿里巴巴普惠体 3.0 */
--font-body: "Alibaba PuHuiTi 3.0", "Microsoft YaHei", "PingFang SC", sans-serif;

/* 英文标题 — Playfair Display (衬线, 经典商务感) */
--font-en-heading: "Playfair Display", "Georgia", "Times New Roman", serif;

/* 英文正文 — Inter (无衬线, 高可读) */
--font-en-body: "Inter", "Segoe UI", "Helvetica Neue", Arial, sans-serif;

/* 等宽字体 — 代码/数据/时间戳 */
--font-mono: "JetBrains Mono", "Fira Code", "Consolas", "Monaco", monospace;
```

### 5.2 字体 Personality 与使用场景

| 字体 | Personality | 使用场景 | 原因 |
|---|---|---|---|
| 得意黑 | 现代、几何、略带张力 | 中文标题（H1-H3）、品牌名 "KB-AI" | 几何斜切造形带来现代感，但不喧宾夺主 |
| 阿里巴巴普惠体 3.0 | 中性、清晰、商务 | 中文正文、按钮、标签、表单 | 专为屏显优化，GB 全字库，小字号清晰 |
| Playfair Display | 经典、优雅、权威 | 英文标题、数字展示（如版本号） | 衬线体带来"经典商务"感，与黑体形成层次 |
| Inter | 现代、高可读、中性 | 英文正文、界面标签 | 为大屏/小屏屏显优化，字距合理 |
| JetBrains Mono | 技术、精确、清晰 | 代码块、引用角标 [1]、时间戳、日志 | 等宽，防止数字跳动，技术感但不冰冷 |

### 5.3 字号阶（7 阶）

| Token | 尺寸 | 行高 | 字重 | 字间距 | 用途 | Tailwind |
|---|---|---|---|---|---|---|
| `text-xs` | 12px / 0.75rem | 1.5 (18px) | 400 | 0.01em | 脚注角标、时间戳、标签、状态文字 | `text-xs` |
| `text-sm` | 14px / 0.875rem | 1.5 (21px) | 400 | 0.01em | 次文字、辅助说明、按钮小字 | `text-sm` |
| `text-base` | 16px / 1rem | 1.6 (26px) | 400 | 0.02em | **正文标准**、聊天内容、表单输入 | `text-base` |
| `text-lg` | 18px / 1.125rem | 1.5 (27px) | 500 | 0.01em | 卡片标题、设置项名称 | `text-lg` |
| `text-xl` | 24px / 1.5rem | 1.3 (31px) | 600 | 0 | 页面标题、模态标题 | `text-xl` |
| `text-2xl` | 32px / 2rem | 1.2 (38px) | 700 | -0.01em | 大标题、品牌名 | `text-2xl` |
| `text-3xl` | 48px / 3rem | 1.1 (53px) | 700 | -0.02em | 仅用于品牌展示/欢迎页 | `text-3xl` |

**中文排版特殊规则**:
- 正文行高 **1.6**（高于西文 1.5），CJK 字符需要更多呼吸空间
- 中文标题使用 **-0.01em** 字间距，避免字距松散
- 正文字间距 **0.02em**（约 0.32px @ 16px），提升可读性
- 绝不在正文中使用 `font-weight: 300`（light），中文笔画细会糊
- 中文段落最佳宽度：25-35 个汉字/行（约 500-700px 容器）
- 引用角标 `[1]` 使用 `font-mono` + `text-xs`，与正文形成区分

### 5.4 字重规范

| 字重 | 值 | 使用场景 |
|---|---|---|
| Light | 300 | **禁用**（中文笔画糊） |
| Regular | 400 | 正文、说明、次要信息 |
| Medium | 500 | 按钮文字、标签、选中项、导航 |
| Semibold | 600 | 卡片标题、章节标题、重要数字 |
| Bold | 700 | 页面标题、品牌名、关键数字 |

---

## 6. 间距系统

### 6.1 间距阶（7 阶）

基于 4px 基数，遵循 8px 网格系统。所有间距使用这些阶，禁止随机值。

| Token | 值 | 用途 | Tailwind |
|---|---|---|---|
| `space-1` | 4px / 0.25rem | 图标内边距、最小间隙 | `p-1`, `gap-1` |
| `space-2` | 8px / 0.5rem | 小按钮内边距、文字与图标间距 | `p-2`, `gap-2` |
| `space-3` | 12px / 0.75rem | 输入框内边距、列表项间距 | `p-3`, `gap-3` |
| `space-4` | 16px / 1rem | 卡片内边距、表单字段间距、按钮内边距 | `p-4`, `gap-4` |
| `space-6` | 24px / 1.5rem | 区域间距、模态内边距、抽屉内边距 | `p-6`, `gap-6` |
| `space-8` | 32px / 2rem | 页面区块间距、卡片外边距 | `p-8`, `gap-8` |
| `space-12` | 48px / 3rem | 大区块间距、页面顶部/底部留白 | `p-12`, `gap-12` |

### 6.2 容器宽度

| 容器 | 最大宽度 | 水平内边距 | 说明 |
|---|---|---|---|
| 主内容区 | 无限制（聊天流自适应） | `px-4` (16px) | 聊天内容流不做 max-width 限制，自动换行 |
| 消息气泡最大宽 | 75% 视口宽，最大 768px | — | 防止超宽行导致阅读困难 |
| 资料库卡片网格 | 自适应列，min 280px | `gap-4` (16px) | 使用 CSS Grid |
| 设置页内容区 | 640px | `px-6` | 居中，表单体验最佳 |
| 模态框 | 480px (sm) / 640px (md) | `p-6` | 标准模态宽度 |
| 抽屉 | 320px | `p-4` | 会话历史抽屉固定宽度 |

### 6.3 外边距规范

- **组件之间**：`gap-4` (16px) 标准，紧密排列用 `gap-2` (8px)
- **卡片之间**：`gap-4` (16px) 到 `gap-6` (24px)
- **区块之间**：`gap-8` (32px) 到 `gap-12` (48px)
- **页面顶部**（nav 下方）：`pt-4` (16px) 或紧贴状态条
- **页面底部**：`pb-4` (16px) 最小，确保内容不被底部遮挡

---

## 7. 圆角系统

> **收敛说明**：原 `design/design.md` 已废弃为跳转说明页，不再承载任何 Token。本文件是唯一规范源。

### 7.1 圆角阶（4 阶）

| Token | 值 | 使用场景 | 理由 |
|---|---|---|---|
| `radius-0` | 0px | 顶部 nav、状态条、全宽按钮、分割线 | 方正 = 商务、稳定、可信赖 |
| `radius-sm` | 4px | 输入框、小按钮、标签、角标 | 微圆，减少尖锐感但不幼稚 |
| `radius-md` | 8px | 卡片、消息气泡、模态框、抽屉 | 标准圆角，友好但专业 |
| `radius-lg` | 16px | 大卡片、欢迎页、空状态插画容器、**聊天输入框(核心交互区例外,见 §10.2)** | 最大圆角,大面积容器或核心交互区 |

### 7.2 使用规则

- **圆角一致原则**：同一层级使用同一圆角。例如所有卡片统一 `radius-md`，不混用 4/8/12px
- **圆角不嵌套**：圆角容器内嵌套另一个圆角容器时，内层圆角 ≤ 外层圆角
- **按钮圆角**：默认 `radius-sm` (4px)，大按钮 `radius-md` (8px)
- **消息气泡**：用户消息 `radius-md` (8px)，AI 消息 `radius-md` (8px)，但方向不同（左/右）
- **禁止圆角**：顶部 nav、状态条、进度条——这些元素需要全宽平直，体现商务严肃感

---

## 8. 阴影系统

### 8.1 阴影阶（4 阶 + 内阴影）

| Token | 值 | 使用场景 | 强度描述 |
|---|---|---|---|
| `shadow-sm` | `0 1px 2px 0 rgba(0,0,0,0.05)` | 卡片默认、列表项 | 几乎不可见，仅在白色背景上区分层次 |
| `shadow-md` | `0 1px 3px 0 rgba(0,0,0,0.08), 0 1px 2px 0 rgba(0,0,0,0.04)` | 按钮 hover、下拉菜单、小浮层 | 轻量级，暗示可交互 |
| `shadow-lg` | `0 4px 6px -1px rgba(0,0,0,0.08), 0 2px 4px -2px rgba(0,0,0,0.04)` | 模态框、抽屉、悬浮面板 | 中度，从背景中"弹出" |
| `shadow-xl` | `0 10px 15px -3px rgba(0,0,0,0.08), 0 4px 6px -4px rgba(0,0,0,0.04)` | 全屏模态、toast 通知 | 最强，覆盖层级最高 |
| `shadow-inner` | `inset 0 2px 4px 0 rgba(0,0,0,0.05)` | 输入框内阴影（可选，极轻） | 暗示"凹陷"，但首版不用 |

### 8.2 使用规则

- **极轻原则**：KB-AI 是"经典商务"，阴影必须克制。90% 的组件使用 `shadow-sm` 或不用阴影
- **无阴影区**：顶部 nav、状态条、聊天消息气泡、正文区域——保持平实，不用阴影
- **阴影即层级**：只有"浮于内容之上"的组件才用阴影（模态、抽屉、下拉、toast）
- **无彩色阴影**：所有阴影使用纯黑 `rgba(0,0,0, x)`，不使用带色相的阴影
- **阴影 + 遮罩组合**：模态弹出时，使用 `shadow-lg` + `background-overlay`（45% 黑遮罩）

---

## 9. 图标系统

### 9.1 图标库

**Lucide React**（纯 SVG，轻量，可 Tree-shaking）

```bash
npm install lucide-react
```

### 9.2 图标尺寸规范

| Token | 尺寸 | 使用场景 | 触摸目标 |
|---|---|---|---|
| `icon-xs` | 12px | 内联小图标、角标、状态指示 | 父容器 ≥ 24px |
| `icon-sm` | 16px | 按钮内图标、表单前缀 | 父容器 ≥ 32px |
| `icon-md` | 20px | 导航图标、列表项图标 | 父容器 ≥ 40px |
| `icon-lg` | 24px | 主要操作图标、空状态图标 | 父容器 ≥ 48px |
| `icon-xl` | 32px | 大空状态、欢迎页图标 | 父容器 ≥ 48px |

### 9.3 图标状态规范

| 状态 | 视觉表现 | 用途 |
|---|---|---|
| 默认 | `stroke: currentColor` + `stroke-width: 2` | 标准图标 |
| hover | `opacity: 0.7` | 悬停弱化（非主操作） |
| active | `stroke: var(--primary)` | 选中/激活状态 |
| disabled | `opacity: 0.3` + `cursor: not-allowed` | 不可操作 |
| 加载 | `animate-spin` + `opacity: 0.5` | 旋转加载图标 |

### 9.4 图标语义表（核心图标映射）

| 语义 | 图标名 | 尺寸 | 用途 |
|---|---|---|---|
| 品牌/知识 | `BookOpen` | 20px | 顶部 nav "KB-AI" 标志旁 |
| 对话 | `MessageSquare` | 20px | 导航 "对话" 项 |
| 资料库 | `Library` | 20px | 导航 "资料库" 项 |
| 设置 | `Settings` | 20px | 导航 "设置" 项 |
| 发送 | `Send` | 16px | 聊天发送按钮 |
| 附件 | `Paperclip` | 16px | 聊天附件按钮 |
| 图片 | `Image` | 16px | 图片上传按钮 |
| 新建 | `Plus` | 16px | 新建会话按钮 |
| 删除 | `Trash2` | 16px | 删除会话/文档 |
| 关闭 | `X` | 16px | 关闭模态、抽屉、toast |
| 搜索 | `Search` | 16px | 搜索输入框前缀 |
| 上传 | `Upload` | 24px | 拖拽上传区主图标 |
| 文档 | `FileText` | 20px | 文档卡片图标 |
| PDF | `File` | 20px | PDF 文件类型图标 |
| Excel | `Table` | 20px | Excel 文件类型图标 |
| 成功 | `CheckCircle2` | 16px | 成功状态 |
| 错误 | `XCircle` | 16px | 错误状态 |
| 警告 | `AlertTriangle` | 16px | 警告状态 |
| 信息 | `Info` | 16px | 信息提示 |
| 离线 | `WifiOff` | 16px | 离线状态指示 |
| 在线 | `Wifi` | 12px | 在线状态指示（小绿点） |
| 加载 | `Loader2` | 16px | 旋转加载图标 |
| 更多 | `MoreHorizontal` | 16px | 更多操作菜单 |
| 展开 | `ChevronRight` | 16px | 抽屉展开指示 |
| 折叠 | `ChevronLeft` | 16px | 抽屉折叠指示 |
| 安全弹出 | `Eject` | 20px | 安全弹出按钮 |
| 电源 | `Power` | 20px | 关闭按钮 |

**关键规则**：禁止用 emoji 作为结构性图标。所有图标必须是 Lucide SVG。

---

## 10. 组件规范

### 10.1 按钮（Button）

#### 变体（Variants）

| 变体 | 背景色 | 文字色 | 边框 | 圆角 | 阴影 | 用途 |
|---|---|---|---|---|---|---|
| `primary` | `var(--primary)` `#1F2937` | `var(--primary-foreground)` 白 | 无 | `radius-sm` 4px | `shadow-sm` | 主操作：发送、确认、保存 |
| `secondary` | `var(--secondary)` `#F4D35E` | `var(--secondary-foreground)` `#1F2937` | 无 | `radius-sm` 4px | `shadow-sm` | 次要操作：新建、上传、导出 |
| `outline` | `transparent` | `var(--primary)` `#1F2937` | `1px solid var(--border)` | `radius-sm` 4px | 无 | 第三操作：取消、更多 |
| `ghost` | `transparent` | `var(--foreground-secondary)` `#
| `destructive` | `var(--error)` `#B91C1C` | 白 | 无 | `radius
| `link` | `transparent` | `var(--info)` `#2563EB` | 无 | 0 | 无 | 文字链接：查看详情、原文跳转 |

#### 尺寸（Sizes）

| 尺寸 | 高度 | 水平内边距 | 字号 | 用途 |
|---|---|---|---|---|
| `sm` | 32px | 12px | 12px | 小按钮：角标操作、表单内按钮 |
| `default` | 40px | 16px | 14px | 标准按钮：发送、确认、保存 |
| `lg` | 48px | 24px | 16px | 大按钮：欢迎页 CTA、模态主按钮 |
| `icon` | 40px | 0 | — | 图标按钮：发送按钮、附件按钮（正方形） |

#### 状态（States）

| 状态 | 变化 | 过渡参数 |
|---|---|---|
| `default` | 如上表 | — |
| `hover` | 背景色 → hover 色；`shadow-sm` → `shadow-md`；若 ghost → 背景 `var(--primary-subtle)` | `200ms var(--easing-default)` |
| `active` | 背景色 → active 色；`scale: 0.97`（微压） | `100ms var(--easing-default)` |
| `focus` | `outline: 2px solid var(--primary)` + `outline-offset: 2px` | 无（即时） |
| `disabled` | `opacity: 0.4` + `cursor: not-allowed` + 无 hover/click 效果 | `200ms` |
| `loading` | 左侧显示 `Loader2` 旋转图标 + 文字后移 + `cursor: wait` | 旋转 `1s linear infinite` |

#### 间距规则

- 按钮内部：图标 + 文字间距 `gap-2` (8px)
- 按钮之间：水平 `gap-3` (12px)，垂直 `gap-4` (16px)
- 按钮与相邻组件：最小 `gap-4` (16px)
- 触摸目标：最小 40×40px（桌面端不低于 32×32px，但尽量 40px+）

### 10.2 输入框（Input）

#### 基础样式

| 属性 | 值 | 说明 |
|---|---|---|
| 高度 | 48px | 与按钮 `default` 一致，视觉对齐 |
| 水平内边距 | 16px | `px-4` |
| 垂直内边距 | 12px | `py-3` |
| 背景色 | `var(--background-tertiary)` `#EBE3D2` | 略灰，区分于纯白背景 
| 边框 | `1px solid var(--border)` `#DDD3C0` | 默认细边框 |
| 圆角 | `radius-md` 8px | 比按钮稍大，亲和 |
| 字号 | `text-base` 16px | 避免 iOS 自动缩放 |
| 文字色 | `var(--foreground)` `#111827` | 主文字 |
| placeholder | `var(--foreground-tertiary)` `#9CA3AF` | 浅灰提示 |

#### 状态

| 状态 | 变化 | 过渡参数 |
|---|---|---|
| `default` | 如上 | — |
| `hover` | 边框色 → `var(--border-strong)` `#D1D5DB` | `200ms` |
| `focus` | 边框色 → `var(--primary)` `#1F2937`；`ring: 2px var(--primary)` + `ring-offset: 2px` | `200ms` |
| `error` | 边框色 → `var(--error)` `#B91C1C`；背景 → `var(--error
| `disabled` | `opacity: 0.5` + `cursor: not-allowed` + 背景 `var(--background-secondary)` | `200ms` |
| `filled` | 背景 → 白 `#FFFFFF`；边框 → `var(--border-strong)` | 即时 |

#### 聊天输入框（特殊组件）

聊天输入框是 KB-AI 的核心交互区域，**不是普通 Input**。

```
┌────────────────────────────────────────────────────────────┐
│ [Paperclip]  ┌──────────────────────────────────────────────┐  [Send] │
│     │  问 AI 经营问题...                              │    │
│     └──────────────────────────────────────────────┘      │
└────────────────────────────────────────────────────────────┘
```

| 属性 | 值 |
|---|---|
| 容器高度 | 自适应，最小 48px，最大 160px（多行） |
| 容器背景 | `var(--background-tertiary)` `#EBE3D2` |
| 容器圆角 | `radius-lg` 16px（大面积，最大圆角） |
| 内边距 | `p-3` (12px) 左/右/上，底部 `pb-3` + 预留按钮空间 |
| 附件按钮 | 左侧，`icon` 尺寸按钮（40×40px），`ghost` 变体 |
| 发送按钮 | 右侧，`icon` 尺寸按钮（40×40px），`primary` 变体，圆形 `radius-0` 或 `radius-sm` |
| 字号 | `text-base` 16px |
| 占位符 | "问 AI 经营问题，比如：招牌菜红烧肉怎么做？" |
| 多行 | 支持 Shift+Enter 换行，最大 5 行 |
| 聚焦 | 容器边框 → `var(--primary)` `#1F2937`，`ring: 2px` |

### 10.3 卡片（Card）

用于文档卡片、设置项、提示卡片。

| 属性 | 值 | 说明 |
|---|---|---|
| 背景 | `var(--background-secondary)` `#F2EBDE` | 次背景，与主背景区分 
| 边框 | `1px solid var(--border)` `#DDD3C0` | 默认细边框 |
| 圆角 | `radius-md` 8px | 标准圆角 |
| 阴影 | `shadow-sm` 或无 | 平实为主，需要层级时加 shadow-sm |
| 内边距 | `p-4` (16px) 标准，`p-6` (24px) 大卡片 |
| 标题字号 | `text-lg` 18px | 卡片标题 |
| 内容字号 | `text-sm` 14px 或 `text-base` 16px | 根据内容量 |
| hover | 边框 → `var(--border-strong)`；阴影 → `shadow-md`；微升 `translateY(-1px)` | `200ms` |

#### 文档卡片（特殊）

| 属性 | 值 |
|---|---|
| 布局 | 左侧文件图标 + 右侧文件名/大小/状态 |
| 文件图标 | 24px，根据类型变色（PDF=红、Excel=绿、Word=蓝、PPT=橙、通用=灰） |
| 进度条 | 高度 4px，底部全宽，`radius-0` |
| 错误状态 | 边框 → `var(--error)`，顶部加 `4px` 错误色条 |
| 完成状态 | 右侧显示绿色 `CheckCircle2` 图标 |

### 10.4 模态框（Modal / Dialog）

| 属性 | 值 | 说明 |
|---|---|---|
| 遮罩 | `var(--background-overlay)` `rgba(0,0,0,0.45)` | 45% 黑，确保前景可读 |
| 背景 | `var(--background)` `#FFFFFF` | 纯白 |
| 圆角 | `radius-lg` 16px | 最大圆角，体现"浮层" |
| 阴影 | `shadow-xl` | 最强阴影 |
| 宽度 | 480px (sm) / 640px (md) | 标准模态宽度 |
| 内边距 | `p-6` (24px) | 内部统一间距 |
| 标题 | `text-xl` 24px，`font-weight: 600` | 模态标题 |
| 内容 | `text-base` 16px，`text-foreground-secondary` | 说明文字 |
| 按钮区 | 底部，`flex justify-end`，`gap-3` (12px) | 右对齐，主按钮在右 |

#### 状态

| 状态 | 动画 |
|---|---|
| 打开 | 遮罩 `opacity: 0 → 1` (150ms)；内容 `scale: 0.95 → 1` + `opacity: 0 → 1` + `translateY(8px → 0)` (200ms) |
| 关闭 | 内容 `scale: 1 → 0.95` + `opacity: 1 → 0` + `translateY(0 → 8px)` (150ms)；遮罩 `opacity: 1 → 0` (100ms) |
| 滚动锁定 | body `overflow: hidden` | 防止背景滚动 |
| ESC 关闭 | 支持 `Escape` 键关闭 | 无障碍要求 |
| 点击遮罩关闭 | 支持（除确认类模态外） | 便捷操作 |

### 10.5 抽屉（Sheet / Drawer）

用于会话历史抽屉。

| 属性 | 值 | 说明 |
|---|---|---|
| 位置 | 左侧 | 从左侧滑入 |
| 宽度 | 320px | 固定宽度 |
| 背景 | `var(--background)` `#FFFFFF` | 纯白 |
| 边框 | 右侧 `1px solid var(--border)` | 分隔线 |
| 阴影 | 打开时右侧 `shadow-lg` | 暗示层级 |
| 头部 | 标题 + 新建按钮，`h-14` (56px) 与顶部 nav 同高 | 视觉对齐 |
| 列表项 | 高 48px，`px-4` (16px)，`gap-3` (12px) | 可点击区域 |
| 点击遮罩关闭 | 支持(除"删除确认"等关键操作外) | 便捷操作 |
| 空状态 | 居中图标 + 文字，`text-foreground-tertiary` | 无会话时显示 |

#### 动画

| 动作 | 起始状态 | 结束状态 | 参数 |
|---|---|---|---|
| 打开 | `translateX(-100%)` | `translateX(0)` | `300ms var(--easing-enter)` |
| 关闭 | `translateX(0)` | `translateX(-100%)` | `250ms var(--easing-exit)` |
| 遮罩 | `opacity: 0` | `opacity: 1` | `200ms`（与抽屉同步） |
| 列表项入场 | `opacity: 0` + `translateX(-8px)` | `opacity: 1` + `translateX(0)` | `200ms`，每项 stagger 30ms |

### 10.6 开关（Switch）

用于设置页开关项。

| 属性 | 值 | 说明 |
|---|---|---|
| 轨道宽 | 44px | 标准开关宽 |
| 轨道高 | 24px | 标准开关高 |
| 轨道圆角 | `9999px`（完全圆形） | 标准开关圆角 |
| 轨道背景（关） | `var(--background-tertiary)` `#EBE3D2` | 浅灰 |
| 轨道背景（开） | `var(--primary)` `#1F2937` | 主色 |
| 轨道边框（关） | `1px solid var(--border)` | 细边框 |
| 滑块直径 | 20px | 轨道内居中 |
| 滑块背景 | 白 `#FFFFFF` | 纯白滑块 |
| 滑块阴影 | `shadow-sm` | 微浮起 |

#### 状态

| 状态 | 动画 |
|---|---|
| 切换（关→开） | 滑块 `translateX(0 → 20px)`，轨道背景 `#EBE3D2 → #1F293
| 切换（开→关） | 反向，`200ms var(--easing-default)` |
| hover | 轨道 `opacity: 0.9`，`100ms` |
| disabled | `opacity: 0.5`，`cursor: not-allowed` |
| focus | 轨道外圈 `ring: 2px var(--primary)` + `ring-offset: 2px` |

### 10.7 标签（Tag / Badge）

用于分类标签、文档类型、状态指示。

| 变体 | 背景 | 文字色 | 边框 | 圆角 | 字号 | 内边距 |
|---|---|---|---|---|---|---|
| `default` | `var(--primary-subtle)` `#EBE3D2` | `var(--pri
| `secondary` | `var(--secondary-subtle)` `#FEF9C3` | `var(--warning)` `#D97706` | 无 | `radius-sm` 4px | 12px | `px-2 py-1` |
| `outline` | `transparent` | `var(--primary)` | `1px solid var(--border)` | `radius-sm` 4px | 12px | `px-2 py-1` |
| `destructive` | `var(--error-subtle)` `#FEE2E2` | `var(--e
| `success` | `var(--success-subtle)` `#DCFCE7` | `var(--suc
| `warning` | `var(--warning-subtle)` `#FEF3C7` | `var(--warning)` `#D97706` | 无 | `radius-sm` 4px | 12px | `px-2 py-1` |

**可删除标签**：右侧显示 `X` 小图标（12px），hover 时图标显示/加深。

### 10.8 进度条（Progress）

用于冷启动、文档解析、上传进度。

#### 基础样式

| 属性 | 值 | 说明 |
|---|---|---|
| 容器高 | 4px（细条）/ 8px（标准） | 根据场景选择 |
| 容器背景 | `var(--background-tertiary)` `#EBE3D2` | 浅灰轨道 |
| 容器圆角 | `9999px`（完全圆形） | 标准进度条圆角 |
| 填充色 | `var(--primary)` `#1F2937` | 主色填充 |
| 填充圆角 | 同容器 | 两端圆形 |

#### 特殊变体

| 变体 | 填充色 | 使用场景 |
|---|---|---|
| 冷启动 | `var(--secondary)` `#F4D35E` | 暖黄填充，温度感 |
| 上传 | `var(--primary)` `#1F2937` | 标准主色 |
| 错误 | `var(--error)` `#B91C1C` | 失败/超时 |
| 成功 | `var(--success)` `#166534` | 完成 |
| 降级 | `var(--warning)` `#D97706` | 降级处理中 |
| 不确定 | 动画滑块 `translateX` 循环 | 无法预估进度时 |

#### 动画

| 类型 | 动画描述 | 参数 |
|---|---|---|
| 进度填充 | 宽度从 `0%` 到目标百分比 | `width: 0% → N%` + `300ms var(--easing-enter)` |
| 不确定 | 滑块从左到右循环 | `translateX(-100% → 100%)` + `1.5s linear infinite` |
| 完成 | 填充色闪变一次 | 背景色 → `var(--success)` → 保持，`200ms` |
| 错误 | 填充色闪变 + 抖动 | 背景色 → `var(--error)` + `translateX(±2px)` 抖动 3 次，`300ms` |

### 10.9 消息气泡（Chat Bubble）

KB-AI 最核心的 UI 组件。

#### 用户消息气泡

```
┌────────────────────────┐
│  用户的问题内容在这里    │
│  支持多行               │
└────────────────────────┘
                    14:32
```

| 属性 | 值 | 说明 |
|---|---|---|
| 背景 | `var(--primary)` `#1F2937` | 主色，用户消息深色 |
| 文字色 | 白 `#FFFFFF` | 主色上的白字 |
| 圆角 | `radius-md` 8px | 标准圆角 |
| 最大宽 | 75% 视口，最大 768px | 防止超宽 |
| 内边距 | `p-4` (16px) | 内容留白 |
| 字号 | `text-base` 16px | 正文 |
| 时间戳 | `text-xs` 12px，`text-foreground-tertiary` | 右侧，消息下方 |
| 定位 | 右侧（`margin-left: auto`） | 用户消息靠右 |
| 箭头 | 无 | 无气泡箭头，扁平设计 |

#### AI 消息气泡

```
        KB-AI
┌────────────────────────┐
│  AI 回答内容在这里，可  │
│  能包含 [1] 引用角标。  │
│  点击角标可跳原文。     │
└────────────────────────┘
                    14:32
```

| 属性 | 值 | 说明 |
|---|---|---|
| 背景 | `var(--background-secondary)` `#F2EBDE` | 次背景，浅色 |
| 文字色 | `var(--foreground)` `#111827` | 主文字 |
| 圆角 | `radius-md` 8px | 标准圆角 |
| 最大宽 | 75% 视口，最大 768px | 同用户 |
| 内边距 | `p-4` (16px) | 内容留白 |
| 字号 | `text-base` 16px | 正文 |
| 发件人标签 | 顶部 `KB-AI`，`text-xs` 12px，`font-weight: 500`，`text-foreground-secondary` | 标识 AI 消息 |
| 时间戳 | `text-xs` 12px，`text-foreground-tertiary` | 右侧,消息下方(与用户消息时间戳对齐) |
| 定位 | 左侧（`margin-right: auto`） | AI 消息靠左 |

#### 引用角标（Citation Badge）

```
...回答内容 [1] 还有 [2] 更多内容。
```

| 属性 | 值 | 说明 |
|---|---|---|
| 外观 | `[1]` `[2]` 方括号数字 | 纯文本角标，非按钮 |
| 字体 | `font-mono` | JetBrains Mono |
| 字号 | `text-xs` 12px | 小字 |
| 文字色 | `var(--info)` `#2563EB` | 蓝色，可点击感 |
| 背景 | `transparent` | 无背景，仅文字色区分 |
| hover | 文字色 → `var(--primary)`；下划线 `text-decoration: underline` | `150ms` |
| 点击 | 触发原文高亮 + 滚动定位 | 即时 |
| 间距 | 与文字间距 `1px`（紧贴文字） | 视觉上属于文字流 |
| 元信息提示 | hover 时显示 tooltip：`[1] 经营手册.pdf · §3.2` | `200ms` 延迟显示 |

### 10.10 角标（Badge / Status Indicator）

#### 状态圆点

| 状态 | 颜色 | 尺寸 | 动画 |
|---|---|---|---|
| 在线 | `var(--success)` `#166534` | 8px 圆点 | 无 |
| 离线 | `var(--error)` `#B91C1C` | 8px 圆点 | 无 |
| 降级 | `var(--warning)` `#D97706` | 8px 圆点 | 无 |
| 加载中 | `var(--primary)` `#1F2937` | 8px 圆点 | `pulse` 动画，`1.5s ease-in-out infinite` |
| 未读消息 | `var(--error)` `#B91C1C` | 16px 圆，含数字 | 无 |

#### 数量徽章（Notification Badge）

| 属性 | 值 |
|---|---|
| 背景 | `var(--error)` `#B91C1C` |
| 文字色 | 白 `#FFFFFF` |
| 字号 | `text-xs` 12px |
| 圆角 | `9999px`（完全圆形） |
| 最小宽 | 16px（单行数字） |
| 位置 | 图标右上角，偏移 `translate(-4px, -4px)` |
| 最大数字 | 显示 `99+` 当超过 99 |

---

## 11. 布局规范

### 11.1 全局布局结构

```
┌────────────────────────────────────────────────────────────┐ ← 顶部 nav (56px)
│  KB-AI [BookOpen]   对话   资料库   设置          [●在线] [Power]  │
├────────────────────────────────────────────────────────────┤ ← 状态条（可选，离线/降级时显示）
│ [离线] 离线模式 — 您可以查看历史记录，但 AI 暂时无法回答      │
│ [降级] 已降级到网络搜索，结果来自公开网络                     │
├──────────┬─────────────────────────────────────────────────┤
│          │                                                 │
│  抽屉     │              主内容区                          │
│ (320px)  │         聊天对话流（默认）                       │
│  会话历史 │                                                 │
│          │  ┌────────────────────────┐                   │
│ [+] 新建 │  │  用户: 问题内容...      │  ← 用户消息靠右    │
│          │  └────────────────────────┘                   │
│ 会话 1   │                                                 │
│ 会话 2   │  ┌────────────────────────┐                   │
│ 会话 3   │  │  KB-AI: 回答内容 [1]    │  ← AI 消息靠左     │
│          │  └────────────────────────┘                   │
│          │                                                 │
│          │         ┌──────────────────────────┐         │
│          │         │  [Paperclip] 问 AI 经营问题...  [Send]  │  ← 输入区          │
│          │         └──────────────────────────┘         │
│          │                                                 │
├──────────┴─────────────────────────────────────────────────┤
```

### 11.2 顶部导航（Top Nav）

| 属性 | 值 | 说明 |
|---|---|---|
| 高度 | 56px（`h-14`） | 固定高度，标准桌面导航高 |
| 背景 | `var(--primary)` `#1F2937` | 主色，深色 |
| 文字色 | 白 `#FFFFFF` | 主色上的白字 |
| 定位 | `fixed` 顶部，`z-index: 50` | 始终可见 |
| 内边距 | `px-4` (16px) | 水平内边距 |
| 左侧 | 品牌区：图标 `BookOpen` (20px) + "KB-AI" 文字 | 品牌标识 |
| 中部 | 导航项：`MessageSquare` + "对话" / `Library` + "资料库" / `Settings` + "设置" | 导航链接 |
| 右侧 | 状态指示器（8px 圆点 + 状态文字）+ 关闭按钮 `Power` | 状态和操作 |
| 导航项间距 | `gap-6` (24px) | 导航项之间 |
| 选中态 | 文字下 `2px` 底线 `var(--secondary)` `#F4D35E` | 暖黄指示当前页 |
| hover | 文字 `opacity: 0.8` | 快速反馈 |
| 圆角 | `radius-0` 0px | 顶部 nav 全宽平直 |
| 阴影 | 无（底部 `1px solid rgba(255,255,255,0.1)` 细线分隔） | 平实，不浮起 |

### 11.3 状态条（Status Bar）

状态条位于顶部 nav 下方，**仅在离线或降级时显示**。

| 变体 | 背景 | 文字色 | 高度 | 动画 |
|---|---|---|---|---|
| 离线（§A） | `var(--error)` `#B91C1C` | 白 | 40px | 从顶部滑入 `tran
| 降级（§B） | `var(--warning)` `#D97706` | 白 | 40px | 从顶部滑入，`300ms` |
| 在线恢复 | 无（条消失） | — | — | 向上滑出 `translateY(0 → -100%)`，`200ms` |
| 容量告警 | 告警级别对应色 | 白 | 40px | 同离线 |

**内容结构**：
```
[状态图标] 状态文字说明                    [关闭按钮 X（降级条可关，离线条不可关）]
```

- 离线条：不可关闭，一直显示直到网络恢复
- 降级条：可关闭（`X` 按钮），但下次降级重新触发
- 30s 自动重检：网络恢复时状态条自动消失，无操作

### 11.4 主内容区（Main Content）

| 属性 | 值 | 说明 |
|---|---|---|
| 背景 | `var(--background)` `#FFFFFF` | 纯白 |
| 顶部内边距 | 16px（无状态条时）/ 56px（有状态条时） | 预留 nav + 状态条 |
| 水平内边距 | `px-4` (16px) 到 `px-8` (32px) | 根据内容区调整 |
| 底部内边距 | `pb-24` (96px) | 预留底部输入区空间 |
| 滚动 | `overflow-y: auto` | 主区可滚动 |
| 最小高 | `calc(100vh - 56px)` | 填满视口减去 nav |

### 11.5 底部输入区（Bottom Input）

| 属性 | 值 | 说明 |
|---|---|---|
| 定位 | `sticky` 底部或 `fixed` 底部 | 始终在底部可见 |
| 背景 | `var(--background)` `#FFFFFF` 或 `rgba(255,255,255,0.95)` | 半透明，滚动时可见内容 |
| 上边框 | `1px solid var(--border)` | 与内容区分隔 |
| 内边距 | `px-4 py-3` (16×12px) | 标准内边距 |
| 最大宽 | 与主内容区一致 | 居中或自适应 |
| 高度 | 自适应（48px 到 160px） | 根据输入内容 |
| 布局 | 左侧附件 + 中间文本区 + 右侧发送 | 水平布局 |
| 移动端安全区 | `pb-4` 底部额外内边距 | 防止被系统栏遮挡 |

### 11.6 响应式断点

KB-AI 面向 Win 10/11 桌面，**桌面优先**，响应式仅做基础适配。

| 断点 | 宽度 | 调整 | 说明 |
|---|---|---|---|
| `sm` | ≥640px | 基础样式 | 最小桌面宽度 |
| `md` | ≥768px | 抽屉固定 320px | 标准平板/小桌面 |
| `lg` | ≥1024px | 主内容区 80% 居中 | 标准桌面 |
| `xl` | ≥1280px | 主内容区 75% 居中，最大 1200px | **目标桌面** |
| `2xl` | ≥1536px | 主内容区 70% 居中，最大 1200px | 大屏桌面 |

**不做的响应式**：
- 不做移动端底部导航（无移动 App）
- 不做折叠汉堡菜单（桌面始终显示完整 nav）
- 不做竖屏/横屏特殊适配（桌面默认横屏）
- 不做触摸手势优化（桌面鼠标操作为主）

---

## 12. 动效规范

### 12.1 全局动画 Token

```css
:root {
  /* 持续时间 */
  --duration-instant: 100ms;     /* 状态微变、opacity 切换 */
  --duration-fast: 150ms;        /* 按钮 hover、图标切换 */
  --duration-normal: 200ms;      /* 标准过渡：hover、focus、状态切换 */
  --duration-slow: 300ms;        /* 抽屉滑入、模态弹出 */
  --duration-modal: 400ms;       /* 复杂模态、页面过渡 */
  
  /* 缓动曲线 */
  --easing-default: cubic-bezier(0.4, 0, 0.2, 1);  /* 标准状态过渡 */
  --easing-enter: cubic-bezier(0, 0, 0.2, 1);        /* 进入：柔和减速 */
  --easing-exit: cubic-bezier(0.4, 0, 1, 1);          /* 退出：加速离开 */
  --easing-emphasis: cubic-bezier(0.16, 1, 0.3, 1);   /* 克制强调：按钮按压、角标出现，无回弹 */
  --easing-linear: linear;                           /* 进度条、加载、shimmer */
  
  /* Stagger */
  --stagger-base: 30ms;         /* 列表项入场间隔 */
  --stagger-max: 300ms;         /* 最大 stagger 累计（避免过慢）*/
}
```

### 12.2 性能约束

- **仅使用 `transform` 和 `opacity`**：绝不动画 `width`、`height`、`top`、`left`、`margin`、`padding`
- **使用 `will-change: transform, opacity`** 仅在动画即将发生时添加，动画结束后移除
- **避免动画布局属性**：`will-change` 不能滥用，否则触发 GPU 内存占用
- **60fps 目标**：每帧渲染 < 16ms

### 12.3 场景动画表

#### 消息流式出现（AI 打字效果）

| 属性 | 值 | 说明 |
|---|---|---|
| 触发 | SSE 流式接收到新字符 | 后端流式推送 |
| 动画 | 无逐字符动画 | 字符直接出现，不逐字 fade（避免闪烁） |
| 光标 | 末尾闪烁光标 `|`（`opacity` 脉冲） | `animate-pulse` 1.5s |
| 段落完成 | 整段 `opacity: 0.5 → 1` + `translateY(2px → 0)` | `150ms`（仅新段落） |
| 引用角标出现 | 角标 `opacity: 0 → 1` + `scale: 0.8 → 1` | `200ms`，延迟 100ms |

#### 新消息滑入

| 属性 | 值 | 说明 |
|---|---|---|
| 触发 | 用户发送或 AI 完整回复到达 | 消息完整时 |
| 起始状态 | `opacity: 0` + `translateY(12px)` + `scale: 0.98` | 从下方略小略淡 |
| 结束状态 | `opacity: 1` + `translateY(0)` + `scale: 1` | 正常位置 |
| 持续时间 | `300ms` | 可见但不拖沓 |
| 缓动 | `var(--easing-enter)` | 柔和减速 |
| 列表 stagger | 多个消息同时入场时，间隔 `30ms` | 避免堆叠感 |

#### 抽屉打开/关闭

| 属性 | 值 | 说明 |
|---|---|---|
| 触发 | 点击历史按钮或 nav "对话" | 用户操作 |
| 打开起始 | `translateX(-100%)` | 完全在左侧外 |
| 打开结束 | `translateX(0)` | 完全显示 |
| 打开持续时间 | `300ms` | 标准抽屉速度 |
| 打开缓动 | `var(--easing-enter)` | 柔和进入 |
| 关闭起始 | `translateX(0)` | 完全显示 |
| 关闭结束 | `translateX(-100%)` | 完全隐藏 |
| 关闭持续时间 | `250ms` | 退出比进入快（响应感） |
| 关闭缓动 | `var(--easing-exit)` | 加速离开 |
| 遮罩 | 同步 `opacity: 0 → 1` / `1 → 0` | `200ms` |
| 列表项 stagger | 抽屉内列表项 `opacity: 0 → 1` + `translateX(-8px → 0)` | 每项 `30ms` 间隔，最多 300ms |

#### 模态弹出/关闭

| 属性 | 值 | 说明 |
|---|---|---|
| 触发 | 安全弹出、冷启动、确认操作 | 用户操作或系统状态 |
| 遮罩起始 | `opacity: 0` | 透明 |
| 遮罩结束 | `opacity: 1` | 45% 黑 |
| 遮罩持续 | `150ms` | 快速显现 |
| 内容起始 | `opacity: 0` + `scale: 0.95` + `translateY(8px)` | 略小、略低、透明 |
| 内容结束 | `opacity: 1` + `scale: 1` + `translateY(0)` | 正常 |
| 内容持续 | `200ms` | 比遮罩稍慢，形成层次 |
| 缓动 | `var(--easing-enter)` | 柔和 |
| 关闭 | 内容先退出（`150ms`），遮罩后退出（`100ms`） | 退出比进入快 |
| 关闭触发 | ESC 键、点击遮罩、点击关闭按钮 | 多种方式 |

#### 按钮点击反馈

| 属性 | 值 | 说明 |
|---|---|---|
| 触发 | 鼠标按下 / 触摸按下 | 用户交互 |
| 效果 | `scale: 0.97` + `opacity: 0.9` | 微压效果 |
| 持续时间 | `100ms` | 快速反馈 |
| 缓动 | `var(--easing-default)` | 标准 |
| 释放 | 恢复 `scale: 1` + `opacity: 1` | `100ms` |
| 主按钮额外 | 背景色 → `var(--primary-active)` | 深色压下 |
| 禁用按钮 | 无反馈 | 明确不可点 |

#### 引用角标点击 → 原文高亮

| 属性 | 值 | 说明 |
|---|---|---|
| 触发 | 点击 `[1]` 等角标 | 用户操作 |
| 角标反馈 | 角标 `scale: 1 → 1.08 → 1`（克制强调） | `180ms var(--easing-emphasis)` |
| 原文滚动 | 平滑滚动到原文位置 | `scroll-behavior: smooth` |
| 原文高亮 | 背景 → `var(--secondary-subtle)` `#FEF9C3`，持续 3s | `300ms` 淡入 |
| 高亮消退 | 背景 → 透明 | `500ms`，3s 后自动触发 |
| 未找到原文 | 角标轻微左右提示 `translateX(±2px)` 2 次 + 显示 "原文未找到，请检查资料是否仍在本地" tooltip | `240ms var(--easing-emphasis)` |

#### 状态条颜色切换（在线 → 降级 → 离线）

| 属性 | 值 | 说明 |
|---|---|---|
| 触发 | `health-probe` 状态变化 | 后端推送 |
| 在线→降级 | 黄条从顶部滑入 `translateY(-100% → 0)` | `300ms var(--easing-enter)` |
| 降级→离线 | 黄条退出 + 红条进入（交叉过渡） | 各 `200ms`，黄条先退 |
| 离线→在线 | 红条退出 `translateY(0 → -100%)` | `200ms var(--easing-exit)` |
| 状态圆点 | 颜色过渡 `200ms`（无位移） | 提示当前状态 |
| 降级文字 | 显示用户可理解的备用方式提示（如"已换用备用方式为您查找"） | 文字即时切换，无动画 |

#### 上传进度条填充

| 属性 | 值 | 说明 |
|---|---|---|
| 触发 | 后端推送进度更新 | SSE / WebSocket |
| 动画 | 宽度从当前值到新值 | `width: N% → M%` |
| 持续时间 | `300ms` | 平滑但不滞后 |
| 缓动 | `var(--easing-enter)` | 减速，给人"逐渐完成"感 |
| 完成 | 填充色闪变为 `var(--success)` 绿色，持续 500ms | 然后恢复或保持 |
| 错误 | 填充色闪变为 `var(--error)` 红色 + 抖动 | `300ms` |
| 不确定 | 滑块 `translateX(-100% → 100%)` 循环 | `1.5s linear infinite` |

#### 骨架屏 shimmer

| 属性 | 值 | 说明 |
|---|---|---|
| 触发 | 内容加载中（> 300ms） | 加载状态 |
| 骨架背景 | `var(--background-tertiary)` `#EBE3D2` | 浅灰占位 |
| shimmer 渐变 | `linear-gradient(90deg, transparent, rgba(255,255,255,0.5), transparent)` | 白色反光 |
| 动画 | 渐变从左到右循环 | `translateX(-100% → 100%)` |
| 持续时间 | `1.5s` | 循环 |
| 缓动 | `linear` | 线性循环 |
| 停止条件 | 内容加载完成后 | 骨架 `opacity: 1 → 0` + `200ms` 后移除 DOM |
| 使用场景 | 聊天加载（3 行骨架）、文档列表加载（卡片骨架）、设置项加载 | 不同骨架形状 |

### 12.4 prefers-reduced-motion 降级

```css
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
    scroll-behavior: auto !important;
  }
  
  /* 例外：进度条需要视觉变化 */
  .progress-bar {
    transition-duration: 0ms !important;
  }
  
  /* 骨架屏直接隐藏，显示静态占位 */
  .skeleton {
    animation: none !important;
    background: var(--background-tertiary) !important;
  }
}
```

**规则**：
- 所有动画必须支持 `prefers-reduced-motion: reduce`
- 减少动画时，所有过渡时间变为 `0.01ms`（实质即时）
- 骨架屏停止 shimmer，显示静态灰色块
- 模态/抽屉直接出现，无滑入/缩放
- 进度条仍然更新，但无平滑过渡（直接跳变）
- 消息直接出现，无滑入效果

---

## 13. 无障碍规范

### 13.1 对比度

| 元素 | 前景色 | 背景色 | 对比度 | 等级 | 状态 |
|---|---|---|---|---|---|
| 正文 | `#111827` | `#F5F0E8` | 15.6:1 | AAA | ✓ |
| 次文字 | `#595E66` | `#F5F0E8` | 5.8:1 | AA | ✓ |
| 主按钮文字 | `#FFFFFF` | `#1F2937` | 14.7:1 | AAA | ✓ |
| 占位符 | `#9CA3AF` | `#F5F0E8` | 2.2:1 | — | ⚠ 仅用于非关键提示;≤14px 关键提示位置请改用 `#595E66` 以增强对比度到 5.8:1 |
| 错误文字 | `#B91C1C` | `#F5F0E8` | 5.7:1 | AA | ✓ |
| 错误按钮 | `#FFFFFF` | `#B91C1C` | 6.5:1 | AA | ✓ |
| 成功文字 | `#166534` | `#F5F0E8` | 6.3:1 | AA | ✓ |
| 警告条文字 | `#FFFFFF` | `#D97706` | 3.2:1 | AA (大文字) | ✓ |
| 离线条文字 | `#FFFFFF` | `#B91C1C` | 6.5:1 | AA | ✓ |
| 暖黄上的文字 | `#1F2937` | `#F4D35E` | 10.0:1 | AAA | ✓ |
| 链接（蓝） | `#2563EB` | `#F5F0E8` | 4.6:1 | AA | ✓ |

**说明**:本表用 Python WCAG 2 严格公式（相对亮度 sRGB 反伽马）重算。原 v1.3 表中部分数字（如成功 4.6:1、次文字 5.7:1）与实测有偏差（实测 3.30:1 / 4.83:1），**v1.4 起 11 项数字以本表为准**。**所有正文级/按钮级/链接级/语义级文字均过 AA**（占位符除外,符合 §11.1 备注）。

**所有正常文字（< 18px 或 < 14px bold）必须 ≥ 4.5:1（AA）**。大文字（≥ 18px 或 ≥ 14px bold）必须 ≥ 3:1（AA）。

**v1.4 起**:占位符建议用 (在  上 5.8:1)而非 ,仅当无障碍非关键场景可用 。

### 13.2 焦点环（Focus Ring）

- **所有可交互元素**必须有可见焦点环
- 焦点环样式：`outline: 2px solid var(--primary)` + `outline-offset: 2px`
- 焦点环颜色：使用主色 `#1F2937`，在白色背景上清晰
- 焦点环不依赖浏览器默认样式（`outline: none` 后必须自定义）
- 焦点环在暗色模式下需要调整（使用 `#60A5FA` 等亮色）

```css
:focus-visible {
  outline: 2px solid var(--primary);
  outline-offset: 2px;
}

/* 暗色模式 */
[data-theme="dark"] :focus-visible {
  outline-color: #60A5FA;
}
```

### 13.3 键盘导航

| 组件 | Tab 顺序 | 快捷键 | 说明 |
|---|---|---|---|
| 顶部 nav | 品牌 → 导航项 → 状态 → 关闭 | — | 从左到右 |
| 抽屉列表 | 列表项从上到下 | `↑` `↓` 导航 | 支持键盘上下 |
| 聊天输入 | Tab 聚焦后 `Enter` 发送 | `Ctrl+Enter` 换行 | 标准行为 |
| 消息气泡 | 不可 Tab 聚焦（仅阅读） | — | 静态内容 |
| 引用角标 | 按消息内 Tab 顺序 | `Enter` 跳原文 | 可聚焦 |
| 模态框 | 聚焦陷阱（Focus Trap） | `Esc` 关闭 | Tab 不跳出模态 |
| 按钮组 | 从左到右 | `Enter` / `Space` 激活 | 标准 |

- **Tab 顺序必须匹配视觉顺序**
- **模态框打开时，焦点必须限制在模态内**（Focus Trap）
- **模态关闭后，焦点返回到触发元素**
- **所有按钮必须可通过 `Enter` 或 `Space` 激活**

### 13.4 屏幕阅读器（ARIA）

| 元素 | ARIA 属性 | 说明 |
|---|---|---|
| 顶部 nav | `<nav aria-label="主导航">` | 导航地标 |
| 抽屉 | `<aside aria-label="会话历史">` | 补充地标 |
| 主内容 | `<main aria-label="主内容">` | 主地标 |
| 聊天消息流 | `role="log" aria-live="polite"` | 新消息自动朗读 |
| 用户消息 | `aria-label="您的消息"` | 标识发件人 |
| AI 消息 | `aria-label="KB-AI 回答"` | 标识发件人 |
| 引用角标 | `aria-label="查看原文 [1] 经营手册.pdf · §3.2"` | 完整描述 |
| 状态条 | `role="alert" aria-live="assertive"` | 状态变化立即朗读 |
| 加载骨架 | `aria-label="正在加载内容"` + `aria-busy="true"` | 加载状态 |
| 进度条 | `role="progressbar" aria-valuenow aria-valuemin aria-valuemax` | 进度语义 |
| 空状态 | `aria-label="暂无内容"` | 空状态提示 |
| 按钮（图标-only） | `aria-label="发送消息"` / `aria-label="关闭"` | 必须描述 |
| 图标按钮 | 绝不 icon-only 无 label |  Lucide 图标无文本含义 |

### 13.5 动态字体支持

- 支持浏览器字体缩放(Chrome/Edge `Ctrl + +` / DPI 缩放)与 Windows 高对比度模式
- 使用 `rem` 单位而非 `px`，响应根字体大小变化
- 测试 `font-size: 200%` 时，布局不崩溃（文字换行、按钮不重叠）
- 避免 `height` 固定值，使用 `min-height` + 自适应内容
- 中文在大字号时，行高保持 1.6 不压缩

### 13.6 暗黑模式 WCAG 对比度验证（v1 不实施，Token 预留参考）

> ⚠️ **范围声明**：本表为暗黑模式 Token 预留参考的对比度验证，v1 不实施（见 §1.5）。若未来启用暗黑模式，需先修复下方 2 项不达标项。

| 元素 | 前景色 | 背景色 | 对比度 | 等级 | 状态 |
|---|---|---|---|---|---|
| 正文 | `#F9FAFB` | `#111827` | 17.0:1 | AAA | ✓ |
| 次文字 | `#9CA3AF` | `#111827` | 7.0:1 | AAA | ✓ |
| muted 文字 | `#6B7280` | `#111827` | 3.7:1 | — | ⚠ 仅大文字 AA（正常文字不达标）|
| 主按钮文字 | `#111827` | `#F9FAFB` | 17.0:1 | AAA | ✓ |
| 占位符（输入框）| `#6B7280` | `#1F2937` | 3.0:1 | — | ✗ 不达标 |
| 错误文字 | `#EF4444` | `#111827` | 4.7:1 | AA | ✓ |
| 成功文字 | `#22C55E` | `#111827` | 7.8:1 | AAA | ✓ |
| 警告文字 | `#FBBF24` | `#111827` | 10.6:1 | AAA | ✓ |
| info 文字 | `#60A5FA` | `#111827` | 7.0:1 | AAA | ✓ |
| 离线文字 | `#9CA3AF` | `#111827` | 7.0:1 | AAA | ✓ |
| 暖黄上的文字 | `#111827` | `#F4D35E` | 12.1:1 | AAA | ✓ |

**不达标项修复建议**（未来启用暗黑模式时处理）：

1. **muted 文字 `#6B7280` on `#111827`（3.7:1）**：提升至 `#9CA3AF`（→ 7.0:1 AAA），但会与 secondary 重合；或新增 `--color-text-muted-dark` 中间灰（如 `#7280A0`）
2. **占位符 `#6B7280` on `#1F2937`（3.0:1）**：提升至 `#9CA3AF`（→ 5.8:1 AA），与亮色模式策略一致（亮色模式占位符 `#9CA3AF` on `#FFFFFF` 为 2.7:1 仅用于非关键提示）

---

## 14. 反模式清单

### 14.1 基于项目简报 §6 的 7 类坑

| # | 类别 | 禁止内容 | 原因 | 正确做法 |
|---|---|---|---|---|
| 1 | **数据治理** | 加密上传 UI、云备份按钮、自动同步开关、"数据安全"宣传页 | 用户已决策接受无加密/无备份 | 首次启动横幅提醒 + 关闭时再次提醒 |
| 2 | **账号体系** | 登录页、注册页、找回密码、账户设置、角色管理、SSO 入口 | 单用户本地，无账号 | 直接进入主界面，无登录流程 |
| 3 | **模型选择** | 模型切换下拉、当前模型名显示（除降级黄条外）、模型参数调节 | 后端静默调，用户不选 | 不显示，一切由后端决定 |
| 4 | **可用性假设** | 不做离线状态条、不做离线输入降级、假设永远在线 | 必须有离线降级 UX | §A 离线状态条 + 输入框降级提示 |
| 5 | **性能假设** | 不做启动进度、不做骨架屏、假设秒开 | U 盘+Win 启动 60-90s | §D 6 段冷启动进度 + 全局骨架屏 |
| 6 | **响应式** | 移动端底部导航、折叠汉堡菜单、触摸手势优化、PWA 适配 | 桌面为主，1280-1920px | 桌面优先，仅基础响应式 |
| 7 | **深色模式** | 首版实现暗色模式（CSS 变量已预留，但 v1 不实现） | 商务基调，无需求 | Token 用 CSS 变量，方便后续扩展 |

### 14.2 隐性"不要做"清单（11 项）

| # | 禁止项 | 原因 | 替代方案 |
|---|---|---|---|
| 1 | 紫白渐变背景 | 反"通用 AI 美学"，与商务黑灰冲突 | 纯白或浅灰纯色背景 |
| 2 | 蓝紫渐变 | 同上，与 KB-AI 品牌无关 | 深灰 + 暖黄双色方案 |
| 3 | Glassmorphism（玻璃拟态） | 与"经典商务"冲突，降低可读性 | 实色卡片，无模糊 |
| 4 | 大色块/大插画装饰 | 极简原则，非技术用户不需要视觉噪音 | 留白 + 清晰文字层级 |
| 5 | 使用 emoji 作为结构性图标 | 不可控、无设计令牌、平台差异 | Lucide SVG 图标 |
| 6 | "Notion 风格"块编辑器 | 不适用 RAG 场景 | 纯文本聊天流 |
| 7 | 大屏 Dashboard / Analytics | 单用户无 KPI 需求 | Chat-first 界面 |
| 8 | 工作流编排 / 拖拽流程 | 单用户线性使用 | 简单上传 → 聊天流程 |
| 9 | 水印 / 版权页 | 单用户本地工具无意义 | 无 |
| 10 | 分享链接功能 | 本地无外网 | 无 |
| 11 | 导入云盘（OneDrive/Dropbox/坚果云） | 本地工具，无云连接 | 仅本地文件上传 |

### 14.3 通用 UX 反模式（基于 99 条指南）

| # | 反模式 | 正确做法 | 来源指南 |
|---|---|---|---|
| 1 | 移除焦点环 | 自定义可见焦点环 `2px solid + 2px offset` | §1 `focus-states` |
| 2 | 仅依赖 hover 的交互 | 所有操作可通过点击/键盘完成 | §2 `hover-vs-tap` |
| 3 | 即时状态切换（0ms） | 所有状态变化有过渡动画（150-300ms） | §2 `press-feedback` |
| 4 | 无加载反馈的按钮 | 异步操作禁用按钮 + 显示加载图标 | §2 `loading-buttons` |
| 5 | 占位符-only 标签 | 可见的 `label` 元素，placeholder 仅辅助 | §8 `input-labels` |
| 6 | 错误仅显示在顶部 | 错误显示在对应字段下方 | §8 `error-placement` |
| 7 | 装饰性动画 | 每个动画必须表达因果关系 | §7 `motion-meaning` |
| 8 | 动画 width/height/top/left | 仅使用 `transform` + `opacity` | §7 `transform-performance` |
| 9 | 无 reduced-motion 支持 | 提供 `prefers-reduced-motion` 降级 | §1 `reduced-motion` |
| 10 | 触摸目标 < 44px | 最小交互区域 44×44px | §2 `touch-target-size` |
| 11 | 无 escape 路由的模态 | 所有模态提供关闭/取消按钮 | §1 `escape-routes` |
| 12 | 水平滚动 | 禁止横向滚动，内容适配视口 | §5 `horizontal-scroll` |
| 13 | 灰色文字在灰色背景 | 确保文字与背景对比度 ≥ 4.5:1 | §6 `contrast-readability` |
| 14 | 组件中硬编码 hex | 使用语义颜色 Token | §6 `color-semantic` |
| 15 | 无空状态设计 | 每个列表/区域提供空状态 + 引导 | §8 `empty-states` |
| 16 | 无骨架屏的长加载 | > 300ms 加载显示骨架屏 | §3 `progressive-loading` |
| 17 | 导航层级混乱 | 顶部 nav 为主，抽屉为次，不混合 | §9 `nav-hierarchy` |
| 18 | 模态用于主导航 | 模态仅用于确认/提示，不用于流程 | §9 `modal-vs-navigation` |
| 19 | 文字 < 12px | 最小正文 16px，最小辅助 12px | §6 `text-styles-system` |
| 20 | 无顺序的 heading | h1→h2→h3 顺序，不跳级 | §1 `heading-hierarchy` |

---

## 15. 页面级覆盖建议

> **注**：以下建议供 `design-system/pages/<page>.md` 覆盖使用。MASTER.md 定义全局规则，页面文件在此基础上做特定调整。

### 15.1 聊天主页（Chat Page）—— 默认页面

**布局覆盖**：
- 主内容区完全用于聊天流，无侧边栏
- 输入区固定在底部，`sticky` 或 `fixed`
- 顶部 nav 下方可显示状态条（离线/降级时）

**组件特殊规则**：
- 消息气泡最大宽 75%（用户）/ 75%（AI），但 AI 气泡内引用角标可超出气泡边界（视觉上角标可"悬挂"）
- 连续用户消息合并显示（无头像间隔），时间戳只在最后一条显示
- AI 消息中的代码块使用 `font-mono` + 深色背景 `#1F2937`，语法高亮（可选）
- 图片消息气泡（REQ-11 多模态）：
  - 上传限制：单次最多 8 张，单张 ≤ 20 MB（来源：REQ-11 / PRD v0.7）
  - 气泡内单图：最大宽 320px，最大高 240px，保持原始比例，圆角 `radius-md` 8px
  - 气泡内多图网格（2-9 张）：CSS Grid，缩略图固定 96×96px（`object-fit: cover`），圆角 `radius-sm` 4px，`gap-1` (4px)
    - 2 张：1×2 网格
    - 3 张：1×3 网格
    - 4 张：2×2 网格
    - 5-6 张：2×3 网格
    - 7-8 张：3×3 网格（最多 8 张，第 3 行 2-3 张）
  - 图片在文字下方（同气泡），或纯图片消息（无文字）
  - 点击放大：标准模态（宽 640px md），图片居中，最大宽 100%，最大高 80vh，`object-fit: contain`，点击遮罩或 ESC 关闭
  - 加载状态：图片加载时显示骨架（`var(--background-tertiary)` 占位 + shimmer），加载完成 `opacity: 0 → 1`，`200ms`
  - 错误状态：图片加载失败显示 Lucide `ImageOff` 24px + "图片加载失败" 文字，`var(--foreground-tertiary)`
- 反问卡片（`type=clarify`）：使用 `info` 变体卡片，背景 `var(--info-subtle)`，含"跳过"按钮
- 多选题卡片（`type=multi_choice`）：选项按钮使用 `outline` 变体，选中后 `primary` 变体
- 新会话：抽屉顶部 "+ 新建会话" 按钮，点击后清空聊天流，标题自动为首个问题前 20 字

**动画特殊规则**：
- 聊天流加载时，骨架屏显示 3 条消息骨架（交替左右）
- 用户发送消息时，输入区有轻微按压反馈（`scale: 0.98 → 1`，`100ms var(--easing-emphasis)`）
- AI 流式回复时，输入区显示 "AI 正在思考..." 微提示（`text-xs`，`foreground-tertiary`）
- 超过 50 轮时，显示 50 轮记忆提示（`warning` 级别系统提示，非红色错误条）：
  - 位置：聊天流内居中（系统提示样式），非顶部状态条
  - 文字色：`var(--warning)` `#D97706`（黄色警告，非红色错误）
  - 内容："对话已超过 50 轮，AI 记忆可能开始模糊，建议新建对话" — Lucide `AlertTriangle` 16px 图标前缀
  - 背景：`var(--background-tertiary)` `#EBE3D2`，圆角 `radius-md`
  - 不自动消失：需用户点击"知道了"按钮关闭（与自动消失的 3s 系统提示不同）
  - "知道了"按钮：`ghost` 变体，`text-sm` 14px，`var(--foreground-seco

### 15.2 文档上传页（Upload Page）

**布局覆盖**：
- 居中大卡片布局，最大宽 640px
- 顶部有返回按钮（或顶部 nav 直接切换）

**组件特殊规则**：
- 拖拽区域：虚线边框 `2px dashed var(--border)`，拖拽时边框变 `var(--primary)` + 背景 `var(--primary-subtle)`
- 文件卡片：显示文件名、大小、类型图标、进度条、状态标签
- 解析失败卡片：顶部红色条 + 错误原因 + "重试" 按钮
- 批量操作：选中文件后显示顶部操作栏（移动分类、改标签、删除）
- 分类下拉：扁平一级分类，无嵌套
- 标签输入：chips 输入，输入后按 Enter 或逗号生成 chip，可删除

**动画特殊规则**：
- 文件拖入时，拖拽区域 `scale: 1.02` + 边框色变化，`200ms`
- 文件卡片入场：从顶部 `translateY(-16px)` + `opacity: 0 → 1`，`stagger 50ms`
- 进度条完成时，文件卡片右侧出现绿色对勾 `scale: 0 → 1`，`200ms var(--easing-emphasis)`
- 删除文件时，卡片 `opacity: 1 → 0` + `translateX(100px)` + `height` 收缩（使用 `max-height` 动画），`300ms`

### 15.3 资料库管理页（Library Page）

**布局覆盖**：
- 卡片网格布局，CSS Grid，`minmax(280px, 1fr)`，自适应列数
- 顶部有搜索栏 + 筛选器（分类下拉 + 标签 chips）+ 排序下拉
- 无文档时显示空状态：大图标 `Library` (48px) + "暂无文档" + "上传第一个文档" 按钮

**组件特殊规则**：
- 文档卡片：左侧文件类型图标（24px）+ 文件名（截断，最大 1 行）+ 大小/日期 + 分类标签 + 操作菜单
- 批量操作：顶部复选框全选，选中后操作栏出现（fixed 顶部或相对）
- 分页/无限滚动：文档量可能大，用虚拟滚动（> 50 项）
- 搜索即时过滤：输入 300ms debounce 后过滤，无结果显示空状态

**动画特殊规则**：
- 筛选切换时，卡片重新排列使用 `layout` 动画（若使用 Framer Motion）或 `opacity` 过渡
- 卡片 hover 时微升 `translateY(-2px)` + `shadow-md`，`200ms`
- 删除卡片时与上传页相同动画

### 15.4 设置页（Settings Page）

**布局覆盖**：
- 居中单列布局，最大宽 640px
- 分组显示，每组之间有 `32px` 间距 + 分组标题

**组件特殊规则**：
- 设置项：左侧标签 + 右侧控件（开关/下拉/输入），项间距 `24px`
- 开关项：标签 + 说明文字 + 开关，说明文字 `text-sm` `foreground-secondary`
- 只读容量显示：使用进度条展示 5 级容量，颜色随级别变化（绿→黄→橙→红→深红）
- 版本信息：使用 `font-mono` 显示版本号
- 无备份提醒：首次进入设置页时，顶部显示 `warning` 提示条（可关闭）
- 安全弹出按钮：底部大按钮，`destructive` 变体，点击触发 §C 模态

**动画特殊规则**：
- 开关切换：使用全局开关动画（`200ms var(--easing-emphasis)`）
- 设置保存成功：按钮右侧显示绿色 `CheckCircle2` 图标，`opacity: 0 → 1`，`200ms`，3s 后消失
- 设置保存失败：按钮右侧显示红色 `XCircle` 图标 + 错误 tooltip

### 15.5 特殊页面/状态覆盖

#### 冷启动进度页（§D）

**模态容器**：

| 属性 | 值 | 说明 |
|---|---|---|
| 宽度 | 480px (sm) | 与 §10.4 标准模态一致 |
| 最大高 | 80vh | 超出滚动 |
| 模态背景 | `var(--background)` `#FFFFFF` | 纯白 |
| 圆角 | `radius-lg` 16px | 最大圆角 |
| 阴影 | `shadow-xl` | 最强阴影 |
| 内边距 | `p-8` (32px) | 大量呼吸空间 |
| 遮罩 | `var(--background-overlay)` `rgba(0,0,0,0.45)` | 45% 黑 |
| 出现动画 | `opacity: 0 → 1` + `scale: 0.95 → 1`，`300ms var(--easing-enter)` | |
| 消失动画 | `opacity: 1 → 0` + `scale: 1 → 0.95`，`200ms var(--easing-exit)` | |

**内容结构**：

- 标题："AI Assistant 启动中" — `font-heading` `text-xl` 24px，`font-weight: 600`，`var(--foreground)` `#111827`，居中
- 顶部图标：Lucide `Zap` 40px，`var(--secondary)` `#F4D35E`，闪烁动画（opacity 脉冲，`1.5s ease-in-out infinite`）
- 进度列表：6 项，每项含：
  - 序号：`font-mono` 14px，`var(--foreground-secondary)` `#595E
  - 步骤名：`text-sm` 14px 400，`#374151`，例 "U 盘根目录检测"
  - 状态图标：等待 `Circle` 16px `#D1D5DB` / 进行中 `Loader2` 16px `var(--primary)` 旋转 / 成功 `CheckCircle2` 16px `var(--success)` / 失败 `XCircle` 16px `var(--error)`
  - 耗时：`font-mono` `text-xs` 12px `var(--foreground-tertiary)` `#9CA3AF`，右对齐
  - 项高 32px，项间距 `gap-3` (12px)
- 总进度条：高 6px，背景 `var(--background-tertiary)` `#DDD3C0`，圆角 `9
- 百分比文字："3/6" — `font-mono` `text-sm` 14px `var(--foreground

**状态分支**：

- 任一步 > 60s：该步骤文字变 `var(--warning)` `#D97706`，下方显示 "这一步花的时间有点久，正在继续重试"（`text-xs` 12px `var(--warning)`）
- 总超时 > 120s：整体进度条填充变 `var(--error)` `#B91C1C`，显示 "启动超时，请重新启
- 重试按钮：`primary` 变体，`sm` 尺寸（高 36px，`px-4`），圆角 `radius-sm` 4px
- 完成：标题变 "启动完成！" + 进入按钮，进度条填充变 `var(--success)` `#166534`
- 动画：每步骤完成时，✓ 图标 `scale: 0 → 1` + `opacity: 0 → 1`，`200ms var(--easing-emphasis)`

#### 安全弹出模态（§C）

**模态容器**：

| 属性 | 值 | 说明 |
|---|---|---|
| 宽度 | 480px (sm) | 与 §10.4 标准模态一致(v1.0 时代曾定为 440px,本版统一为标准 480px) |
| 圆角 | `radius-lg` 16px | 最大圆角 |
| 内边距 | `p-6` (24px) | 标准 |
| 阴影 | `shadow-xl` | 最强阴影 |
| 遮罩 | `var(--background-overlay)` `rgba(0,0,0,0.45)` | 45% 黑 |
| 动画 | 标准模态动画(见 §10.4) | |

**内容结构**：

- 标题："确定要关闭 AI Assistant 吗？" — `text-xl` 24px，`font-weight: 600`，`var(--foreground)` `#111827`
- 正文列表（`text-sm` 14px）：
  - **关闭后**（3 项，`var(--foreground-secondary)` `#374151`）：
    - "Dify 容器优雅停止（约 10 秒）"
    - "您可以安全弹出 U 盘"
    - "下次使用需重新双击 Windows-Start.bat"
  - **重要**（2 项，带 Lucide 图标，图标与文字 `gap-2` 8px）：
    - "您当前会话已自动保存" — `var(--success)` `#166534`，Lucide `Chec
    - "数据无云备份，仅在本地 U 盘" — `var(--warning)` `#D97706`，Lucide `AlertTriangle` 16px
- 列表项间距：`gap-2` (8px)
- 复选框："不再提示（本次会话）" — `text-xs` 12px `var(--foreground-second
- **按钮组**（底部，`flex justify-end`，`gap-3` 12px，主按钮在右）：
  - 取消：`outline` 变体，`default` 尺寸（高 40px，`px-5`），圆角 `radius-sm` 4px
  - 确认关闭：`destructive` 变体，`default` 尺寸（高 40px，`px-5`），圆角 `radius-sm` 4px
- **按钮交互**：hover 取消 → 背景 `var(--primary-subtle)`；hover 确认 → 背景 `#B91C1C`（`var(--error)` 加深）；active 确认 → `scale: 0.98`（`100ms`）

**特殊状态**：

- 意外拔 U 盘：检测到 U 盘断开时，自动显示错误提示模态："U 盘意外拔出，数据可能损坏" — 使用 `error` 变体样式
- 关闭确认后：整个页面淡出（`opacity: 1 → 0`，`500ms`），然后显示居中文字 "已关闭，请安全弹出

#### 空状态（Empty States）

| 场景 | 图标 | 标题 | 说明 | 操作 |
|---|---|---|---|---|
| 无会话 | `MessageSquare` (48px) | "还没有对话" | "开始您的第一个问题，AI 会引用您的资料回答" | "开始对话" 按钮 |
| 无文档 | `Library` (48px) | "还没有文档" | "上传经营文档，让 AI 学习您的知识" | "上传文档" 按钮 |
| 搜索无结果 | `Search` (48px) | "未找到相关文档" | "尝试其他关键词，或上传更多文档" | "清除筛选" 按钮 |
| 离线无内容 | `WifiOff` (48px) | "离线模式" | "您可以查看历史记录，但无法获取新回答" | "检查网络" 按钮（重试） |
| 加载失败 | `AlertTriangle` (48px) | "加载失败" | "请检查网络或刷新页面" | "重试" 按钮 |

- 空状态图标颜色：`var(--foreground-tertiary)` `#9CA3AF`
- 标题：`text-xl` 24px，`font-weight: 600`
- 说明：`text-base` 16px，`foreground-secondary`
- 操作按钮：`primary` 或 `outline` 变体
- 动画：空状态整体 `opacity: 0 → 1` + `translateY(8px → 0)`，`300ms`

---

## 附录 A：设计令牌速查表

### 色彩 Token

```
--primary: #1F2937
--primary-foreground: #FFFFFF
--secondary: #F4D35E
--secondary-foreground: #1F2937
--background: #FFFFFF
--background-secondary: #F2EBDE
--foreground: #111827
--foreground-secondary: #595E66
--border: #DDD3C0
--error: #B91C1C
--success: #166534
--warning: #D97706
--info: #2563EB
```

### 排版 Token

```
--font-heading: "Smiley Sans", "PingFang SC", "Microsoft YaHei", sans-serif
--font-body: "Alibaba PuHuiTi 3.0", "PingFang SC", "Microsoft YaHei", sans-serif
--font-mono: "JetBrains Mono", "Fira Code", "Consolas", monospace

字号: 12 / 14 / 16 / 18 / 24 / 32 / 48 px
行高: 1.5 (小字) / 1.6 (正文)
字重: 400 / 500 / 600 / 700
字间距: 0.01em (小字) / 0.02em (正文)
```

### 间距 Token

```
space: 4 / 8 / 12 / 16 / 24 / 32 / 48 px
```

### 圆角 Token

```
radius: 0 / 4 / 8 / 16 px
```

### 阴影 Token

```
shadow-sm: 0 1px 2px 0 rgba(0,0,0,0.05)
shadow-md: 0 1px 3px 0 rgba(0,0,0,0.08), 0 1px 2px 0 rgba(0,0,0,0.04)
shadow-lg: 0 4px 6px -1px rgba(0,0,0,0.08), 0 2px 4px -2px rgba(0,0,0,0.04)
shadow-xl: 0 10px 15px -3px rgba(0,0,0,0.08), 0 4px 6px -4px rgba(0,0,0,0.04)
```

### 动画 Token

```
duration: 100 / 150 / 200 / 300 / 400 ms
easing: default / enter / exit / emphasis / linear
properties: transform, opacity only
stagger: 30ms per item
```

---

## 附录 B：与 UI-UX-Pro-Max 指南对照表

| KB-AI 设计决策 | 对应的 UX 指南 | 优先级 |
|---|---|---|
| 对比度 ≥ 4.5:1 | §1 `color-contrast` | P1 CRITICAL |
| 自定义焦点环 | §1 `focus-states` | P1 CRITICAL |
| 触摸目标 ≥ 40px（桌面扩展至 44px） | §2 `touch-target-size` | P1 CRITICAL |
| 按钮加载状态 | §2 `loading-buttons` | P1 CRITICAL |
| 骨架屏替代长加载 | §3 `progressive-loading` | P2 HIGH |
| 统一 Lucide 图标 | §4 `no-emoji-icons` | P2 HIGH |
| 语义颜色 Token | §6 `color-semantic` | P3 MEDIUM |
| 动画 150-300ms | §7 `duration-timing` | P3 MEDIUM |
| transform/opacity only | §7 `transform-performance` | P3 MEDIUM |
| prefers-reduced-motion | §1 `reduced-motion` | P1 CRITICAL |
| 可见 input label | §8 `input-labels` | P3 MEDIUM |
| 错误就近显示 | §8 `error-placement` | P3 MEDIUM |
| 空状态设计 | §8 `empty-states` | P3 MEDIUM |
| 导航层级清晰 | §9 `nav-hierarchy` | P2 HIGH |
| 模态不用于导航 | §9 `modal-vs-navigation` | P2 HIGH |
| 渐进式披露 | §8 `progressive-disclosure` | P3 MEDIUM |

---

> **文件结束**。本文件为 KB-AI 设计系统的全局真相源。所有页面级覆盖请写入 `design-system/pages/<page>.md`，并遵循"页面规则覆盖全局规则"的层级原则。

---

## 附录 C：修订追踪记录
| 2026-07-07 | AI 文档修复代理 | P0 自违规修复 | 占位符对比度提示补充：≤14px 关键提示位置改用 `#595E66` 以增强对比度到 5.8:1（注:v1.4 起 #6B7280 已被 #595E66 取代） | design-review.md §3.4 |
| 修订日期 | 修订人 | 变更类型 | 变更内容 | 关联评审 |
|---|---|---|---|---|
| 2026-07-07 | AI 文档修复代理 | P0 自违规修复 | ASCII 草图中 emoji 结构性图标替换为文字标注（`[BookOpen]`、`[●在线]`、`[Power]`、`[离线]`、`[降级]`） | design-review.md §3.1 |
| 2026-07-07 | AI 文档修复代理 | P0 自违规修复 | 占位符对比度提示补充：≤14px 关键提示位
| 2026-07-07 | AI 文档修复代理 | 元数据增强 | 文件头部新增 Status、最后评审、维护者、冲突裁决字段；追加 "冲突裁决：以本文件为准" | design-review.md §6.3 |
| 2026-07-07 | AI 文档修复代理 | 元数据增强 | 文件头部新增 Status、最后评审、维护者、冲突裁决字段 | design-review.md §6.3 |
| 2026-07-08 | AI 文档修复代理 | P0 账实核对 | §10.2 ASCII 草图残留 emoji 清理：`📎` → `[Paperclip]`，`⏩` → `[Send]` | 评审 §四 P0 |
| 2026-07-08 | AI 文档修复代理 | P2 完整性深化 | §15.5 §D 冷启动进度页补完整尺寸表（容器/内容/状态分支，从 design §6.8 提升） | 评审 §四 P2 #9 |
| 2026-07-08 | AI 文档修复代理 | P2 完整性深化 + 冲突修复 | §15.5 §C 安全弹出模态补完整尺寸表（容器/内容/按钮组/特殊状态）；§C 宽度 480px 统一（design §6.9 原 440px 不在标准档） | 评审 §四 P2 #8 |
| 2026-07-08 | AI 文档修复代理 | P2 完整性深化 | §15.1 补多模态图片消息气泡规格（单图/多图网格/点击放大/加载/错误状态，REQ-11 MAX 8 张 ≤ 20MB） | 评审 §四 P2 #10 |
| 2026-07-08 | AI 文档修复代理 | P2 冲突修复 | §15.1 50 轮记忆提示由"红色提示条"改为"黄色 warning 系统提示"（与 design §8.1 一致），补完整 UI 规格 | 评审 §四 P2 #11 |
| 2026-07-08 | Kimi Code + Impeccable | 文档收敛 | 原 `design/design.md` 的视觉叙事、品牌记忆点、文案语气表合并入 §2；`MASTER.md` 升级为唯一设计真相源；移除默认 bounce/spring easing，改为克制 emphasis easing | impeccable critique 2026-07-07 |
| 2026-07-08 | Kimi Code + Impeccable | 专业感体验准则 | 新增 §3 专业感体验准则，明确启动、回答、引用、错误、关闭与安全弹出的专业感验收要求；目录和 `AGENTS.md` 章节引用同步调整 | 用户要求"执行专业感设计方案" |
| 2026-07-08 | AI 文档修复代理 | P2 遗漏修复 | §13.6 补暗黑模式 WCAG 对比度验证表（11 项，2 项不达标已标注修复建议，从 design §9.5 迁移重建）；design.md 跳转壳移除虚假 .bak 引用，改为 git history 追溯说明 | 评审 §四 P2 #12 |

| 2026-07-10 | maintainer + AI 代理 | 全面修复（v1.3） | NEW-1 章节编号重排（11 主章 + 56 子节 + 8 内部引用同步）、NEW-2 `--offline` 死代码 token 删除、NEW-3 §13.5 动态字体支持从 iOS/Android 改 Windows 桌面浏览器、NEW-4 §15.5 §C 安全弹出模态删 `design §6.9` 废弃引用、NEW-5 引用角标格式统一（§3.2 风格，中点+§符号）、NEW-6 §10.9 AI 消息气泡属性表补时间戳行、NEW-7 §7.1 圆角阶加聊天输入框 `radius-lg` 例外、NEW-8 §10.5 抽屉补点击遮罩关闭行、NEW-9 §5.1 字体后备栈优化（去重复别名，Win 字体前置）、NEW-10 §15.1 多模态图片限制加 REQ-11 / PRD v0.7 来源、维护者更新为 maintainer + AI 代理辅助修订、版本升级 v1.2 → v1.3 | KB-AI 设计系统评审报告 2026-07-10 |
| 2026-07-10 | maintainer + AI 代理 | 调色（v1.4 · C+） | 商务为主、餐饮为辅调性下,用户实测预览后认为 #F9FAFB 系列太冷,选 C+ 调色（冷顶 nav + 暖正文 + L=0.88 不刺眼 + 全部过 AA）：`--background #FFFFFF → #F5F0E8` 米白主背景（L=0.88 8h 不刺眼）、`--background-secondary #F9FAFB → #F2EBDE` 深米次背景、`--background-tertiary #F3F4F6 → #EBE3D2` 米灰输入框、`--border #E5E7EB → #DDD3C0` + `--border-subtle #F3F4F6 → #ECE3D0` 暖边框、`--foreground-secondary #6B7280 → #595E66` 次文字加深过 AA、`--error #DC2626 → #B91C1C` + `--success #16A34A → #166534` 语义色加深过 AA、§11.1 对比度表 11 行用 Python WCAG 2 严格公式重算（原 v1.3 表部分数字不准）、§11.1 规则段加占位符建议用 `#595E66` 替代 `#9CA3AF` | 用户预览反馈 + AI 调色 |
> **当前状态**：v1.4 · 单一真相源收敛完成,新增专业感体验准则（§3），并完成 2026-07-10 全面修复（v1.3：章节/死代码/设备/废弃引用/格式/时间戳/例外/抽屉/字体/来源 10 项）+ 同日 v1.4 调色（C+：冷顶 nav + 暖正文 L=0.88 + 8 变量 + 11 项对比度全重算）。`design/design.md` 已废弃为跳转说明页,原文件已覆盖,历史追溯请用 git history。剩余 P3：暗黑模式 2 项不达标色值修复（v1 不实施,未来启用时处理）。
