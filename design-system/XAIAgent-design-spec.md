# XAIAgent 暗黑赛博风格 — 设计规范文档

> 基于站酷作品《XAIAgent 官网/品牌形象设计》拆解，可直接作为 AI 生成代码的 Prompt 附件使用。

---

## 1. 设计概述

| 项目 | 规范 |
|------|------|
| **风格名称** | Dark Cyber-Industrial / 暗黑机能科技 |
| **情绪关键词** | 硬核、神秘、未来、高端、去中心化 |
| **适用场景** | AI Agent 官网、Web3 项目、数据工具、科技产品落地页 |
| **设计哲学** | 极简信息密度 + 非对称留白 + 单屏叙事 |
| **技术栈建议** | React + Tailwind CSS + shadcn/ui + Framer Motion + Three.js/Spline |

---

## 2. 配色系统

### 2.1 核心色板

```
Background Primary:   #000000  (纯黑，主背景)
Background Secondary: #0A0A0A  (近黑，卡片/区块背景)
Accent:               #FF540E  (熔岩橙，强调色、CTA、高亮)
Text Primary:         #FFFFFF  (纯白，标题、正文)
Text Secondary:       #A1A1AA  (灰白，辅助文字、描述)
Border:               rgba(255, 255, 255, 0.08)  (极淡白边，玻璃态边框)
Glass Background:     rgba(255, 255, 255, 0.03)  (玻璃态卡片底色)
```

### 2.2 使用规则

| 场景 | 颜色 | 说明 |
|------|------|------|
| 页面背景 | `#000000` | 全局纯黑，不可使用渐变背景 |
| 大标题 | `#FFFFFF` | 纯白，高对比 |
| 正文/描述 | `#A1A1AA` | 降低阅读疲劳 |
| 主按钮 | `#FF540E` | 橙色填充，白色文字 |
| 次级按钮 | `transparent` + `border: 1px solid #FF540E` | 橙色描边，橙色文字 |
| 标签/徽章 | `#FF540E` | 小面积使用，点睛 |
| 图表高亮 | `#FF540E` | 数据可视化中的主色 |
| 分割线/边框 | `rgba(255,255,255,0.08)` | 极淡，不抢视觉 |
| Hover 状态 | `#FF540E` 亮度提升 10% | `#FF6B2C` |
| 禁用状态 | `rgba(255,255,255,0.2)` | 极低透明度 |

---

## 3. 字体系统

### 3.1 字体选择

| 用途 | 字体 | 备选 |
|------|------|------|
| **Display / 大标题** | 自定义像素/机能字体 | "Press Start 2P", "Space Mono", "JetBrains Mono" |
| **Heading / 副标题** | "Inter", "Circular Std" | "SF Pro Display", "Helvetica Neue" |
| **Body / 正文** | "Inter", "Circular Std" | "Noto Sans SC", "PingFang SC" |
| **Code / 数据** | "JetBrains Mono", "Fira Code" | "Consolas", "Monaco" |

### 3.2 字号层级（Desktop / 1440px+）

```
H1 (Hero):     96px - 150px  /  font-weight: 700  /  line-height: 1.0  /  letter-spacing: -0.02em
H2 (Section):  56px - 72px   /  font-weight: 600  /  line-height: 1.1  /  letter-spacing: -0.01em
H3 (Card):     32px - 34px   /  font-weight: 600  /  line-height: 1.2
H4 (Label):    20px - 24px   /  font-weight: 500  /  line-height: 1.3
Body:          16px           /  font-weight: 400  /  line-height: 1.6  /  color: #A1A1AA
Caption:       12px - 14px   /  font-weight: 400  /  line-height: 1.5  /  color: #A1A1AA
Pixel Number:  14px           /  font-weight: 400  /  如 [01], [02] 编号
```

### 3.3 字体特效

- **Display 字体**：允许使用渐变填充（黑→橙）或单色，带轻微发光 `text-shadow: 0 0 40px rgba(255,84,14,0.3)`
- **正文**：绝对不可使用纯黑背景上的纯白大段文字（刺眼），必须用 `#A1A1AA`
- **编号标签**：像素风格，橙色，如 `[01]`、`[02]`，使用等宽字体

---

## 4. 间距与布局系统

### 4.1 网格与容器

```
Max Width:     1280px - 1440px
Padding X:     24px (mobile) / 48px (tablet) / 80px (desktop)
Grid:          12列，列间距 24px (desktop) / 16px (mobile)
```

### 4.2 间距尺度（基于 8px 网格）

```
4px   — 极细间距（图标与文字）
8px   — 紧凑间距（按钮内边距上下）
16px  — 标准间距（卡片内边距、元素间距）
24px  — 中等间距（模块内元素组）
32px  — 宽松间距（卡片之间）
48px  — 区块内间距
64px  — 大区块间距
80px  — Section 之间间距
120px — 大 Section 分隔
```

### 4.3 布局原则

- **单屏叙事**：每个 Section 尽量占满 `100vh`，内容垂直居中或偏上
- **非对称平衡**：拒绝绝对居中，文字靠左/靠右，视觉元素占据另一侧
- **大量留白**：信息密度极低，一页只说一件事
- **Z轴层次**：背景(纯黑) → 装饰元素(3D/粒子) → 内容层(文字卡片) → 导航(固定顶部)

---

## 5. 组件规范

### 5.1 按钮 (Button)

**Primary Button**
```css
background: #FF540E;
color: #FFFFFF;
padding: 12px 28px;
border-radius: 6px;
font-size: 14px;
font-weight: 500;
letter-spacing: 0.05em;
transition: all 0.3s ease;
/* Hover */
background: #FF6B2C;
box-shadow: 0 0 20px rgba(255, 84, 14, 0.4);
```

**Secondary Button**
```css
background: transparent;
border: 1px solid #FF540E;
color: #FF540E;
padding: 12px 28px;
border-radius: 6px;
/* Hover */
background: rgba(255, 84, 14, 0.1);
```

**Ghost Button**
```css
background: transparent;
border: 1px solid rgba(255, 255, 255, 0.1);
color: #FFFFFF;
/* Hover */
border-color: rgba(255, 255, 255, 0.3);
```

### 5.2 卡片 (Card)

**Glass Card（玻璃态）**
```css
background: rgba(255, 255, 255, 0.03);
backdrop-filter: blur(12px);
border: 1px solid rgba(255, 255, 255, 0.08);
border-radius: 12px;
padding: 32px;
/* Hover 可选 */
border-color: rgba(255, 84, 14, 0.3);
transition: border-color 0.3s ease;
```

**Data Card（数据面板）**
```css
background: #0A0A0A;
border: 1px solid rgba(255, 255, 255, 0.06);
border-radius: 8px;
padding: 24px;
/* 内部数据高亮使用 #FF540E */
```

### 5.3 导航 (Navigation)

**Top Nav**
```css
position: fixed;
top: 0;
width: 100%;
height: 64px;
background: rgba(0, 0, 0, 0.8);
backdrop-filter: blur(12px);
border-bottom: 1px solid rgba(255, 255, 255, 0.05);
z-index: 50;
```

- Logo 左侧，菜单右侧
- 菜单项：白色文字，Hover 变橙色，无下划线
- 可选：右侧 CTA 按钮（橙色）

**Mobile Menu**
- 全屏覆盖菜单，黑色背景
- 菜单项大字号（32px+），垂直排列
- 右侧滑入或淡入动画

### 5.4 标签与徽章

**Section Number**
```css
font-family: monospace;
font-size: 14px;
color: #FF540E;
margin-bottom: 16px;
/* 样式: [01] [02] [03] */
```

**Tag/Badge**
```css
background: rgba(255, 84, 14, 0.15);
color: #FF540E;
padding: 4px 12px;
border-radius: 4px;
font-size: 12px;
font-weight: 500;
```

### 5.5 数据可视化（图表）

- **饼图/环形图**：主色 `#FF540E`，辅色 `#FFFFFF`，其他用 `#27272A` 层级递减
- **柱状图**：柱子用 `#FF540E`，背景网格线 `rgba(255,255,255,0.05)`
- **折线图**：线条 `#FF540E`，填充区域 `rgba(255, 84, 14, 0.1)`，数据点发光
- **数字展示**：大字号（48px+），白色，下方小字描述用灰色

---

## 6. 视觉元素与装饰

### 6.1 核心 3D 元素

- **双环交叉结构**（品牌符号）：金属质感，缓慢旋转，橙色发光边缘
- **实现建议**：
  - 方案 A：Spline 导出 WebGL 嵌入
  - 方案 B：Three.js 编写简单环面几何体 + 自定义材质
  - 方案 C：预渲染视频/GIF 循环（性能最优）

### 6.2 背景装饰

- **粒子效果**：极少量的白色/橙色微光粒子，缓慢漂移，不干扰阅读
- **网格线**：底部或边缘可有极淡的十字网格（`+` 排列），透明度 0.05
- **光晕**：页面局部可有径向渐变光晕 `radial-gradient(circle at 30% 50%, rgba(255,84,14,0.08), transparent 60%)`

### 6.3 图标

- 使用线性图标（Line style），1.5px 描边
- 颜色：默认 `#A1A1AA`，Hover 或激活态 `#FF540E`
- 推荐库：Lucide React, Heroicons

---

## 7. 动效与交互规范

### 7.1 页面加载

- **顺序**：背景 → 3D 元素淡入 → 导航滑入 → Hero 文字逐行显现
- **时长**：整体控制在 1.5s 内
- **缓动**：`cubic-bezier(0.16, 1, 0.3, 1)`（类似 Expo Out）

### 7.2 滚动动画

- **触发**：元素进入视口 20% 时触发
- **效果**：
  - 文字：从下方 30px 滑入 + 透明度 0→1
  - 卡片：从下方 50px 滑入 + 轻微缩放 0.95→1
  - 3D 元素：持续缓慢旋转（Y 轴 360° 循环，60s/圈）
- **时长**：0.6s - 0.8s
- **缓动**：`cubic-bezier(0.25, 0.46, 0.45, 0.94)`

### 7.3 Hover 效果

| 元素 | 效果 | 时长 |
|------|------|------|
| 按钮 | 亮度提升 + 外发光扩散 | 0.3s |
| 卡片 | 边框颜色变橙色 + 轻微上浮 translateY(-4px) | 0.3s |
| 链接 | 颜色白→橙，无下划线 | 0.2s |
| 图标 | 颜色灰→橙，轻微放大 1.1x | 0.2s |

### 7.4 微交互

- **按钮点击**：按下时 scale(0.97)，回弹
- **输入框聚焦**：边框从 `rgba(255,255,255,0.1)` 变为 `#FF540E`，底部发光
- **数据刷新**：数字滚动动画（CountUp 效果）

---

## 8. 页面模块结构（单页官网）

```
1. Navigation (固定顶部)
   └─ Logo | 菜单项 | CTA按钮

2. Hero Section (100vh)
   └─ 左侧：编号 [01] + 大标题 + 描述 + 双按钮
   └─ 右侧/中央：3D 双环视觉元素（缓慢旋转）
   └─ 底部：滚动提示（鼠标图标或文字）

3. Intro Section (100vh)
   └─ 非对称布局：文字在左下，大面积留白
   └─ 右下角：项目说明卡片（玻璃态）

4. Visual Identity Section (100vh)
   └─ 左侧：3D 金属质感特写图
   └─ 右侧：AI 概念图（机械人头像）
   └─ 背景：浅灰过渡（#1A1A1A）可选

5. UI Showcase Section (100vh)
   └─ 中央：品牌 Logo 展示（带发光边框）
   └─ 左下：介绍文字（玻璃态卡片）
   └─ 右上：导航菜单预览（橙色面板）

6. Color System Section (auto)
   └─ 展示三色色板：Black / Orange / White
   └─ 大标题：COLOR（像素字体）

7. Ecosystem Section (100vh)
   └─ 中央：3D 双环 + 周围环绕头像/Logo（节点感）
   └─ 隐喻：去中心化网络、连接

8. Typography Section (auto)
   └─ 展示字体层级和字符集
   └─ 背景：纯黑

9. Data Dashboard Section (100vh)
   └─ 左侧：数据卡片组（数字 + 图表）
   └─ 右侧：趋势图（折线图 + 发光效果）
   └─ 背景：浅灰（#111111）

10. Footer
    └─ 极简：Logo + 社交链接 + 版权信息
    └─ 文字颜色：#52525B（深灰）
```

---

## 9. 响应式断点

```
Mobile:   < 640px   (单列，文字缩小，3D 元素隐藏或替换为静态图)
Tablet:   640px - 1024px  (双列变单列，间距缩减)
Desktop:  1024px - 1440px (标准布局)
Large:    > 1440px  (最大容器 1440px 居中，两侧留白)
```

### 移动端特殊处理

- Hero 标题：48px - 64px
- 3D 元素：替换为预渲染图片或简化版视频
- 导航：汉堡菜单，全屏覆盖
- 卡片：全宽，单列堆叠
- 间距：Section 间距缩减为 48px - 64px

---

## 10. 给 AI 的一键生成 Prompt

```
请基于以下设计规范，使用 React + Tailwind CSS + shadcn/ui + Framer Motion 构建一个单页官网：

【风格】暗黑赛博科技（Dark Cyber-Industrial），纯黑背景，极简留白，非对称布局
【配色】背景 #000000，强调色 #FF540E（熔岩橙），文字白 #FFFFFF，辅助文字 #A1A1AA
【字体】标题使用 JetBrains Mono / Space Mono（像素/机能感），正文使用 Inter
【核心视觉】中央放置一个缓慢旋转的 3D 双环交叉结构（金属质感+橙色发光边缘），可用 CSS 3D 或静态图替代
【组件】玻璃态卡片（半透明+模糊+白边框）、橙色主按钮、幽灵按钮、数据面板
【动效】滚动触发淡入上滑、按钮 Hover 发光、卡片 Hover 边框变橙+上浮
【页面模块】导航 → Hero（大标题+3D元素+双按钮）→ 介绍 → 视觉展示 → 品牌色展示 → 生态网络 → 数据面板 → Footer
【要求】单屏叙事，每 Section 尽量占满视口，信息密度极低，留白充足，整体气质硬核、神秘、未来感
```

---

> 文档版本：v1.0
> 基于：XAIAgent 官网设计 by 梁敏亮（站酷）
> 适用：AI Agent / Web3 / 数据工具类项目官网
