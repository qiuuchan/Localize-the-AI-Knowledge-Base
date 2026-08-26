# KB-AI · 移动硬盘便携启动可靠性收口设计

> **文档目的**：定义 KB-AI “移动硬盘接入干净 Windows 10/11、用户预装依赖为零、双击启动”愿景的首个可验收里程碑。
> **编写时间**：2026-07-27
> **当前基线**：KB-AI v1.5.2
> **状态**：设计已确认，待用户复核书面版本

---

## 0. 基本信息

| 项 | 内容 |
|---|---|
| 里程碑名称 | 移动硬盘便携启动可靠性收口 |
| 产品路线 | 分阶段完善 Docker Desktop，后续再评估原生便携化 |
| 交付实现 | 复用并校验现有完整离线镜像包 `tools/kb-ai-images.tar` |
| 客户机环境 | 干净 Windows 10/11；不预装 Docker、Python、Node.js、Git |
| 首次系统操作 | 允许一次管理员 UAC；Windows 功能需要时允许重启 |
| API Key | 由交付人员发盘前写入客户专属配置 |
| 验收范围 | 自动化门禁 + 开发机断网验证 + Win10/Win11 干净客户机实测 |

---

## 1. 背景与事实基线

KB-AI 的产品形态不是“交付源码让客户部署”，而是“移动硬盘即产品”。客户插入移动硬盘后，应通过双击入口完成主机检查、运行环境准备、服务启动和浏览器打开，不需要理解 Python、Node.js、Docker Compose、Qdrant、SQLite 或端口配置。

当前 v1.5.2 已具备：

- `precheck.bat` 检查 Windows 版本、CPU 虚拟化、移动盘空间、内存和 S Mode。
- `start.bat` 能从移动盘安装 Docker Desktop、加载离线镜像、启动 Compose 并打开浏览器。
- Compose 使用相对宿主路径，启动入口通过 `%~dp0` 定位项目根目录，不依赖固定 `E:\` 盘符。
- Docker Desktop 安装包、完整镜像归档和 reranker 模型已随盘提供。
- `stop.bat` 负责停止容器、等待落盘并执行备份。

2026-07-27 对 `tools/kb-ai-images.tar` 的 Docker save manifest 做了只读核验。归档已经包含 Compose 5 个服务所需的 4 个唯一镜像 tag：

```text
qdrant/qdrant:v1.7.0
langgenius/dify-api:1.0.0
kb-ai/dify-db-init:local
kb-ai/backend:local
```

`dify-api` 和 `dify-worker` 共用 `langgenius/dify-api:1.0.0`，所以 5 个服务对应 4 个唯一镜像。由此确认：**backend 镜像未随盘不是当前缺口，不应新增重复的 backend tar。**

当前真正需要收口的是：

1. `.docker-images-loaded.flag` 位于移动盘，无法表示当前客户机是否已经加载镜像；换电脑后会误判。
2. 镜像归档没有机器可读的版本、tag 和 SHA-256 完整性契约。
3. 归档缺失或加载失败时，现有流程可能回退到在线 pull/build，掩盖交付包缺陷。
4. 容器数据根目录可能形成 `data/data/db.sqlite` 分叉。
5. backend 容器可能使用 `localhost:6333`，无法连接 Qdrant 容器。
6. 容器内缺少宿主停止脚本时，浏览器关闭流程可能错误提示“可以安全弹出”。
7. 现有验证以结构测试为主，尚未形成 Win10 + Win11 干净客户机验收闭环。

### 1.1 本里程碑目标

1. 以现有单一镜像归档启动全部 5 个 Compose 服务，不增加重复大文件。
2. 客户机启动应用时不执行 `docker build`、`docker pull`、`pip install`、GitHub 下载或 Hugging Face 下载。
3. 换电脑或换盘符后，启动脚本根据当前电脑的 Docker tag 决定是否加载镜像。
4. 加载前验证归档版本、必需 tag 声明和 SHA-256。
5. backend 使用移动盘预期数据目录，并通过 Compose 服务名连接 Qdrant。
6. 容器模式下不再错误宣称浏览器内“关闭”操作已完成安全弹出。
7. 在干净 Windows 10 和 Windows 11 客户机上完成真实验收。

### 1.2 非目标

本里程碑明确不包含：

- 移除 Docker Desktop、WSL2 或管理员权限要求。
- 将 Docker、WSL 数据完全迁移到移动硬盘。
- 将 HF reranker 缓存从系统盘迁回移动硬盘。
- 恢复或重新打包 MinerU；PDF/PPTX/Office 解析能力边界保持现状。
- 改为完全本地 LLM；实际问答仍需联网调用阿里云百炼。
- 修改 `.env`、`package.bat`、锁定的第三方镜像 tag 或架构评审报告 Part 1。
- 自动迁移或删除现有 `data/data/` 内容。
- 与本里程碑无关的前后端重构和视觉改版。

---

## 2. 方案比较与决策

### 2.1 方案 A：校验现有单一完整归档（采用）

保留 `tools/kb-ai-images.tar`，新增 manifest、SHA-256、当前电脑 tag 检测和断网验收。

**优点**：不增加重复资产；复用当前已存在的完整归档；对现有启动链路改动最小。

**代价**：发布时必须保证单一归档小于目标移动盘文件系统的单文件限制，并为每次发布重新生成 manifest。

### 2.2 方案 B：拆分基础镜像和 backend 归档（不采用）

把 backend 镜像单独保存为第二个 tar。

**不采用原因**：当前单一归档已包含 backend 且总大小约 1.5 GB，远低于 FAT32 4 GB 单文件限制；现在拆分只会增加发布步骤和重复资产风险。若未来归档接近 4 GB，再单独设计拆分策略。

### 2.3 方案 C：客户机离线构建（不采用）

随盘提供 wheels、PyTorch 和 pwsh 等离线依赖，在客户机本地执行 Docker build。

**不采用原因**：首次启动耗时长；Windows/Docker 构建故障面大；仍需维护完整离线依赖闭包；不符合“客户机只负责运行”的原则。

---

## 3. 离线资产契约

### 3.1 镜像归档

继续使用：

```text
tools/kb-ai-images.tar
```

该归档必须包含以下 4 个唯一 tag，且 tag 值与 `docker-compose.yml` 一致：

- `qdrant/qdrant:v1.7.0`
- `langgenius/dify-api:1.0.0`
- `kb-ai/dify-db-init:local`
- `kb-ai/backend:local`

第三方镜像 tag 保持现有锁定值。

### 3.2 机器可读清单

新增 `tools/offline-images.manifest.json`。字段契约如下：

| 字段 | 类型 | 规则 |
|---|---|---|
| `schemaVersion` | integer | 固定为 `1` |
| `packageVersion` | string | 发布脚本从根 `version` 文件读取，不允许手工双写 |
| `archive.file` | string | 固定为 `kb-ai-images.tar` |
| `archive.sha256` | string | 归档实际 SHA-256，64 位小写十六进制 |
| `archive.sizeBytes` | integer | 归档实际字节数，用于快速检测截断 |
| `archive.requiredTags` | string[] | 上述 4 个唯一 tag，排序稳定 |
| `generatedAtUtc` | string | ISO 8601 UTC 时间，仅用于追溯 |

清单不得包含 `.env` 内容、API Key、客户名称或其他秘密。SHA-256 用于检测复制不完整或归档损坏，不替代代码签名。

### 3.3 发布侧打包工具

新增 PowerShell 5.1 脚本 `scripts/package-offline-images.ps1`，只供发盘/发布人员使用：

1. 校验项目根、Docker 可用性和根 `version`。
2. 校验 Compose 引用的 4 个唯一 tag 已存在。
3. 重新生成单一 `tools/kb-ai-images.tar`。
4. 从归档的 `manifest.json` 反向核验 4 个 tag。
5. 计算文件大小和 SHA-256。
6. 原子写入 `tools/offline-images.manifest.json`。
7. 输出版本、归档大小、tag 和校验结果。

该脚本不由客户机 `start.bat` 调用，不能修改 `.env`，也不能把 secrets 写入镜像或 manifest。生成多 GB 归档、构建镜像或访问网络时，实施阶段必须单独获得用户确认。

### 3.4 当前电脑镜像状态代替移动盘 flag

现有 `.docker-images-loaded.flag` 无法表达“当前这台电脑已经加载镜像”：移动硬盘换到另一台电脑后，flag 仍存在，但新电脑的 Docker 镜像库为空。

新逻辑：

- 4 个必需 tag 均存在：跳过归档哈希和加载。
- 任一必需 tag 缺失：校验 manifest、文件大小和 SHA-256，然后执行 `docker load`。
- 加载完成后再次检查 4 个 tag；仍缺失则失败。

旧 flag 不再参与启动判断，并加入 `.gitignore`，防止运行态文件污染工作区。

---

## 4. 启动状态机

`start.bat` 保留双击入口、PowerShell 5.1 兼容和现有日志机制，将关键步骤收紧为可恢复状态机。

### 4.1 主机预检

继续调用 `precheck.bat` 检查 Windows 版本、CPU 虚拟化、S Mode、最低内存、系统盘空间和移动盘空间。失败时不得安装 Docker 或加载镜像；屏幕输出中文原因、下一步和日志路径。

### 4.2 Docker Desktop 准备

- 已安装且 `docker info` 可用：继续。
- 未安装：调用随盘安装包并申请一次 UAC。
- Windows 功能尚未生效：提示“请重启电脑，重启后再次双击启动”，记录日志后退出。
- 安装失败：显示诊断信息，不删除客户数据，不尝试其他安装器。

首次 UAC 和必要重启属于当前 Docker 路线的已知产品边界。

### 4.3 配置检查

API Key 由交付人员发盘前配置。启动时检查 `.env` 存在，且 `ALIYUN_BAILIAN_API_KEY` 不是项目定义的占位符。失败时提示联系交付人员，不引导普通客户编辑 `.env`，也不把密钥写入日志。

### 4.4 离线资产校验与加载

当当前电脑缺少任一必需 tag 时：

1. 确认 manifest 和归档存在。
2. 校验 manifest schema、产品版本、归档文件名和 4 个 tag。
3. 先比较 `sizeBytes`，再用 PowerShell 5.1 `Get-FileHash -Algorithm SHA256` 校验归档。
4. 校验成功后执行 `docker load`。
5. 再次检查 4 个 tag。

离线资产缺失或损坏时 **失败即明确停止**，不自动执行 `docker pull`、`docker build` 或在线依赖下载。这样可避免网络回退掩盖发盘资产缺陷。

只有当前电脑缺少 tag、准备加载归档时才计算大文件 SHA-256；已有全部 tag 时跳过，控制后续启动耗时。

### 4.5 服务启动与就绪

执行 `docker compose up -d` 后验证：

- 5 个服务均按预期创建；一次性 init 服务允许成功退出。
- Qdrant 健康。
- backend HTTP 健康端点可访问。
- backend 的 Qdrant 配置指向 `http://qdrant:6333`。
- SQLite 实际路径位于挂载的 `/data`，对应移动盘 `data/`，不得写入新的 `/data/data/` 分叉。

只有核心服务就绪后才打开 `http://localhost:8000`。非核心能力降级应在前端展示，不得把核心依赖失败误报为成功。

---

## 5. 容器运行契约修复

### 5.1 项目根与数据目录分离

不能继续用一个 `KB_AI_ROOT` 同时表达“应用根目录”和“持久化数据目录”。设计上分离为：

- 应用根：容器内应用代码和版本文件所在目录。
- 数据根：显式环境变量 `KB_AI_DATA_DIR=/data`。

SQLite、上传文件、解析缓存和健康状态等持久化路径统一从数据根派生。宿主机继续挂载 `./data:/data`，因此盘符变化不会影响路径。

host Python fallback 保留现有默认行为：没有设置 `KB_AI_DATA_DIR` 时使用项目根下的 `data/`。测试必须覆盖容器显式路径和 host 默认路径。

禁止自动删除或迁移现有 `data/data/`。若确认其中有真实业务数据，另立带备份和回滚的数据迁移任务。

### 5.2 Qdrant 服务地址

Compose 为 backend 显式设置：

```text
QDRANT_URL=http://qdrant:6333
```

host Python fallback 继续使用 `http://localhost:6333` 默认值，代码不能把容器服务名硬编码为所有环境的默认地址。

### 5.3 容器模式关闭语义

浏览器无法可靠地直接停止宿主机 Docker Desktop，也不能完成 Windows 安全弹盘。因此：

- Compose 为 backend 设置 `KB_AI_RUNTIME_MODE=container`。
- `/api/shutdown` 在容器模式返回明确的“需要运行 `stop.bat`”结果，并设置 `safe_to_eject=false`。
- 前端不得在该结果下显示“现在可以安全拔出”。
- `stop.bat` 是本里程碑唯一安全停止入口：停止服务、等待数据落盘、执行备份、最后提示安全弹出。

host Python fallback 可保留脚本关闭能力，但必须基于实际执行结果设置 `safe_to_eject`。

---

## 6. 错误处理与可观测性

所有启动错误继续写入移动盘 `logs/start-*.log`。普通用户只看到可执行的下一步，不展示密钥、完整环境变量或冗长堆栈。

| 场景 | 用户提示 | 程序行为 |
|---|---|---|
| 虚拟化未开启 | 联系电脑管理员开启虚拟化 | 预检失败，停止 |
| Docker 安装后需重启 | 重启后再次双击启动 | 正常退出，可恢复 |
| API Key 缺失/占位 | 联系交付人员完成配置 | 不启动业务服务 |
| manifest 缺失或格式错误 | 交付包不完整 | 停止，不联网回退 |
| tar 大小或 SHA-256 不匹配 | 镜像包损坏，请重新复制或更换交付盘 | 停止，不执行 `docker load` |
| 加载后仍缺少 tag | 镜像包内容不匹配 | 停止并记录缺失 tag |
| Qdrant 不健康 | 知识库服务启动失败 | 不打开成功页面 |
| backend 超时 | 应用服务启动失败 | 保留容器和日志用于诊断 |
| 浏览器内点击关闭 | 请关闭页面并双击 `stop.bat` | 不宣称已安全弹出 |

失败处理不得删除 `data/`、`vectors/`、备份或客户资料。

---

## 7. 测试设计

### 7.1 自动化门禁

新增或调整测试，覆盖：

1. manifest 字段、文件名、文件大小和 SHA-256 格式。
2. manifest 的 4 个 tag 与 Compose 实际引用一致。
3. manifest 不含 secret-like 字段或真实 API Key。
4. `start.bat` 根据当前电脑 tag 状态决定加载，不读取 `.docker-images-loaded.flag`。
5. 缺失归档、截断归档、SHA-256 不匹配和加载后 tag 缺失均失败。
6. 离线启动控制流不包含 `docker pull`、`docker build`、pip、GitHub 或 Hugging Face 下载。
7. Compose 为 backend 设置正确的数据目录、Qdrant 地址和运行模式。
8. host fallback 保持 localhost Qdrant 和项目根 `data/` 默认行为。
9. 容器模式 shutdown 返回 `safe_to_eject=false`，前端不显示安全拔盘成功态。
10. 重复启动保持幂等，不重复加载当前电脑已有镜像。
11. `.docker-images-loaded.flag` 已被忽略且不参与控制流。

相关 ruff、pytest、PowerShell 结构测试、Vitest、eslint 和 Vite build 纳入常规验证。自动化门禁不调用付费 API。

### 7.2 开发机断网验证

在获得执行确认后，于可控测试环境执行：

1. 记录当前 Docker 状态。
2. 删除测试用 KB-AI 容器和镜像，不删除 volume 或移动盘数据。
3. 断开外网或通过受控方式阻止外部下载。
4. 从移动盘加载现有单一镜像归档。
5. 启动 5 个服务，确认没有 pull、build 或依赖下载。
6. 验证页面可打开、SQLite 路径正确、backend 可连接 Qdrant。
7. 恢复网络后执行一次真实问答，确认百炼调用正常并记录成本。
8. 执行 `stop.bat`，验证容器停止、数据落盘和备份。

删除本机测试镜像、启动容器、断网和真实 API 调用均属于实施期单独确认事项。

### 7.3 干净客户机验收

至少准备一台干净 Windows 10 和一台干净 Windows 11 机器。两台均未安装 Docker、Python、Node.js、Git，移动盘已由交付人员配置客户专属 API Key。

每台机器执行：

1. 插盘并记录实际盘符。
2. 双击 `start.bat`。
3. 接受一次 UAC；必要时重启并再次双击。
4. 确认镜像从移动盘加载，无在线构建和依赖下载。
5. 确认浏览器自动打开。
6. 上传一个当前受支持格式的文档并完成入库。
7. 执行一次真实问答并检查引用。
8. 连续启动 3 次，确认幂等。
9. 双击 `stop.bat`，确认服务停止、数据落盘和备份生成。
10. 安全弹出移动盘。
11. 记录系统盘新增内容；Docker Desktop、WSL 数据和现有 HF 缓存属于当前路线的已知残留。

### 7.4 性能门槛

- 首次安装和启动：不含人工重启等待，15 分钟内完成。
- Docker 已就绪后的正常启动：90 秒内打开可用页面。
- 连续启动 3 次：0 次失败。

### 7.5 验收证据

- 两台机器的 Windows 版本、内存和盘符。
- 对应 `logs/start-*.log`。
- 5 个服务状态。
- SQLite 和 Qdrant 持久化路径证据。
- 首次与后续启动耗时。
- 上传、问答和引用结果。
- `stop.bat` 输出与备份结果。
- 系统盘残留清单。

证据不得包含 API Key、客户文档正文或其他隐私数据。

---

## 8. 完成定义

只有同时满足以下条件，里程碑才能标记完成：

- [ ] 单一离线归档的 manifest、文件大小和 SHA-256 已生成并通过校验。
- [ ] manifest 与归档均包含 Compose 所需的 4 个唯一 tag。
- [ ] 客户机启动路径不再 build、pull 或下载运行依赖。
- [ ] 当前电脑 tag 检测替代移动盘全局 flag。
- [ ] 容器数据目录没有产生新的 `data/data/db.sqlite` 分叉。
- [ ] backend 通过 `qdrant:6333` 连接 Qdrant。
- [ ] 容器模式 shutdown 不再误报安全弹出。
- [ ] 相关 ruff、pytest、Vitest、eslint 和 Vite build 全绿。
- [ ] 开发机断网启动验证通过。
- [ ] Windows 10 干净客户机验收通过。
- [ ] Windows 11 干净客户机验收通过。
- [ ] 两个平台均满足性能门槛并完成 3 次连续启动。
- [ ] 用户文档准确说明 UAC、必要重启、联网问答和系统盘残留边界。

若缺少 Win10 或 Win11 实机，状态只能是“代码与打包完成，等待客户机验收”，不能宣称整个里程碑完成。

---

## 9. 风险与缓解

| 风险 | 等级 | 缓解 |
|---|---|---|
| 未来单一归档接近 FAT32 4 GB | 🟡 | 发布脚本设置体积门槛；达到门槛时另立拆包设计 |
| 每次启动计算大文件 SHA-256 太慢 | 🟡 | 仅在当前电脑缺少 tag、准备加载时校验 |
| 移动盘换电脑后旧 flag 误导 | 🔴 | 完全改为检查当前电脑 Docker tag |
| Docker 首装要求重启 | 🟡 | 状态机明确提示；重启后再次双击可恢复 |
| Docker/WSL 写入系统盘 | 🟡 | 作为当前路线已知边界记录，不宣称绿色免安装 |
| 数据目录修正遇到历史 `data/data/` | 🔴 | 不自动删除或迁移；先识别是否存在真实业务数据 |
| 安全关闭 API 无法停止宿主 Docker | 🔴 | 容器模式拒绝安全弹出；统一引导 `stop.bat` |
| 自动联网回退掩盖交付缺陷 | 🔴 | 离线资产失败即停止并记录原因 |
| API Key 泄漏到日志或 manifest | 🔴 | 清单禁止 secret 字段；日志测试扫描；证据脱敏 |
| Win10/Win11 行为差异 | 🟡 | 两个平台分别做干净机验收，不以开发机测试替代 |

---

## 10. 预计涉及文件

具体行号由实施计划在读取最新文件后确定。

| 文件 | 预计改动 |
|---|---|
| `start.bat` | manifest 校验、按当前电脑 tag 加载、移除 flag 控制、离线失败提示 |
| `.gitignore` | 忽略旧运行态 flag，并修正相关忽略规则格式 |
| `docker-compose.yml` | 显式数据目录、Qdrant 地址、运行模式 |
| `backend/core/config.py` | 分离项目根和数据根，同时兼容 host fallback |
| `backend/core/rag/qdrant_store.py` | 使用显式环境配置，保留 host 默认值 |
| `backend/api/shutdown.py` | 返回准确的 `safe_to_eject` 语义 |
| `frontend/src/App.tsx` 或对应关闭组件 | 容器模式引导用户执行 `stop.bat` |
| `scripts/package-offline-images.ps1` | 新增发布侧归档生成和 manifest 工具 |
| `tools/offline-images.manifest.json` | 新增机器可读离线资产清单 |
| `tests/unit/` | 数据目录、Qdrant、shutdown 契约测试 |
| `tests/integration/` | manifest、start.bat、Compose 和离线结构测试 |
| `frontend/src/__tests__/` | 关闭提示回归测试 |
| `scripts/run-checks.ps1` | 纳入相关无外部依赖测试与 Vitest |
| `README.md`、`QUICKSTART.md`、`docs/troubleshooting.md`、`docs/backend-container.md`、`客户必读.md` | 同步交付和故障边界 |
| `AGENTS.md`、`CHANGELOG.md`、`version` | 实施完成时同步项目状态和版本 |

二进制镜像归档是否纳入 Git 继续沿用项目现有资产管理策略；设计不要求把多 GB tar 提交到源码仓库。

---

## 11. 后续里程碑

1. **HF 模型留盘**：backend 只读挂载移动盘模型，不复制到 `%USERPROFILE%`。
2. **文档解析能力恢复**：离线打包并验证 MinerU，恢复 PDF/PPTX/Office 支持。
3. **首次使用图形化引导**：在不暴露 `.env` 的前提下提供配置和故障说明。
4. **系统盘残留治理**：评估 Docker data-root、WSL 导入或原生便携运行包。
5. **真正免 Docker 预研**：验证 Windows 原生 Qdrant/替代向量库和便携 Python 运行时。

---

## 12. 已确认决策

| 日期 | 决策 |
|---|---|
| 2026-07-27 | 产品路线采用“分阶段完善 Docker” |
| 2026-07-27 | 首个里程碑包含干净 Windows 客户机实测 |
| 2026-07-27 | 首次使用允许一次 UAC 和必要重启 |
| 2026-07-27 | API Key 由交付人员发盘前预配置 |
| 2026-07-27 | 采用完整镜像随盘，不在客户机离线构建 |
| 2026-07-27 | 里程碑包含数据路径、Qdrant 地址和关闭语义修复 |
| 2026-07-27 | 离线资产缺失或损坏时失败即停止，不自动联网回退 |
| 2026-07-27 | Win10 + Win11 双平台验收，并保留 15 分钟/90 秒性能门槛 |
| 2026-07-27 | 经 tar manifest 核验，现有单一归档已包含全部 4 个唯一镜像 tag；不新增重复 backend tar |
