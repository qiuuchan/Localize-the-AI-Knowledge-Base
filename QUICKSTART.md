# KB-AI · 快速开始指南

> **适用对象**:非技术用户(餐饮分公司老总)
> **技术读者**:CLI 入口见 `scripts/setup.ps1`(v0.7.1 由 `quickstart.ps1` 重命名,与本文件名消歧义)。
> **读完这篇**,您应该能从零开始,5 分钟内让 AI 助手跑起来。
> **不需要任何编程基础**——只要您能装微信,就能装这个。
> **重要前提**:本文是 M3 阶段完整版,涵盖文档上传、图片理解、多轮对话。
> **macOS 用户**:**跳过 §1-§9,直接看 [§10 macOS 部署](#10-macos-部署v170-新增)**(v1.7.0+)。
> **新 Mac 首次准备**:见 [`docs/superpowers/specs/2026-07-28-v1.7.0-mac-new-machine-setup.md`](docs/superpowers/specs/2026-07-28-v1.7.0-mac-new-machine-setup.md)(3 小时数据迁移 + 系统准备)
> **Mac 端 Kimi Code 接手**:见 [`docs/superpowers/specs/2026-07-28-v1.7.0-mac-kimi-handoff.md`](docs/superpowers/specs/2026-07-28-v1.7.0-mac-kimi-handoff.md)

---

## 0. 您手上的实物

您会拿到一个 **1TB 移动固态硬盘(SSD)**(看起来像大号 U 盘,信用卡大小,80 克)。

插到 Windows 10/11 电脑的 USB 口后,会看到这样的目录:

```
D:\                         ← U 盘根目录,卷标 AIAssistant
├── start.bat              ← 双击启动 AI 助手
├── stop.bat               ← 关闭 AI 助手(拔 U 盘前必做)
├── QUICKSTART.md          ← 您正在读的文件
├── docker-compose.yml     ← 5 个容器的配置
├── .env.example           ← 配置模板(请勿直接编辑)
├── .env                   ← 您的实际配置(需要您填 API Key)
├── docs\                  ← 说明文档
├── scripts\               ← 各种小工具
└── tests\                 ← 验收测试(工程师调试用)
```

---

## 1. 启动 — 2 分钟

**步骤**:

1. 插入 U 盘(电脑显示一个 1TB 的新硬盘)
2. 双击 `start.bat`
3. 等待 30-60 秒,屏幕会显示"启动完成"
4. 浏览器自动打开 AI 助手网页(http://localhost:8000)

**如果浏览器没自动打开**:手动打开浏览器,输入 `http://localhost:8000`

首次启动会加载预置的 Docker 镜像和模型,大约需要 3-5 分钟。之后每次启动 30-60 秒。

---

## 2. 配置 API Key — 1 分钟

**为什么?** 您的问题文字要发给阿里云(AI 大脑在云上),需要您的"通行证"。

**步骤**:

1. 第一次启动时,记事本会自动打开 `.env` 文件
2. 找到这一行:`ALIYUN_BAILIAN_API_KEY=sk-PLEASE-FILL-IN-...`
3. 把 `sk-PLEASE-FILL-IN-...` 替换成您的真实 API Key
4. 保存(Ctrl+S),关闭记事本
5. 在终端窗口按 Enter 继续

**API Key 在哪申请?**:登录 https://bailian.console.aliyun.com/ → 右上角头像 → API-Key 管理 → 创建 API Key → 复制(以 `sk-` 开头)。一次创建,永久使用。

---

## 3. 对话 — 30 秒

### 第一次试对话

1. 浏览器 Dify 界面 → 右上角"工作室" → 创建空白应用 → 类型选"聊天助手"
2. 应用创建后,左侧"知识库" → 创建知识库 → 上传一些文档(等 5-10 分钟入库)
3. **最简单的对话 — 不用打开网页**,直接在 U 盘根目录按住 Shift+右键 → "在此处打开 PowerShell 窗口",输入:

```
powershell -File scripts\chat.ps1 -Question "你好"
```

如果您看到 AI 的回答,说明一切就绪!

### 多轮对话

加上 `-SessionId` 参数(任意 UUID,首次可省略):

```
powershell -File scripts\chat.ps1 -SessionId "" -Question "红烧肉怎么做?"
```

下次同样 `-SessionId "abc-uuid"` 再问一次,AI 会记得上下文。

---

## 4. 上传文档 — 5 分钟

把您电脑上的 Word / PDF / PPT / Excel 文档导入知识库:

```
powershell -File scripts\parse-doc.ps1 -Input "C:\Users\您的名字\Documents\菜单.docx"
powershell -File scripts\embed-and-ingest.ps1
```

第二条命令会调阿里云 Embedding 模型把每页文本变成"数字表示",写入 U 盘上的向量数据库。5 分钟内可被 AI 引用。

**批量**:`parse-doc.ps1 -InputFolder C:\Documents\菜单汇总\`(整个文件夹一起处理)。

---

## 5. 弹出 — 必做!

**拔 U 盘前必须做的两步**(否则 SQLite 数据库可能损坏):

```
powershell -File scripts\safe-eject.ps1
```

5 秒倒计时,按 Enter 确认 → 自动调 stop.bat 停容器 → Windows 弹窗"可以安全拔出 U 盘"→ 在系统托盘找到 USB 弹出图标 → 选择 USB SSD → 物理拔出。

**重要提示**:直接拔 U 盘会损坏 SQLite 数据库,导致下次启动失败。

---

## 6. 故障排查

### 问题 1:Docker Desktop 未装或未启动
**现象**:双击 start.bat 后**预检就失败**(5 项检查里 [1/5] CPU 虚拟化 或 [2/5] Windows 版本 没过);或者黑窗口显示"[错误] Docker Desktop 安装失败"
**解决**:
- **看 precheck 输出**:v1.5.2.1+ 黑窗口会直接告诉您哪项不通过 + 原因 + 建议。**拍照这一屏发微信给发盘人**。
- **如果显示"Docker 未安装,正在从 U 盘离线包自动安装"后又失败**:说明自动装不上(常见原因:CPU 虚拟化未开 / 系统是 Win10 S / 缺管理员权限)。
- **如果 Docker Desktop 已装但没启动**:右键桌面"Docker Desktop"图标 → 选"启动",等 30 秒 → 重跑 start.bat。

### 问题 2:端口 8080 / 6333 / 5001 占用
**现象**:docker compose up 失败,提示 port is already allocated
**解决**:用记事本打开 `.env`,修改 `DIFY_PORT=8081`(换不冲突的端口)

### 问题 3:AI 调用一直失败
**现象**:chat.ps1 报错 "API 调用失败" 或 "网络超时"
**解决**:跑 `powershell -File scripts\status-bar.ps1 -Mode auto -Loop` 看在线状态,30 秒后会自动刷新

### 问题 4:AI 服务 OFFLINE
**现象**:health-full.ps1 显示 "OFFLINE(AI 暂不可用)"
**解决**:检查网络是否畅通(能否打开 https://bailian.console.aliyun.com/),或等待 60 秒后重跑

### 问题 5:U 盘容量告警
**现象**:health-full.ps1 显示"容量告警"
**解决**:跑 `powershell -File scripts\disk-alert.ps1` 看等级:
  - 0 (绿色):正常
  - 1-2 (黄色):建议清理
  - 3+ (红色):禁止新增文档

### 问题 6:完全不知道哪里出错了
**终极方案**:跑 `powershell -File scripts\health-full.ps1`,一屏看到所有指标。
把这一屏截图发给工程师,通常能定位 80% 的问题。

### 问题 7:忘记命令了
**万能帮手**:跑 `powershell -File scripts\show-help.ps1`,列出所有可用命令。

### 问题 8:首次 5 分钟引导
**最快路径**:在 U 盘根目录按住 Shift+右键 → "在此处打开 PowerShell 窗口" → `powershell -File scripts\setup.ps1`,自动走完 5 步。

---

## 7. 命令速查

| 命令 | 作用 |
|------|------|
| `start.bat` | 启动 AI 助手(双击) |
| `stop.bat` | 停止 AI 助手(双击) |
| `powershell -File scripts\setup.ps1` | 5 步引导(首次使用推荐) |
| `powershell -File scripts\show-help.ps1` | 命令速查 |
| `powershell -File scripts\health-full.ps1` | 1 屏健康度自检 |
| `powershell -File scripts\chat.ps1 -Question "..."` | 单次对话 |
| `powershell -File scripts\chat.ps1 -SessionId "" -Question "..."` | 首次多轮对话 |
| `powershell -File scripts\parse-doc.ps1 -Input 文档.pdf` | 解析单个文档 |
| `powershell -File scripts\embed-and-ingest.ps1 -ChunksFile ...` | 文档入库(Embedding) |
| `powershell -File scripts\safe-eject.ps1` | 安全弹出 U 盘 |
| `powershell -File scripts\status-bar.ps1 -Mode auto -Loop` | 后台状态轮询 |

---

## 8. 还有问题?

1. **查看日志**:`logs\` 目录下的最新 `.log` 文件
2. **跑完整测试**:`powershell -File tests\e2e_test.ps1`(工程验收)
3. **看发布说明**:`RELEASE-M3.md`(本阶段技术详情,工程师用)

---

## 9. 系统边界与限制

请在使用前了解本系统的"硬边界",避免误用:

| 维度 | 边界 | 备注 |
|---|---|---|
| 部署 | **单设备**(U 盘一次只能在 1 台电脑用) | 不支持多设备同步 |
| 用户 | **单用户**,无登录/权限 | 多人共享同一对话记录 |
| 端口 | **127.0.0.1 环回口**(6333/6334/8000/8001) | 不暴露 LAN/公网,无 TLS/Auth |
| 离线能力 | 知识库检索 / 历史对话可用;AI 生成不可用(降级提示) | 无网时降级到 websearch 也不可用 |
| 单文件大小 | **200 MB** | 超出走 `backend/core/rag/mineru.py` SIZE_LIMIT_BYTES |
| 单图大小 | **20 MB** | `/api/knowledge/upload` 413 拦截 |
| 多图批量 | **5 张/次** | `/api/knowledge/upload` 413 拦截 |
| 对话长度 | **1-100 轮**可配(默认 50) | 80% 时 soft_warning;超限截断 |
| 数据规模 | 实测 ~300GB 文档 + ~100GB 向量 | U 盘 1TB 留 ~575GB 余量 |
| 容器资源 | **5 容器全设 `mem_limit` / `cpus`**(v0.7.1 加固,v1.5.0 kb-ai-backend 加入) | 见 `docker-compose.yml` 每容器配置 |
| LLM 模型 | qwen3.6-plus(默认) + qwen3.7-max(复杂) | 阿里云百炼 API,商业配额计费 |
| 月度配额 | 默认 block ¥1500/月 | 可 `.env` `COST_ALERT_THRESHOLDS` 覆盖,详见 degradation-guide |
| U 盘物理风险 | 丢失 = 数据外泄;损坏 = 数据丢失 | 用户已接受,见 PRD §2.2 |

**降级场景**详见 [`docs/degradation-guide.md`](docs/degradation-guide.md)。

---

## 10. macOS 部署(v1.7.0+ 新增)

> **本节适用对象**:MacBook Air / Pro(M1/M2/M3/Intel)+ macOS 13+(Ventura)+ Apple Silicon 推荐
> **首次部署预留时间**:~20 分钟(装 PowerShell + 格式化 U 盘 + 拉镜像 + 验收)
> **Windows 用户跳过本节**

### 10.1 一次性准备(~10 分钟)

**步骤 1:装 PowerShell 7+**(KB-AI 编排脚本语言)

```bash
brew install --cask powershell
```

验证:`pwsh --version` 应输出 `7.4.x` 或更高。

**步骤 2:U 盘准备**

⚠️ **必须 exFAT 或 APFS,不能用 NTFS**(Mac 默认对 NTFS 只读,Qdrant / SQLite 写不进去)

```bash
# 看 U 盘设备号
diskutil list
# 假设是 /dev/disk2(看清再做,选错会清掉电脑硬盘!)

# 1. 格式化为 exFAT(跨 Win/Mac 互通)
diskutil eraseDisk ExFAT AIAssistant /dev/disk2

# 2. 如果只在 Mac 上用,APFS 性能更好(时间戳纳秒精度)
# diskutil eraseDisk APFS AIAssistant /dev/disk2
```

**步骤 3:把 KB-AI 源文件拷到 U 盘**

```bash
# 假设 U 盘挂载到 /Volumes/AIAssistant
cp -R /path/to/KB-AI/. /Volumes/AIAssistant/
ls /Volumes/AIAssistant/start.command   # 应存在
```

### 10.2 启动 KB-AI

**双击 `start.command`**(Finder 中)

首次会弹 Gatekeeper:

> "无法打开,因为它来自身份不明的开发者"

**解决**:右键 `start.command` → 打开方式 → 打开(只需一次,之后双击直接走)

启动脚本会:
1. 跑 5 项预检(虚拟化 / OS / 磁盘 / 内存 / SIP)
2. 拉起 Docker Desktop(`open -a Docker`)
3. 启动 5 容器 + FastAPI 后端
4. 打开浏览器到 `http://localhost:8000`

冷启动约 30-90 秒。

### 10.3 停止 + 安全弹出

**双击 `stop.command`**:

1. 5 秒倒计时确认
2. 停止后端容器 + 全部容器
3. 自动备份数据到电脑硬盘
4. 弹"现在可以拔出"对话框(osascript)
5. 桌面拖 USB SSD 图标到废纸篓 → 等待消失 → 物理拔出

### 10.4 故障排查(Mac 专属)

| 症状 | 原因 | 解决 |
|---|---|---|
| `pwsh: command not found` | 未装 PowerShell 7+ | `brew install --cask powershell` |
| `Cannot connect to the Docker daemon` | Docker Desktop 未启 | `open -a Docker` + 等 30 秒 |
| `permission denied: start.command` | 无可执行位 | `chmod +x start.command` |
| 首次双击弹 Gatekeeper | 未签名 | 右键 → 打开 → 始终允许 |
| `xcrun: error: invalid active developer path` | Xcode CLT 未装 | `xcode-select --install` |
| `database is locked` (Dify SQLite) | virtiofs 并发问题 | 反馈给发盘人,临时回退 gRPC-FUSE |

### 10.5 文件系统选型建议

| 特性 | exFAT | APFS |
|---|---|---|
| 跨 Win/Mac 读写 | ✅ | ❌(Win 需第三方工具) |
| 时间戳精度 | 2 秒 | 纳秒 |
| SQLite/Qdrant 并发写 | 良好 | 优秀 |
| 适合场景 | 多人共用 U 盘(Win + Mac) | 纯 Mac 环境,追求性能 |

**推荐**:跨平台用 exFAT;纯 Mac 且不放 Win 用 APFS。

### 10.6 与 Windows 体验差异

| 功能 | Windows | macOS |
|---|---|---|
| 双击入口 | `start.bat` | `start.command` |
| 启动通知 | cmd 窗口 + 中文 chcp 65001 | Terminal.app 自动开 |
| 浏览器打开 | `start "" URL` | `open URL` |
| "现在可以拔出"弹窗 | WinForms MessageBox | osascript System Events |
| Docker 启动 | `Docker Desktop.exe` | `open -a Docker` |
| HF 模型缓存 | `%USERPROFILE%\.cache\huggingface` | `~/.cache/huggingface` |
| 安全弹出 | 系统托盘图标 | 访达废纸篓 / `diskutil unmountDisk` |

---

**最后更新**:2026-07-28 · v1.7.0 同步版(新增 §10 macOS 部署)
