# KB-AI v0.8.10 · 目录与结构整理 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 一次性清掉 v0.7→v0.8 跃迁期间积累的 13 个文件组 + 迁 3 个里程碑文档 + 同步 `backup.ps1` / `package.bat` + 升版本号 0.8.9 → 0.8.10。零功能变更,单 git commit。

**Architecture:** 单 commit 清理方案。Task 是执行阶段(每个 task 独立可验证),最终在 Task 10 一次性 commit(按 spec §7)。顺序:前置安全网 → 建占位 → 删临时 → 删重复 → 改代码 → 改文档 → 升版本 → 全量验证 → commit。

**Tech Stack:** Git Bash、PowerShell 5.1、Python 3.12 (backend/.venv)、pytest、ruff、npm

## Global Constraints

- **Spec**:`docs/superpowers/specs/2026-07-20-directory-cleanup-design.md`(本文档是其实现)
- **工作目录**:项目根 `E:/`(假定 KB-AI 仓在此)
- **单 commit 收尾**:所有变更在 Task 10 一次性 commit;中间 task 状态可工作但不 commit
- **不动项**:`.env` / `start.bat` / `stop.bat` / 容器镜像 tag / `architecture-validation-report.md` Part 1
- **`package.bat` diff 范围仅 line 67**(用户授权,其他行严禁改动)— 实施后用 `git diff package.bat` 复核
- **PowerShell 5.1 兼容**:无 `??`、无 `Get-Content -Raw` 之外的不存在 API;写文件优先 `[System.IO.File]::WriteAllText(..., [System.Text.UTF8Encoding]::new($false))`
- **Ruff 配置**:`backend/ruff.toml`(调 ruff 时显式 `--config backend/ruff.toml`)
- **前端/后端路径决策**:**保留** `frontend/`(`src/` + `dist/` + `node_modules/` + 全部配置);**删除** `backend/static/`(7/14 旧 Vite 快照)
- **版本号读取优先级**(`scripts/version.ps1:78-82`):`.kb-ai-root/version` → 根 `version` → 0.7.0。本计划完成后:`.kb-ai-root/version`=**0.8.9**,根 `version`=**0.8.10**
- **`backend/main.py:_read_version()` 只读根 `version`**:所以 `/api` 端点返回 `0.8.10`
- **gitignore 关注**:`data/`, `vectors/`, `cache/`, `logs/`, `tmp/` 全部 gitignored,本次补 5 个 `.gitkeep` 占位

---

## Task 1: Pre-flight 安全网

**Files:**
- 不修改任何文件
- 检查:运行中后端进程、`sessions.db` 引用、122MB 数据库健康、spec 文件存在

**目的:** 在动刀前验证环境安全,避免误删正在用的资源或破坏数据完整性。

- [ ] **Step 1: 确认 KB-AI 工作目录**

```bash
cd E:/
pwd
```

期望输出:`/e/`(Git Bash 形式)

- [ ] **Step 2: 确认 spec 文件已落盘**

```bash
test -f "docs/superpowers/specs/2026-07-20-directory-cleanup-design.md" && echo "OK"
```

期望输出:`OK`

- [ ] **Step 3: 确认后端未在跑(H2 风险)**

```bash
tasklist | grep -i python || echo "No python processes"
```

期望输出:`No python processes`(或仅 IDE/系统 python,无 uvicorn)

如果看到 `python.exe` 在跑,**先停后端**:
```bash
powershell -File scripts/stop-backend.ps1
```

然后再 grep 一次确认。

- [ ] **Step 4: 验证 `data/db.sqlite` 健康,数据未丢(S8 风险)**

```bash
test -f "data/db.sqlite" && \
  SIZE=$(stat -c%s "data/db.sqlite" 2>/dev/null || stat -f%z "data/db.sqlite") && \
  echo "db.sqlite size: $SIZE bytes" && \
  if [ "$SIZE" -lt 104857600 ]; then echo "WARN: db.sqlite < 100MB,异常"; fi
```

然后用 Python 验证表结构(避免 `grep` 对二进制文件报警告):

```bash
backend/.venv/Scripts/python -c "
import sqlite3, sys
c = sqlite3.connect('data/db.sqlite')
tables = [r[0] for r in c.execute(\"SELECT name FROM sqlite_master WHERE type='table'\").fetchall()]
print('tables:', tables)
if not tables:
    print('ERROR: no tables found'); sys.exit(1)
for t in tables:
    count = c.execute(f'SELECT count(*) FROM \"{t}\"').fetchone()[0]
    print(f'  {t}: {count} rows')
c.close()
"
```

期望输出:列出若干表(如 `sessions`, `messages`, `degradation_events`, `keyword_index`)及各表行数,至少一个表有数据

- [ ] **Step 5: 扫描当前 `sessions.db` 引用面(H3 风险)**

```bash
grep -rn "sessions\.db" backend/ scripts/ docker-compose.yml start.bat stop.bat package.bat 2>/dev/null
```

期望看到:
- `scripts/backup.ps1:11` 和 `:135`(待改)
- `scripts/lib/Invoke-SqliteExec.ps1:26`(docstring 示例,不动)
- `backend/api/sessions.py:1`(docstring,不动)
- `backend/core/sqlite.py:1`(docstring,不动)

**不应**在 `backend/main.py` 或 `backend/api/*.py` 的实际函数体看到 `sessions.db`。

- [ ] **Step 6: git 状态检查**

```bash
git status --short
```

期望输出:空(工作区干净)或仅有未追踪项。

**⚠️ 禁止带未提交变更进入 Task 2**:若有 modified 文件,先 `git stash` 或提交后再继续。本计划会大量删除/移动文件,带脏状态进入会导致 `git status` 无法区分计划变更与之前的修改,回退也会误丢旧变更。

- [ ] **Step 7(S10): 重建 `frontend/dist/`(确保与源码同步)**

反转决策后 `frontend/dist/` 是生产前端真相源。若 dist 过期(源码改了但没 build),UI 会落后于 `frontend/src/`。

```bash
cd E:/frontend && npm run build
```

期望输出:Vite 构建成功,`dist/` 目录更新。

**若 Node.js 或 npm 不可用**:跳过本步,但在 commit message 中注明 `frontend/dist/ 为当前快照,如需更新请手动 npm run build`。

---

## Task 2: 建占位与迁移

**Files:**
- Create: `data/.gitkeep`, `vectors/.gitkeep`, `cache/.gitkeep`, `logs/.gitkeep`, `tmp/.gitkeep`
- Move: `RELEASE-M3.md` / `RELEASE-M3a.md` / `RELEASE-M3b.md` → `docs/releases/`
- 注:`docs/releases/` 迁移后会有 3 个 .md 文件,git 自动跟踪该目录,无需 `.gitkeep`

**目的:** 建好后续 `rm` 后的占位,并把里程碑文档移入 docs/ 统一管理。

- [ ] **Step 1: 创建 `docs/releases/` 目录**

```bash
mkdir -p "docs/releases"
```

- [ ] **Step 2: 创建 5 个 `.gitkeep` 占位**

```bash
touch "data/.gitkeep" "vectors/.gitkeep" "cache/.gitkeep" "logs/.gitkeep" "tmp/.gitkeep"
```

- [ ] **Step 3: 验证 .gitignore 引用匹配**

```bash
grep -E "^(data|vectors|cache|logs|tmp)/\*" .gitignore
grep -E "^!(data|vectors|cache|logs|tmp)/\.gitkeep" .gitignore
```

期望看到 5 个 `xxx/*` 和 5 个 `!xxx/.gitkeep` 配对。

- [ ] **Step 4: 迁移 3 个里程碑文档**

```bash
mv "RELEASE-M3.md" "docs/releases/RELEASE-M3.md"
mv "RELEASE-M3a.md" "docs/releases/RELEASE-M3a.md"
mv "RELEASE-M3b.md" "docs/releases/RELEASE-M3b.md"
```

- [ ] **Step 5: 验证迁移**

```bash
ls "docs/releases/"
test ! -f "RELEASE-M3.md" && echo "old RELEASE-M3.md gone"
```

期望输出:`RELEASE-M3.md  RELEASE-M3a.md  RELEASE-M3b.md` + `old RELEASE-M3.md gone`

---

## Task 3: 删 9 个临时/历史项

**Files:**
- Delete: `_ubrain_backup_20260709/`, `_trim_agents.py`, `compose.err.tmp`, `compose.out.tmp`, `skills-lock.json`, `.ruff_cache/`(根), `backend/tests/integration/`(空), `design-system/MASTER.md.v1.2.bak`, `design-system/MASTER.md.v1.3.bak`

**目的:** 清理 7/9 原型备份、一次性脚本、Docker 临时输出、npx 锁、ruff 根缓存、空目录、旧版设计规范。

- [ ] **Step 1: 删 7/9 原型备份**

```bash
rm -rf "_ubrain_backup_20260709"
```

- [ ] **Step 2: 删一次性压缩脚本**

```bash
rm "_trim_agents.py"
```

- [ ] **Step 3: 删 Docker 临时输出**

```bash
rm -f "compose.err.tmp" "compose.out.tmp"
```

- [ ] **Step 4: 删 npx skills 锁**

```bash
rm -f "skills-lock.json"
```

- [ ] **Step 5: 删 ruff 根级缓存**

```bash
rm -rf ".ruff_cache"
```

- [ ] **Step 6: 删空 `backend/tests/integration/`**

```bash
rmdir "backend/tests/integration" 2>/dev/null || rm -rf "backend/tests/integration"
```

- [ ] **Step 7: 删 2 份旧版设计规范**

```bash
rm "design-system/MASTER.md.v1.2.bak" "design-system/MASTER.md.v1.3.bak"
```

- [ ] **Step 8: 验证 9 项全删**

```bash
test ! -d "_ubrain_backup_20260709" && \
test ! -f "_trim_agents.py" && \
test ! -f "compose.err.tmp" && \
test ! -f "compose.out.tmp" && \
test ! -f "skills-lock.json" && \
test ! -d ".ruff_cache" && \
test ! -d "backend/tests/integration" && \
test ! -f "design-system/MASTER.md.v1.2.bak" && \
test ! -f "design-system/MASTER.md.v1.3.bak" && \
echo "all 9 temporary items removed"
```

期望输出:`all 9 temporary items removed`

- [ ] **Step 9: 验证 `backend/.ruff_cache/` 仍存在(真正的 ruff 缓存)**

```bash
test -d "backend/.ruff_cache" && echo "backend/.ruff_cache OK"
```

期望输出:`backend/.ruff_cache OK`

---

## Task 4: 删 6 个重复/分叉项

**Files:**
- Delete: `docs/quickstart.md`, `design/`, `backend/static/`, `data/sessions.db`, `backend/data/sessions.db`, `tmp/*`(保留 `.gitkeep`)

**目的:** 清理已合并的旧文档、DEPRECATED 目录、7/14 旧 Vite 快照、两个死 sessions.db、~130MB 临时数据。

- [ ] **Step 1: 删旧 `docs/quickstart.md`(M1 骨架版)**

```bash
rm "docs/quickstart.md"
```

- [ ] **Step 2: 删 `design/` 整个目录**

```bash
rm -rf "design"
```

- [ ] **Step 3: 删 `backend/static/`(7/14 旧快照)**

```bash
rm -rf "backend/static"
```

- [ ] **Step 4: 删两个死 sessions.db**

```bash
rm -f "data/sessions.db" "backend/data/sessions.db"
```

- [ ] **Step 5: 验证 5 项已删 + 清理空目录**

```bash
test ! -f "docs/quickstart.md" && \
test ! -d "design" && \
test ! -d "backend/static" && \
test ! -f "data/sessions.db" && \
test ! -f "backend/data/sessions.db" && \
echo "5 duplicate items removed"
```

期望输出:`5 duplicate items removed`

若 `backend/data/` 目录变空,顺手清理(S12):
```bash
rmdir "backend/data" 2>/dev/null || true
```

- [ ] **Step 6: 验证 `frontend/` 仍存在(反转决策的关键校验)**

```bash
test -f "frontend/dist/index.html" && \
test -d "frontend/src" && \
test -f "frontend/package.json" && \
echo "frontend/ preserved"
```

期望输出:`frontend/ preserved`

- [ ] **Step 7: 列 tmp/ 当前内容(为下一步做差异)**

```bash
ls "tmp/"
```

记录输出(应有 `.gitkeep` 加上若干文件,总计约 130MB)。

- [ ] **Step 8: 清空 `tmp/` 内容但保留 `.gitkeep`**

```bash
find "tmp" -mindepth 1 ! -name '.gitkeep' -exec rm -rf {} +
```

**注意**:用 `-exec rm -rf {} +` 而非 `-delete`,因为 `tmp/` 下可能有子目录(如 7/13 repair 备份目录),`-delete` 在非空目录时会失败且行为不可预测(H3 修复)。

**警告**:此步删除约 130MB 文件(含 122MB 的 `db.sqlite.bak-before-drift-fix`、10+ ad-hoc 测试脚本、dated 报告)。**已在 Task 1 步骤 4 确认 `data/db.sqlite` 健康**。

- [ ] **Step 9: 验证 `tmp/` 清理结果**

```bash
ls -la "tmp/"
```

期望输出:仅 `.gitkeep`(可能还含 0 字节的 `.` 和 `..` 目录项)

---

## Task 5: 更新 `.kb-ai-root/version`

**Files:**
- Modify: `.kb-ai-root/version`(内容 `0.8.2` → `0.8.9`)

**目的:** 与根 `version` 对齐(虽然落后 1 个 patch),让 `scripts/version.ps1` 优先读到合理值。

- [ ] **Step 1: 查看当前内容**

```bash
cat ".kb-ai-root/version"
```

期望输出:`0.8.2`

- [ ] **Step 2: 用 UTF-8 无 BOM 写新值(H1 修复:仅用 PowerShell)**

```powershell
powershell -Command "[System.IO.File]::WriteAllText('E:\.kb-ai-root\version', '0.8.9', [System.Text.UTF8Encoding]::new(\$false))"
```

**注意**:必须用 UTF-8 无 BOM,否则 PowerShell 读时会异常。此处**不能**用 `bash` 的 `echo` 或 `printf`,因为它们会引入 BOM 或末尾换行不一致。

- [ ] **Step 3: 验证内容(无 BOM 字节)(H2 修复:用 od + cat)**

```bash
cat ".kb-ai-root/version"
```

期望输出:`0.8.9`(无多余字符)

```bash
od -A x -t x1z -N 6 ".kb-ai-root/version"
```

期望输出(无 BOM):`30 2e 38 2e 39 0a` 即 ASCII `0.8.9\n`

**不应**有 `ef bb bf` BOM 字节。

**备选方案**:若 `od` 不可用(极少数环境),用 `file .kb-ai-root/version` 看文件类型描述,应显示 `ASCII text` 而非 `UTF-8 Unicode (with BOM) text`。

- [ ] **Step 4: 验证 `version.ps1` 读到新值(可选,需 PS)**

```bash
powershell -File "scripts/version.ps1" 2>&1 | head -1
```

期望输出:`KB-AI v0.8.9 ...`(因 `.kb-ai-root/version` 优先)

---

## Task 6: 代码层修改 — `backup.ps1` + `package.bat`

**Files:**
- Modify: `scripts/backup.ps1:11`(删注释行)
- Modify: `scripts/backup.ps1:135`(改 foreach 数组)
- Modify: `package.bat:67`(加 `docs\releases\` 前缀,用户授权范围内唯一改动)

**目的:** 让备份脚本不再引用已删的 `sessions.db`;让打包脚本能找到新位置的里程碑文档。

- [ ] **Step 1: 改 `scripts/backup.ps1:11`(删注释行)**

**定位该行**:
```bash
grep -n "sessions.db" "scripts/backup.ps1"
```

期望输出包含:`11:      data\sessions.db(遗留库)`

**Before**(line 11):
```powershell
      data\sessions.db(遗留库)
```

**After**(整行删除,无需替换):
```
# (line 11 整行删除)
```

用 Edit 工具的整行删除模式(line 11 整行去掉)。

- [ ] **Step 2: 改 `scripts/backup.ps1:135`(备份循环数组去 `sessions.db`)**

**Before**(line 135):
```powershell
        foreach ($f in @('sessions.db', 'entities.json', 'embedding-cache.jsonl')) {
```

**After**:
```powershell
        foreach ($f in @('entities.json', 'embedding-cache.jsonl')) {
```

- [ ] **Step 3: 验证 `backup.ps1` 改后无 `sessions.db` 引用**

```bash
grep -n "sessions\.db" "scripts/backup.ps1" || echo "no more sessions.db in backup.ps1"
```

期望输出:`no more sessions.db in backup.ps1`

- [ ] **Step 4: 改 `package.bat:67`(加 `docs\releases\` 前缀)**

**Before**(line 67):
```bat
foreach ($f in @('start.bat','stop.bat','docker-compose.yml','QUICKSTART.md','RELEASE-M3.md','RELEASE-M3a.md','RELEASE-M3b.md','package.bat','.env.example','.gitignore')) {
```

**After**:
```bat
foreach ($f in @('start.bat','stop.bat','docker-compose.yml','QUICKSTART.md','docs\releases\RELEASE-M3.md','docs\releases\RELEASE-M3a.md','docs\releases\RELEASE-M3b.md','package.bat','.env.example','.gitignore')) {
```

- [ ] **Step 5: 验证 `package.bat` 改后 diff 范围仅 line 67**

```bash
git diff --stat package.bat
```

期望输出:
```
 package.bat | 2 +-
 1 file changed, 1 insertion(+), 1 deletion(-)
```

`git diff` 应仅在 line 67 这一行内的 3 处文件名加前缀。

- [ ] **Step 6: 验证 `package.bat` 改后引用路径**

```bash
grep "RELEASE-M3" "package.bat"
```

期望输出:3 行,每行均含 `docs\releases\RELEASE-M3*`

- [ ] **Step 7(S7): 验证 `backup.ps1` PowerShell 语法**

```powershell
powershell -NoProfile -Command "[scriptblock]::Create((Get-Content scripts/backup.ps1 -Raw)) | Out-Null; if (-not \$?) { throw 'backup.ps1 syntax error' }; 'backup.ps1 syntax OK'"
```

期望输出:`backup.ps1 syntax OK`

---

## Task 7: 文档层修改 — `AGENTS.md` + `CHANGELOG.md` + `README.md`

**Files:**
- Modify: `AGENTS.md`(§1, §5, §12.2, §13)
- Modify: `CHANGELOG.md`(顶部, line 5)
- Modify: `README.md`(目录树, 版本链接)

**目的:** 让 `AGENTS.md` §1 文件地图与实际文件系统对齐;记录 v0.8.10 变更;让里程碑链接指向新位置。

- [ ] **Step 1: 改 `AGENTS.md §1` 文件地图 — 删 `backend/static/` 行**

定位原文:
```
│   ├── static/               # 内置前端(可选);主前端在 frontend/dist
```

(在 backend/ 树注释块下)

用 Edit 工具删除该行。

- [ ] **Step 2: 改 `AGENTS.md §1` — 删 `docs/quickstart.md` 行**

定位原文(在 docs/ 树注释块下):
```
├── docs/quickstart.md
```

用 Edit 工具删除该行。

- [ ] **Step 3: 改 `AGENTS.md §1` — `RELEASE-M3*` 路径加 `docs/releases/` 前缀**

定位原文中提到 `RELEASE-M3.md` / `RELEASE-M3a.md` / `RELEASE-M3b.md` 的行(在文档索引或树注释块),全部加 `docs/releases/` 前缀。

- [ ] **Step 4: 改 `AGENTS.md §1` — 删 `design-system/MASTER.md*.bak` 提法**

定位并删除任何提到 `MASTER.md.v1.2.bak` / `MASTER.md.v1.3.bak` 的注释行。

- [ ] **Step 5: 改 `AGENTS.md §1` — 删 `design/` 整段**

定位 `design/` 相关的树注释块,整段删除。

- [ ] **Step 6: 改 `AGENTS.md §5 已知偏差表` 第 10 行(前端 React 措辞微调)**

定位原表第 10 行:
```
| 10 | **前端:Dify Web UI → 自建 React 前端**(v0.8.2) | `frontend/dist/` vs `http://localhost:8080` | ✅ start.bat 改开 localhost:8000 |
```

改为:
```
| 10 | **前端:Dify Web UI → 自建 React 前端**(v0.8.2) | `frontend/dist/` vs `http://localhost:8000` | ✅ start.bat 改开 localhost:8000;v0.8.10 删除 `backend/static/` 旧快照后,`frontend/dist/` 成为唯一前端 |
```

- [ ] **Step 7: 改 `AGENTS.md §12.2` 前端实施路径**

定位原 "已应用:`backend/static/index.html`" 行,改写为:
```
**已部署**:由 `backend/main.py` 挂载 `frontend/dist/` 至 :8000;设计真实载体是 `frontend/src/`
```

- [ ] **Step 8: 改 `AGENTS.md §13` 变更记录 — 新增 v0.8.10 行(F1 修复:表格格式)**

§13 实际格式是表格 `| 日期 | 版本 | 描述 |`(实测 line 309-318),**不是**粗体文本。示例:

```markdown
| 2026-07-17 | v0.8.9 | start.bat 补 MinerU 探测;stop.bat 补 MinerU 关闭 |
| 2026-07-17 | v0.8.8 | 感知性能 UX:ThinkingStatus 组件 |
| 2026-07-17 | v0.8.7 | 性能优化:流式输出/health 缓存/reranker 截断 |
```

定位 §13 表格末尾(在 v0.8.9 行后),新增一行:

```markdown
| 2026-07-20 | v0.8.10 | 目录与结构整理(单 commit,无功能变更):删 9 临时 + 6 重复;迁 3 里程碑至 docs/releases/;同步 backup.ps1:11,135 + package.bat:67;同步 AGENTS.md / CHANGELOG.md / README.md;版本号 0.8.9 → 0.8.10;详见 docs/superpowers/specs/2026-07-20-directory-cleanup-design.md |
```

- [ ] **Step 9: 改 `CHANGELOG.md` — `RELEASE-M3*` 路径加 `docs/releases/` 前缀(F2 修复:覆盖 2 处,实测 line 5 + line 113)**

**先定位实际行号(S4)**:
```bash
grep -n "RELEASE-M3" CHANGELOG.md
```

实测命中 2 行(line 5 + line 113),两处都需改。

**改动 1**(line 5 引用块):
定位原文:
```
> v0.7.0 之前的里程碑细节见 `RELEASE-M3.md` / `RELEASE-M3a.md` / `RELEASE-M3b.md`。
```

改为:
```
> v0.7.0 之前的里程碑细节见 `docs/releases/RELEASE-M3.md` / `docs/releases/RELEASE-M3a.md` / `docs/releases/RELEASE-M3b.md`。
```

**改动 2**(line 113 二级标题引用):
定位原文:
```
### 新增(M1-M3d 阶段收官,详见 `RELEASE-M3.md`)
```

改为:
```
### 新增(M1-M3d 阶段收官,详见 `docs/releases/RELEASE-M3.md`)
```

- [ ] **Step 10: 改 `CHANGELOG.md` 顶部 — 新增 v0.8.10 段**

在文件最顶部(在 "格式遵循 [Keep a Changelog]..." 注释之后,v0.8.9 段之前)插入:

```markdown
## [0.8.10] - 2026-07-20

### 整理(目录与结构一次性清理,无功能变更)
- **删除 9 个临时/历史项**:`_ubrain_backup_20260709/`、`_trim_agents.py`、`compose.*.tmp`、`skills-lock.json`、根 `.ruff_cache/`、`backend/tests/integration/`(空)、`design-system/MASTER.md.v1.2.bak`+`v1.3.bak`
- **删除 6 个重复/分叉项**:`docs/quickstart.md`、`design/`(自标 DEPRECATED)、`backend/static/`(frontend/dist/ 的 7/14 旧快照)、`data/sessions.db`+`backend/data/sessions.db`(v0.7.2 起统一至 `data/db.sqlite`)、`tmp/` 下 20+ 临时文件(总计约 130MB,含 122MB drift 备份)
- **迁移 3 项**:`RELEASE-M3*.md` → `docs/releases/`
- **代码层同步**:`scripts/backup.ps1:11,135` 移除 `sessions.db` 引用;`package.bat:67` 加 `docs\releases\` 前缀(用户授权)
- **文档层同步**:`AGENTS.md` §1/§5/§12.2/§13、`CHANGELOG.md` (本段)、`README.md` 目录树与版本链接
- **更新**:`.kb-ai-root/version` 0.8.2 → 0.8.9
- **版本号**:根 `version` 文件 0.8.9 → 0.8.10
- **不修改**:`backend/main.py`(挂载点现状正确)、`scripts/run-checks.ps1`(4 步仍适用)
- **验证**:见 docs/superpowers/specs/2026-07-20-directory-cleanup-design.md §6

```

- [ ] **Step 11: 改 `README.md` 目录树 — 验证无 `backend/static/` 行**

先验证 README.md 的目录树节无 `backend/static/` 行(spec 误以为有,实际 README.md 目录树只有 `backend/` 与 `frontend/`,不展开子目录):

```bash
grep -n "backend/static" "README.md" || echo "no backend/static/ line in README.md"
```

期望输出:`no backend/static/ line in README.md`

**注**:spec §5.3 此处有误(假设 README 目录树包含 `backend/static/` 行,实际并不展开 backend 子目录)。如果 grep 有意外命中,删除该行;否则无需修改。

- [ ] **Step 12: 改 `README.md` 版本与变更节 — 链接加 `docs/releases/` 前缀**

定位原文:
```
- **变更记录**:[CHANGELOG.md](CHANGELOG.md)(Keep a Changelog 格式);M3 及更早的里程碑见 `RELEASE-M3*.md`。
```

改为:
```
- **变更记录**:[CHANGELOG.md](CHANGELOG.md)(Keep a Changelog 格式);M3 及更早的里程碑见 [`docs/releases/RELEASE-M3*.md`](docs/releases/)。
```

- [ ] **Step 13: 验证文档内链全部指向新位置(S5 扩展验证)**

```bash
grep -rn "RELEASE-M3\|docs/quickstart\.md\|backend/static/\|MASTER\.md\.v[12]\.bak\|sessions\.db\|^frontend/dist" \
  AGENTS.md CHANGELOG.md README.md QUICKSTART.md docs/ 2>/dev/null
```

期望输出:
- `RELEASE-M3` 命中:均在 `docs/releases/RELEASE-M3*` 或 `docs/superpowers/specs/` 路径下
- `docs/quickstart.md`:零结果
- `backend/static/`:仅 spec 文件本身命中
- `MASTER.md.v[12].bak`:零结果
- `sessions.db`:仅在历史/legacy 文档中命中(见 Task 9 Step 10 详述)
- `frontend/dist`:在 README/AGENTS.md 中**应保留**(不再指向 backend/static,而是作为唯一前端)

---

## Task 8: 升根 `version` 文件

**Files:**
- Modify: `version`(根目录,内容 `0.8.9` → `0.8.10`)

**目的:** 触发 `backend/main.py:_read_version()` 返回新版本号,前端 SSE 也会读到新值。

- [ ] **Step 1: 查看当前内容**

```bash
cat "version"
```

期望输出:`0.8.9`

- [ ] **Step 2: 用 UTF-8 无 BOM 写新值(H1 修复:仅用 PowerShell)**

```powershell
powershell -Command "[System.IO.File]::WriteAllText('E:\version', '0.8.10', [System.Text.UTF8Encoding]::new(\$false))"
```

**注意**:此处**不能**用 `bash` 的 `echo` 或 `printf`,因为它们会引入 BOM 或末尾换行不一致。

- [ ] **Step 3: 验证内容(无 BOM 字节)(H2 修复:用 od + cat)**

```bash
cat "version"
```

期望输出:`0.8.10`(无多余字符)

```bash
od -A x -t x1z -N 7 "version"
```

期望输出(无 BOM):`30 2e 38 2e 31 30 0a` 即 ASCII `0.8.10\n`

**不应**有 `ef bb bf` BOM 字节。

- [ ] **Step 4: 验证 `backend/main.py:_read_version()` 逻辑(可选,需跑后端)**

```bash
# 模拟 _read_version 行为(S8 修复:显式 cd E:/ 确保路径正确)
cd E:/ && python -c "from pathlib import Path; v = Path('version').read_text(encoding='utf-8').strip(); print(f'read version: {v!r}')"
```

期望输出:`read version: '0.8.10'`

---

## Task 9: 全量验证(§6 14 项)

**Files:**
- 不修改文件,只跑验证

**目的:** 在 commit 前确保所有动作正确,任一失败则停止并诊断。

- [ ] **Step 1: 验证 #1 — 启动链路(需 Docker,本步可在 commit 后再跑,或跳过)**

(留待 commit 后实际启动验证,本次 plan 不阻塞)

- [ ] **Step 2: 验证 #2 — API 端点(需后端在跑,跳过)**

(留待 commit 后再跑)

- [ ] **Step 3: 验证 #3 — 后端单测**

```bash
cd E:/
backend/.venv/Scripts/python -m pytest tests/unit/ -q
```

期望输出:全过(若 venv 未建,见 `scripts/start-backend.ps1` 先建)

- [ ] **Step 4: 验证 #4 — 后端 ruff 静态检查**

```bash
cd E:/
backend/.venv/Scripts/python -m ruff check --config backend/ruff.toml backend/ tests/unit/ tests/integration/api/
```

期望输出:`All checks passed!`

- [ ] **Step 5: 验证 #5 — 4 步 run-checks(需 npm + frontend/node_modules)**

```bash
cd E:/
powershell -File scripts/run-checks.ps1
```

期望输出:[1/4] ruff + [2/4] pytest + [3/4] eslint + [4/4] build 全部 PASS

**注**:因 `frontend/` 保留(Global Constraints 第 20 行),eslint + build 步骤仍适用。若 reviewer 质疑"为何保留 4 步",指向反转决策 P0 grep 实据。

- [ ] **Step 6: 验证 #6 — 备份脚本**

```bash
cd E:/
powershell -File scripts/backup.ps1 -Quiet
```

期望输出:正常完成,zip 不再含 `sessions.db`(可在 zip 内 `unzip -l` 验证)

- [ ] **Step 7: 验证 #7 — 路径脚本**

```bash
cd E:/
powershell -File scripts/get-usb-root.ps1
```

期望输出:E:/(根路径,`.kb-ai-root` 哨兵仍生效)

- [ ] **Step 8: 验证 #8 — 版本号**

```bash
cd E:/
powershell -File scripts/version.ps1
```

期望输出:`KB-AI v0.8.9 ...`(因 `.kb-ai-root/version` 优先,这是预期的)

- [ ] **Step 9: 验证 #9 — 文档内链(S5 扩展)**

```bash
cd E:/
grep -rn "RELEASE-M3\|docs/quickstart\.md\|backend/static/\|MASTER\.md\.v[12]\.bak\|sessions\.db\|^frontend/dist" \
  AGENTS.md CHANGELOG.md README.md QUICKSTART.md docs/ 2>/dev/null
```

期望输出:
- `RELEASE-M3` 命中:仅 `docs/releases/RELEASE-M3*` 与 `docs/superpowers/specs/` 内
- `docs/quickstart.md`、`MASTER.md.v[12].bak`:零结果
- `backend/static/`:仅 spec 文件本身命中
- `sessions.db`:仅在历史/legacy 文档中(同 Step 10)
- `frontend/dist`:在 README/AGENTS.md 中**应保留**

- [ ] **Step 10: 验证 #10 — `sessions.db` 残留扫描(H3)**

```bash
cd E:/
grep -rn "sessions\.db" backend/ scripts/ docker-compose.yml start.bat stop.bat package.bat \
  AGENTS.md CHANGELOG.md README.md QUICKSTART.md docs/ 2>/dev/null
```

期望输出:仅命中 `chat.ps1`、`test_m2b.ps1`、`frontend-design-brief.md`、`m2-usage.md`、`Invoke-SqliteExec.ps1:26`(docstring)、`backend/api/sessions.py:1` 与 `backend/core/sqlite.py:1`(docstring)、`tests/integration/README.md:81`。

**不应**在 `backend/main.py`、`backend/api/*.py` 实际函数体、`scripts/backup.ps1`(改后)看到。

- [ ] **Step 11: 验证 #11 — `frontend/` 仍存在**

```bash
test -f "frontend/dist/index.html" && \
test -d "frontend/src" && \
test -f "frontend/package.json" && \
echo "frontend/ preserved"
```

期望输出:`frontend/ preserved`

- [ ] **Step 12: 验证 #12 — `backend/static/` 已删**

```bash
test ! -d "backend/static" && echo "backend/static/ removed"
```

期望输出:`backend/static/ removed`

- [ ] **Step 13: 验证 #13 — `.gitignore` 完整性**

```bash
cd E:/
git status --short
```

期望输出:
- 5 个 untracked:`?? data/.gitkeep`, `?? vectors/.gitkeep`, `?? cache/.gitkeep`, `?? logs/.gitkeep`, `?? tmp/.gitkeep`
- 不应有大文件被误跟踪

- [ ] **Step 14: 验证 #14 — `package.bat` diff 范围(S2)**

```bash
cd E:/
git diff --stat package.bat
git diff package.bat
```

期望输出:`git diff` 仅在 line 67 内的 3 处加 `docs\releases\` 前缀,**不应**有其他行变更。

**注(S9)**:`git diff` 默认显示前后各 3 行 context,所以输出会含 line 64-70 左右的内容,但 `+`/`-` 行**仅**在 line 67。若看到其他行也有 `+`/`-`,说明改越界了,立即停止。

---

## Task 10: 单 commit 收尾

**Files:**
- 全部前述变更一次性 commit

**目的:** 按 spec §7,所有变更在一个 commit 内。

- [ ] **Step 1: 确认 `git status` 状态符合预期**

```bash
cd E:/
git status
```

期望看到:
- 9 个 deleted(`_ubrain_backup_20260709/`, `_trim_agents.py`, `compose.err.tmp`, `compose.out.tmp`, `skills-lock.json`, `.ruff_cache/`, `backend/tests/integration/`, `design-system/MASTER.md.v1.2.bak`, `design-system/MASTER.md.v1.3.bak`)
- 6 个 deleted(`docs/quickstart.md`, `design/`, `backend/static/`, `data/sessions.db`, `backend/data/sessions.db`, `tmp/*` 多个)
- 3 个 renamed(`RELEASE-M3.md` / `M3a.md` / `M3b.md` → `docs/releases/...`)
- 5 个 untracked(`data/.gitkeep`, `vectors/.gitkeep`, `cache/.gitkeep`, `logs/.gitkeep`, `tmp/.gitkeep`)
- 7 个 modified(H4 修复:计数与列举对齐):
  - 2 个代码脚本:`scripts/backup.ps1`, `package.bat`
  - 3 个文档:`AGENTS.md`, `CHANGELOG.md`, `README.md`
  - 2 个版本文件:`version`, `.kb-ai-root/version`

- [ ] **Step 2: 暂存所有变更**

```bash
cd E:/
git add -A
git status --short
```

期望看到:所有上述项移到 staged 区域(staged: A/M/D/R/?? 标)

- [ ] **Step 3: 单 commit(spec §7 要求的单一 commit)**

```bash
cd E:/
git commit -m "chore(structure): v0.8.10 目录与结构整理

- 删除 9 个临时/历史项 + 6 个重复/分叉项
- 迁移 3 个里程碑文档至 docs/releases/
- 同步 backup.ps1 / package.bat
- 同步 AGENTS.md / CHANGELOG.md / README.md
- 版本号 0.8.9 → 0.8.10
- 详见 docs/superpowers/specs/2026-07-20-directory-cleanup-design.md"
```

- [ ] **Step 4: 验证 commit 内容**

```bash
cd E:/
git log -1 --stat | head -50
```

期望:看到 commit message 与所有变更文件列表

- [ ] **Step 5: 验证工作区干净**

```bash
cd E:/
git status
```

期望输出:`nothing to commit, working tree clean`

- [ ] **Step 6: 启动后端(可选,完整启动验证)**

```bash
cd E:/
start.bat
```

期望:双击后所有 8 步通过,浏览器打开 :8000 看到 React SPA + XAIAgent 设计

---

## 回退预案

任何 task 失败时:

```bash
cd E:/
git reset --hard HEAD~1
```

即可回退 commit(若已 commit)或丢弃 working tree 变更(若未 commit)。

**注意**:`git reset --hard` 不会恢复未追踪的新文件;但本计划没有需要新建的非 `.gitkeep` 文件(`.gitkeep` 是空文件,丢了再 `touch` 即可),所以是安全的。

---

## 实施后状态

完成后:

| 路径 | 状态 |
|---|---|
| `frontend/` | ✅ 保留(src + dist + node_modules + 配置) |
| `backend/static/` | ❌ 删除(7/14 旧快照) |
| `docs/releases/` | ✅ 新建(3 个里程碑) |
| `docs/quickstart.md` | ❌ 删除 |
| `design/` | ❌ 删除 |
| `data/sessions.db` | ❌ 删除 |
| `backend/data/sessions.db` | ❌ 删除 |
| `tmp/` 内容 | ❌ 清空(留 `.gitkeep`) |
| `_ubrain_backup_20260709/` | ❌ 删除 |
| `_trim_agents.py` | ❌ 删除 |
| `compose.*.tmp` | ❌ 删除 |
| `skills-lock.json` | ❌ 删除 |
| `.ruff_cache/`(根) | ❌ 删除 |
| `backend/tests/integration/` | ❌ 删除(空) |
| `design-system/MASTER.md*.bak` | ❌ 删除(2 份) |
| `version`(根) | `0.8.9` → `0.8.10` |
| `.kb-ai-root/version` | `0.8.2` → `0.8.9` |
| `package.bat:67` | 3 个路径加 `docs\releases\` 前缀 |
| `scripts/backup.ps1:11,135` | 移除 `sessions.db` 引用 |
| `AGENTS.md` §1/§5/§12.2/§13 | 同步 |
| `CHANGELOG.md` 顶部 + line 5 | 同步 |
| `README.md` 目录树 + 链接 | 同步 |
| 5 个 `.gitkeep` | ✅ 新建 |
