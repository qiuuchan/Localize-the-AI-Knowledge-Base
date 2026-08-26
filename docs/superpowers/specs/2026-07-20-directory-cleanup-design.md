# KB-AI v0.8.10 · 目录与结构整理 · Design Spec

> **日期**:2026-07-20
> **作者**:maintainer + AI agent
> **状态**:🟡 待用户 review
> **范围**:文件层清理 + 文档归位 + 结构性微调
> **不涉及**:运行时功能变更 / API 改动 / RAG 管线改动 / 容器编排改动

---

## 1. 背景与目标

v0.7.0 → v0.8.9 期间,项目经历了三次结构性跃迁:Hybrid Search 上线(v0.7.2)、FastAPI 后端包装层替代 `chat.ps1`(v0.8.0)、自建 React 前端(v0.8.2)。期间积累了一批:

- **临时/历史文件**:7/9 原型备份、一次性压缩脚本、Docker 临时输出、npx skills 锁、ruff 根缓存等;
- **分叉/重复**:`backend/static/` 是 `frontend/dist/` 的 Jul 14 旧快照(已落后于 Jul 17 当前生产)、QUICKSTART 两份不同阶段版本、sessions.db 三处文件位置;
- **结构不一致**:`design/` vs `design-system/`、`docs/quickstart.md` vs 根 `QUICKSTART.md`。

**前端现状澄清**:`backend/static/index.html`(19 行)经 source map 验证,是 `frontend/` 经 Vite 7/14 构建的产物副本(`"../../../frontend/node_modules/..."`),不是独立设计实现。`main.py:66-68` 优先挂载 `frontend/dist/`(7/17 新版),`backend/static/` 仅作"免构建快照"备而未挂载。设计真实载体是 `frontend/src/`(含 App.tsx、components/、pages/)。

本次整理目标:把上述三类产物一次性清掉,让 `AGENTS.md §1` 文件地图与实际文件系统对齐,并把里程碑文档归入 `docs/releases/`。**不修改前端挂载链路**,仅删除已过时的 `backend/static/` 旧快照。

---

## 2. 范围与不动项

### 2.1 范围(scope)

✅ 包含:
- 文件/目录删除、迁移、改名;
- `AGENTS.md` / `CHANGELOG.md` / `README.md` 同步更新;
- 2 个运行时脚本 / 配置文件的同步修改(`backup.ps1` + `package.bat`);
- `.kb-ai-root/version` 文件内容更新。

❌ 不包含:
- 运行时功能(LLM 路由、检索管线、上传/解析、容器编排)任何逻辑改动;
- `.env` 任何文件;
- `start.bat` / `stop.bat` 内容(已锁版);
- 容器镜像 tag;
- `architecture-validation-report.md` Part 1。

### 2.2 本次特殊授权

`package.bat` 在 `AGENTS.md §7.2` 禁止修改列表中。本设计**用户明确授权**仅修改 `package.bat:67` 的源文件清单(将 `RELEASE-M3*.md` 三个文件路径加上 `docs\releases\` 前缀),其他内容保持原样。

---

## 3. 文件层动作(17 项)

### 3.1 删除 — 临时/历史(9 项)

| 路径 | 大小/状态 | 删除理由 |
|---|---|---|
| `_ubrain_backup_20260709/` | 整个 U-Brain 原型(7/9 备份) | git 历史可追;`.gitignore` 早已忽略 |
| `_trim_agents.py` | 18KB,一次性压缩 AGENTS.md 脚本 | 无任何代码引用;AGENTS.md 早已稳定 |
| `compose.err.tmp` / `compose.out.tmp` | Docker 临时输出 | `.gitignore` 忽略,运行残留 |
| `skills-lock.json` | npx skills 锁文件 | `.gitignore` 忽略 |
| `.ruff_cache/`(根) | ruff 根级缓存 | `backend/.ruff_cache/` 才是真缓存 |
| `backend/tests/integration/`(空目录) | 空 | 集成测试在顶层 `tests/integration/`,这是空壳 |
| `design-system/MASTER.md.v1.2.bak` / `v1.3.bak` | 2 份旧版设计规范 | git 历史可追 |

### 3.2 删除 — 重复/分叉(6 项)

| 路径 | 替代/规范 | 删除理由 |
|---|---|---|
| `docs/quickstart.md`(227 行,M1 骨架版) | 根 `QUICKSTART.md`(M3 完整版) | 重复,阶段已过 |
| `design/`(含 DEPRECATED design.md + 71KB .bak) | `design-system/MASTER.md` + `XAIAgent-design-spec.md` | `design/design.md` 自标 DEPRECATED |
| `backend/static/`(index.html + assets/index-*.js + assets/index-*.css + 452KB .map) | `frontend/dist/`(7/17 新版,`main.py:66-68` 优先挂载) | 7/14 旧快照,落后于生产;删除后 `frontend/dist/` 仍是单一前端,业务路径零变化 |
| `data/sessions.db`(32KB) | `data/db.sqlite` | `backend/core/sqlite.py:get_db_path()` v0.7.2 起统一至 db.sqlite;`backup.ps1:11` 自注"遗留库" |
| `backend/data/sessions.db`(32KB) | `data/db.sqlite` | 从未被任何代码引用 |
| `tmp/` 下 20+ 文件/目录(总计约 130MB,含 122MB 的 `db.sqlite.bak-before-drift-fix`、10+ ad-hoc test-*.ps1、dated 报告 md、7/13 repair 备份目录、stream-test.log、warm2.json 等) | 新建 `tmp/.gitkeep` 占位 | 漂移已修、临时脚本已用完;`tmp/backend.pid` 由后端启动时自动重建 |

### 3.3 迁移(3 项)

| 原路径 | 目标路径 | 理由 |
|---|---|---|
| `RELEASE-M3.md` | `docs/releases/RELEASE-M3.md` | 里程碑文档归 docs/ 统一管理 |
| `RELEASE-M3a.md` | `docs/releases/RELEASE-M3a.md` | 同上 |
| `RELEASE-M3b.md` | `docs/releases/RELEASE-M3b.md` | 同上 |

### 3.4 文件内容更新(1 项)

| 路径 | 改前 | 改后 | 理由 |
|---|---|---|---|
| `.kb-ai-root/version` | `0.8.2` | `0.8.9` | 与根 `version` 同步,避免 `scripts/version.ps1` 优先读到旧值 |

**优先级澄清(S1)**:`scripts/version.ps1:75-92` 中 `Read-VersionString` 按顺序读 `.kb-ai-root/version` → 根 `version` → 兜底 `0.7.0`。两者更新后,`.kb-ai-root/version` 优先返回 `0.8.9`,根 `version`(升 0.8.10)只在 `.kb-ai-root/version` 缺失时被读到。**`backend/main.py:_read_version()` 仅读根 `version`,不读 `.kb-ai-root/version`**,所以 `/api` 返回的版本号是根 `version` 的值(本次 0.8.10)。

---

## 4. 代码层同步修改(2 个文件)

### 4.1 ~~`backend/main.py:66-68` 挂载点修改~~ → **本次不动**

原计划改挂载点从 `frontend/dist` 改为 `backend/static`,经 P0 grep 复核后用户反转决定:**保留 `frontend/` 全套,删除过时的 `backend/static/`**。`main.py:66-68` 现状即正确,无需修改。

### 4.2 ~~`scripts/run-checks.ps1` 减步骤~~ → **本次不动**

原计划去掉 eslint + build 步骤(因 `frontend/` 被删),反转后 `frontend/` 保留,4 步 ruff/pytest/eslint/build 仍需保留,无需修改。

### 4.3 `scripts/backup.ps1`

**改动 1**(行 11 注释):
```diff
-      data\sessions.db(遗留库)
```

**改动 2**(行 135 备份循环):
```diff
-        foreach ($f in @('sessions.db', 'entities.json', 'embedding-cache.jsonl')) {
+        foreach ($f in @('entities.json', 'embedding-cache.jsonl')) {
```

**影响**:下次 `backup.ps1` 不再尝试拷贝 `data\sessions.db`(文件已删,无实际行为变化,仅日志更干净)。

### 4.4 `package.bat:67`(用户授权,本设计唯一受保护改动)

**改前**(line 67,foreach 块首):
```bat
foreach ($f in @('start.bat','stop.bat','docker-compose.yml','QUICKSTART.md','RELEASE-M3.md','RELEASE-M3a.md','RELEASE-M3b.md','package.bat','.env.example','.gitignore')) {
```

**改后**:
```bat
foreach ($f in @('start.bat','stop.bat','docker-compose.yml','QUICKSTART.md','docs\releases\RELEASE-M3.md','docs\releases\RELEASE-M3a.md','docs\releases\RELEASE-M3b.md','package.bat','.env.example','.gitignore')) {
```

**diff 范围限定(S2)**:仅 line 67 内 3 个文件名加 `docs\releases\` 前缀。`package.bat` 其他内容严禁改动。实施时用 `git diff` 复核:变更应只在这一行内。

**影响**:用户下次双击 `package.bat` 打包 KB-AI 时,3 个里程碑会进 `docs/releases/`,而不是根。

---

## 5. 文档层同步修改(3 个文件)

### 5.1 `AGENTS.md`

**§1 文件地图**(必读清单):
- `backend/static/` 行(原"内置前端(可选);主前端在 frontend/dist"行)整行删除(目录已删);
- `docs/quickstart.md` 行删除(根 `QUICKSTART.md` 行保留);
- `RELEASE-M3*` 路径加 `docs/releases/` 前缀;
- `design-system/` 行的 `.bak` 副本提法去掉;
- `design/` 整段删除;
- `frontend/` 行(原"v0.8.2 React 18 + TypeScript + Vite"行)保留,无改动;
- 树注释块里 `version` 文件说明的"0.8.6"措辞保留(指 `version` 文件本身)。

**§12.2 前端实施路径**:
- 删"完全替代 Dify Web UI(v0.8.2 用户批准)";
- 删"已交付后端任务(v0.8.0~v0.8.1)"整段;
- "当前实施风格:XAIAgent 暗黑赛博..." 段保留;
- "已应用:`backend/static/index.html`" 改写为"已部署:由 `backend/main.py` 挂载 `frontend/dist/` 至 :8000"。

**§13 变更记录**:新增 v0.8.10 段(见 §5.2)。

**§5 已知偏差表**:
- 第 5 行(启动脚本命名)保留;
- 第 9 行(架构跃迁 chat.ps1 → FastAPI)保留;
- 第 10 行(前端:Dify Web UI → 自建 React 前端 v0.8.2)措辞微调:第 2 列由 `frontend/dist/ vs http://localhost:8080` 改为 `frontend/dist/ vs http://localhost:8000`(语义已正确,只是当时还写的是 8080),第 3 列补一句"v0.8.10 删除 `backend/static/` 旧快照后,`frontend/dist/` 成为唯一前端"。

### 5.2 `CHANGELOG.md`

**顶部新增**(S4 已 grep 确认 line 5 是 "v0.7.0 之前的里程碑细节见 RELEASE-M3.md / RELEASE-M3a.md / RELEASE-M3b.md"):
```markdown
## [0.8.10] - 2026-07-20

### 整理(目录与结构一次性清理,无功能变更)
- **删除 9 个临时/历史项**:`_ubrain_backup_20260709/`、`_trim_agents.py`、`compose.err.tmp`、`compose.out.tmp`、`skills-lock.json`、根 `.ruff_cache/`、`backend/tests/integration/`(空)、`design-system/MASTER.md.v1.2.bak`、`design-system/MASTER.md.v1.3.bak`
- **删除 6 个重复/分叉项**:`docs/quickstart.md`、`design/`(自标 DEPRECATED)、`backend/static/`(frontend/dist/ 的 7/14 旧快照)、`data/sessions.db`+`backend/data/sessions.db`(v0.7.2 起统一至 `data/db.sqlite`)、`tmp/` 下 20+ 临时文件(总计约 130MB,含 122MB drift 备份)
- **迁移 3 项**:`RELEASE-M3*.md` → `docs/releases/`
- **代码层同步**:`scripts/backup.ps1:11,135` 移除 `sessions.db` 引用;`package.bat:67` 加 `docs\releases\` 前缀(用户授权)
- **文档层同步**:`AGENTS.md` §1/§5/§12.2/§13、`CHANGELOG.md` (本段)、`README.md` 目录树与版本链接
- **更新**:`.kb-ai-root/version` 0.8.2 → 0.8.9
- **版本号**:根 `version` 文件 0.8.9 → 0.8.10
- **不修改**:`backend/main.py`(挂载点现状正确)、`scripts/run-checks.ps1`(4 步仍适用)
- **验证**:见 docs/superpowers/specs/2026-07-20-directory-cleanup-design.md §6

```

**版本号同步**:根 `version` 文件 `0.8.9` → `0.8.10`(`backend/main.py:_read_version()` 通过 `get_root_dir() / "version"` 读取,自动生效)。

**引用更新**:`CHANGELOG.md:5` 的 "v0.7.0 之前的里程碑细节见 `RELEASE-M3.md` / `RELEASE-M3a.md` / `RELEASE-M3b.md`" 行的路径更新为 `docs/releases/RELEASE-M3.md` / `docs/releases/RELEASE-M3a.md` / `docs/releases/RELEASE-M3b.md`。

### 5.3 `README.md`

**目录结构节**:`backend/static/` 行(原"内置前端(可选);主前端在 frontend/dist")删除;`frontend/` 行保留(本来就是,无需改);`docs/` 描述保留;`design-system/` 描述保留;`design/` 行去掉(它本来就不在 README 目录树里,无需改)。

**版本与变更节**:"变更记录:[CHANGELOG.md](CHANGELOG.md)(Keep a Changelog 格式);M3 及更早的里程碑见 `RELEASE-M3*.md`。" → 改为 "变更记录:[CHANGELOG.md](CHANGELOG.md)(Keep a Changelog 格式);M3 及更早的里程碑见 [`docs/releases/RELEASE-M3*.md`](docs/releases/)。"

**开发命令节**:`cd frontend && npm run build` / `cd frontend && npm run lint` 保留(因为 `frontend/` 保留)。

---

## 6. 验证清单

| # | 验证项 | 命令 | 期望 |
|---|---|---|---|
| 1 | 启动链路 | 双击 `start.bat` → 浏览器打开 :8000 | 看到 React SPA(`frontend/dist/index.html`)+ XAIAgent 设计,与 `frontend/src/` 源码一致 |
| 2 | API 端点 | `curl http://localhost:8000/api` | 返回 `{"name":"KB-AI Backend","version":"0.8.10",...}` |
| 3 | 后端单测 | `backend/.venv/Scripts/python -m pytest tests/unit/ -q` | 全过 |
| 4 | 后端静态检查 | `backend/.venv/Scripts/python -m ruff check --config backend/ruff.toml backend/ tests/unit/ tests/integration/api/` | 全过 |
| 5 | 4 步 run-checks(保留) | `powershell -File scripts\run-checks.ps1` | [1/4] ruff + [2/4] pytest + [3/4] eslint + [4/4] build,全过 |
| 6 | 备份脚本 | `powershell -File scripts\backup.ps1 -Quiet` | 正常完成,zip 不再含 `sessions.db` |
| 7 | 路径脚本 | `powershell -File scripts\get-usb-root.ps1` | 输出根路径,`.kb-ai-root` 哨兵仍生效 |
| 8 | 版本号 | `powershell -File scripts\version.ps1` | `KB-AI v0.8.9 ...`(因 `.kb-ai-root/version` 优先) |
| 9 | 文档内链(S5 扩展) | `grep -rn "RELEASE-M3\|docs/quickstart\.md\|backend/static/\|MASTER\.md\.v[12]\.bak\|sessions\.db\|^frontend/dist" AGENTS.md CHANGELOG.md README.md QUICKSTART.md docs/` | 全部指向新位置或无残留;`frontend/dist` 在 README/AGENTS.md 中应保留 |
| 10 | `sessions.db` 残留扫描(H3 扩展) | `grep -rn "sessions\.db" backend/ scripts/ docker-compose.yml start.bat stop.bat package.bat AGENTS.md CHANGELOG.md README.md QUICKSTART.md docs/ 2>/dev/null` | 仅在历史/legacy 位置命中(chat.ps1、test_m2b.ps1、frontend-design-brief.md、m2-usage.md、Invoke-SqliteExec.ps1 docstring、`backend/api/sessions.py`/`backend/core/sqlite.py` docstring、tests/integration/README.md)。**当前生产代码路径**(`backend/main.py`、`backend/api/*.py` 实际函数体、`scripts/backup.ps1` 改后)零结果 |
| 11 | `frontend/` 仍存在 | `Test-Path frontend/dist/index.html` | True |
| 12 | `backend/static/` 已删 | `Test-Path backend/static/index.html` | False |
| 13 | `.gitignore` 完整性 | `git status` | 无未跟踪大文件;`data/.gitkeep` / `vectors/.gitkeep` / `cache/.gitkeep` / `logs/.gitkeep` / `tmp/.gitkeep` 出现在 untracked 列表(供 commit) |
| 14 | `package.bat` diff 范围(S2) | `git diff package.bat` | 仅 line 67 内 3 个文件名加 `docs\releases\` 前缀 |

---

## 7. 回退方案

本次全部动作由**一个 git commit**承载:

```bash
git add -A
git commit -m "chore(structure): v0.8.10 目录与结构整理

- 删除 9 个临时/历史项 + 6 个重复/分叉项
- 迁移 3 个里程碑文档至 docs/releases/
- 同步 backup.ps1 / package.bat
- 同步 AGENTS.md / CHANGELOG.md / README.md
- 版本号 0.8.9 → 0.8.10
- 详见 docs/superpowers/specs/2026-07-20-directory-cleanup-design.md"
```

**S6 修正**:commit message 内部路径统一使用正斜杠 `docs/superpowers/specs/...`(与 §1 风格一致)。

若任一验证项失败:`git reset --hard HEAD~1` 即可完全回退(所有文件未删除前已 add,reset 后会原样还原)。

**注意**:本次 `git commit` 操作需要用户**单独授权**才执行(AGENTS.md §7.2 默认禁止 AI 主动 commit)。

---

## 8. 风险与缓解

| 风险 | 等级 | 缓解 |
|---|---|---|
| **H2 后端运行时删 `tmp/backend.pid` 导致下次启动冲突** | 🟡 | §10 步骤 0 显式 `tasklist | findstr python` 检查后端进程;若在跑,先 `powershell -File scripts\stop-backend.ps1` 停后端,再继续 |
| **S8 122MB `db.sqlite.bak-before-drift-fix` 误删,含未导出内容** | 🟡 | §10 步骤 9 前置 sanity:`Test-Path data/db.sqlite` + `data/db.sqlite` 大小 > 100MB(健康) + `grep -c "INSERT INTO" data/db.sqlite` 不为 0(有数据)。三检全过才执行删除 |
| `package.bat` 改错(diff 越界) | 🟡 | §6 验证 #14 限定 `git diff` 范围;用户授权仅限 line 67 |
| `backup.ps1` 漏改,下次备份"找不到文件"日志噪音 | 🟢 | Test-Path 本来就静默跳过,仅注释变干净 |
| 用户在 `data/db.sqlite` 中已有未关连接时删除 `data/sessions.db` 失败 | 🟢 | 用 `Remove-Item -Force -ErrorAction SilentlyContinue` |
| `docs/superpowers/specs/` 目录首次创建 | 🟢 | `mkdir -p` 已确认;本文已落盘,目录自动被 git 跟踪 |
| `version` 升号后,前端 SSE 仍报旧版本 | 🟢 | `backend/main.py:_read_version()` 读根 `version` 文件,自动 |
| 删除 `backend/static/` 后,若未来某用户手抖删 `frontend/dist/`,无 fallback | 🟢 | `npm run build` 可重建(本机有 Node.js);无 Node.js 用户应跑 `package.bat` 重装 |
| 删除 `frontend/dist/` 后若想跳过 Node.js 重装 | 🟢 | 本设计不删 `frontend/`,只删 `backend/static/`;`frontend/dist/` 仍可重建 |

---

## 9. 不在本次范围(明确不做的)

- ❌ RAG 管线 11 模块的任何改动
- ❌ 容器编排调整
- ❌ 文档内容重写(仅做路径与版本号同步)
- ❌ `start.bat` / `stop.bat` 内容
- ❌ 任何 .env 文件
- ❌ 任何 LLM/Embedding 模型配置
- ❌ 任何 SQL/schema 改动

---

## 10. 实施检查表(给 writing-plans 用)

> 语法:S7 修正 — 用 GitHub task list 格式 `- [ ]`,可在 PR 渲染为复选框。

### 前置安全网

- [ ] **0a**(H2)`tasklist | findstr python` — 确认后端**未在跑**;若在跑,先 `powershell -File scripts\stop-backend.ps1` 停后端
- [ ] **0b**(H3)`grep -rn "sessions\.db" backend/ scripts/ docker-compose.yml start.bat stop.bat package.bat` — 期望:仅 `scripts/backup.ps1`(待改)+ `scripts/lib/Invoke-SqliteExec.ps1` docstring + `backend/api/sessions.py` + `backend/core/sqlite.py` docstring 命中;实际函数体与配置零引用
- [ ] **0c**(S10)`Test-Path data/db.sqlite` + 文件大小 > 100MB + `grep -c "INSERT INTO" data/db.sqlite` 不为 0(确认有数据,避免误删 122MB 备份前数据已丢)
- [ ] **0d**(S9)`Test-Path docs/superpowers/specs/2026-07-20-directory-cleanup-design.md` — 本设计 spec 已落盘,目录自动可被 git 跟踪

### 文件层动作

- [ ] 1. `mkdir -p docs/releases/`
- [ ] 2. `touch data/.gitkeep vectors/.gitkeep cache/.gitkeep logs/.gitkeep tmp/.gitkeep`(.gitignore 引用但不存在,本次补齐)
- [ ] 3. `mv RELEASE-M3.md RELEASE-M3a.md RELEASE-M3b.md → docs/releases/`
- [ ] 4. `rm -rf` 9 个临时项:`_ubrain_backup_20260709/`、`_trim_agents.py`、`compose.err.tmp`、`compose.out.tmp`、`skills-lock.json`、根 `.ruff_cache/`、`backend/tests/integration/`、`design-system/MASTER.md.v1.2.bak`、`design-system/MASTER.md.v1.3.bak`
- [ ] 5. `rm docs/quickstart.md`
- [ ] 6. `rm -rf design/`
- [ ] 7. `rm -rf backend/static/`(原 19 行 index.html + assets/ 含 452KB source map)
- [ ] 8. `rm data/sessions.db backend/data/sessions.db`(用 `-Force -ErrorAction SilentlyContinue`)
- [ ] 9. `rm -rf tmp/*`(保留新建的 `.gitkeep`)
- [ ] 10. `echo "0.8.9" > .kb-ai-root/version`

### 代码层动作

- [ ] 11. `Edit scripts/backup.ps1:11` 删 `data\sessions.db(遗留库)` 注释行
- [ ] 12. `Edit scripts/backup.ps1:135` 备份循环数组去 `sessions.db`
- [ ] 13. `Edit package.bat:67` foreach 数组中 3 个 `RELEASE-M3*.md` 前加 `docs\releases\` 前缀
- [ ] 14. **diff 范围复核**:`git diff package.bat` 应仅 line 67 一行变化

### 文档层动作

- [ ] 15. `Edit AGENTS.md §1` 删 `backend/static/` 行、删 `docs/quickstart.md` 行、`RELEASE-M3*` 加 `docs/releases/` 前缀、删 `design-system/MASTER.md*.bak` 提法、删 `design/` 段
- [ ] 16. `Edit AGENTS.md §5` 第 10 行(前端 React)措辞微调
- [ ] 17. `Edit AGENTS.md §12.2` "已应用:backend/static/index.html" 改写
- [ ] 18. `Edit AGENTS.md §13` 新增 v0.8.10 变更段
- [ ] 19. `Edit CHANGELOG.md:5` 3 个 `RELEASE-M3*.md` 加 `docs/releases/` 前缀
- [ ] 20. `Edit CHANGELOG.md` 顶部新增 `## [0.8.10] - 2026-07-20` 段(§5.2 已给完整文本)
- [ ] 21. `Edit README.md` 目录树删 `backend/static/` 行、版本链接加 `docs/releases/` 前缀
- [ ] 22. `Write version` 0.8.9 → 0.8.10

### 验证与提交

- [ ] 23. 跑 §6 验证 #1-14(14 项)
- [ ] 24. **用户单独授权**后:`git add -A && git commit -m "chore(structure): v0.8.10 目录与结构整理 ..."`

---

**Status**:🟡 待用户 review · 进入 writing-plans 前需要你确认本文档内容
