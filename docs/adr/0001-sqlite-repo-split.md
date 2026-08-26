# ADR-0001 · KB-AI sqlite 层 5-repo 拆分

| | |
|---|---|
| **状态** | Accepted |
| **日期** | 2026-07-22 |
| **驱动版本** | KB-AI v1.3.0 |
| **配套 spec** | `docs/superpowers/specs/2026-07-21-v1.3-ops-hardening-design.md`(运维加固) |
| **决策工具** | `grilling` skill + `improve-codebase-architecture` skill |
| **影响文件** | `backend/core/sqlite.py`(删)→ `backend/core/sqlite/`(新包,7 文件)+ `backend/core/rag/keyword_index.py`(改)+ 7 个 backend api 文件(改 import)+ 2 个 tests 文件(改 import)+ 1 个新测试文件 |

---

## Context

`backend/core/sqlite.py` 长到 **1064 行**,承载 **8 张表 + ~40 个公开函数** 的 CRUD + schema migration + 跨表逻辑。表面是一个模块,实际是 **5 个独立表组** 的拼凑:

| 表组 | 函数数 | 行数(估) |
|---|---|---|
| sessions + messages | 4 + 3 | ~140 |
| degradation_events | 3 | ~95 |
| databases + processing_state | 6 + 4 + 2 跨表 | ~340 |
| keyword_index | 0(CRUD 在 `core/rag/keyword_index.py`) | 0 + ~30 行 CREATE |
| tags + doc_tags | 10 | ~150 |
| + connection + orchestrator | 2 | ~190 |

**核心问题**:
1. **god 模块**:`interface ≈ implementation`,改一处 SQL 必须横扫整文件,夹具测试要 mock 整个 sqlite 模块
2. **schema 跨包裂缝**:`keyword_index` 表的 CREATE 在 `sqlite.py`,CRUD 在 `rag/keyword_index.py`,改 schema 时易漏同步
3. **跨表非原子**:`delete_database(cascade=True)` 先 DELETE `databases` commit,再 DELETE `keyword_index` commit —— 中途崩溃留脏状态
4. **boot.py 文案硬编码版本**:`schema_migration` 阶段文案写死"应用 v1.1.0 schema migration (tags/doc_tags)",v1.3.0 加 cost_alert 表时不知如何扩展

**驱动因素**:
- v1.3.0 spec §2.4 加 `cost_log` 表时,不希望把 SQLite 表再加进 1064 行 god 模块
- v1.4 batch-upload(REQ-12)+ v1.5 P2 REQ-15 多用户隔离 都将加新表,需要 seam
- 现有 252 pytest 不应该因为这次重构改动一行

---

## Decision

### 1. 模块拆分:5 个独立 repo

把 `backend/core/sqlite.py` 拆为 `backend/core/sqlite/` 包,内含 5 个 repo:

```
backend/core/sqlite/
├── __init__.py             # orchestrator: init_db + 3 步拆分 + 临时 re-export (PR #1)
├── connection.py           # get_connection + transaction() + optional_conn() + commit_and_close_if_owned()
├── sessions_repo.py        # list_sessions / get_session / create_session / touch_session
├── messages_repo.py        # get_messages / count_messages / save_message
├── degradation_repo.py     # save_degradation_event / list_degradation_events / degradation_summary_by_component
├── databases_repo.py       # list/get/create/update/delete/count_documents/bulk_assign + processing_state 的 upsert/finish/list_orphan/recover_orphans
└── tags_repo.py            # tag CRUD (create/list/get/update/delete) + doc_tags CRUD (assign/unassign/list_for_doc/list_documents_by_tags)
```

每个 repo 导出两个固定入口:
- `init_schema(db_path=None)` —— 该 repo 名下所有表的 `CREATE TABLE IF NOT EXISTS`
- `migrate(db_path=None)` —— 该 repo 名下所有表的 `ALTER TABLE`(try/except duplicate column 幂等)

CRUD 函数签名:`def X(..., *, conn: sqlite3.Connection | None = None)` —— `conn=None` 时自管 conn,非 None 时用调用方提供的 conn。

### 2. keyword_index 表的 schema 归属 → `core/rag/keyword_index.py`

`CREATE TABLE keyword_index` 从 `sqlite/init_db` 移到 `rag/keyword_index.init_schema()`。`sqlite/init_db_core` 通过显式 import 调用之。

**Seam 变化**:
- 旧:`databases_repo.delete_database(cascade=True)` 内裸 SQL `DELETE FROM keyword_index ...`
- 新:`databases_repo.delete_database(cascade=True, conn=conn)` 内调 `rag.keyword_index.delete_by_db_prefix(db_id, conn=conn)`

`bulk_assign_documents_to_database` 同理改成调 `rag.keyword_index.rewrite_source_prefix(...)`。

`core/rag/keyword_index.py` 必须保持**不依赖 `core/sqlite`**(用 `get_db_path` + `import sqlite3` 直接管理 conn),避免循环依赖。

### 3. 跨表原子性:`transaction()` context manager

`connection.py` 加:
```python
@contextmanager
def transaction(db_path: Optional[Path] = None) -> Iterator[sqlite3.Connection]:
    conn = get_connection(db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
```

跨 repo 写操作显式 `with transaction() as conn:` 包住,内部调用 repo 函数传 `conn=conn`。**修 `delete_database(cascade=True)` 的已知非原子 bug**。

单 repo 单表写操作**保持现状**(`get_connection() → commit() → close()`),不强制套 `transaction()`。

### 4. conn injection helper:`optional_conn()` + `commit_and_close_if_owned()`

`connection.py` 加 helper,收敛每个 repo 函数的 conn 管理样板:
```python
def optional_conn(conn: Connection | None) -> tuple[Connection, bool]:
    """Return (conn, owns_conn). owns_conn=True means caller should close."""
    if conn is not None:
        return conn, False
    return get_connection(), True

def commit_and_close_if_owned(conn: Connection, owns: bool) -> None:
    try:
        conn.commit()
    finally:
        if owns:
            conn.close()
```

每个 repo 函数 boilerplate 降到 ~3 行 + 1 个 try/finally。

### 5. `init_db` 拆 3 步

`backend/core/sqlite/__init__.py`:
```python
_REPOS = [
    sessions_repo, messages_repo, degradation_repo,
    databases_repo, tags_repo,
]

def init_db(db_path=None) -> None:
    """Orchestrator:core DDL → per-repo migrate → default row."""
    init_db_core(db_path)
    init_db_migrate(db_path)
    init_db_post(db_path)

def init_db_core(db_path=None) -> None:
    for repo in _REPOS:
        repo.init_schema(db_path)
    rag.keyword_index.init_schema(db_path)  # Q1 决策:keyword_index schema 归 rag 层

def init_db_migrate(db_path=None) -> None:
    for repo in _REPOS:
        repo.migrate(db_path)
    # rag.keyword_index 当前无 ALTER(只 init_schema);未来有 ALTER 时也在这里调

def init_db_post(db_path=None) -> None:
    databases_repo.ensure_default_database(db_path)
```

`boot.py:189-206` 当前调 `init_db()` 一次;**不需要改** —— 这次拆分对 boot.py 是零行为变更。后续如需细粒度 SSE 进度,改调 3 步即可。

### 6. 测试策略:5 个精准测

新文件 `tests/unit/test_sqlite_refactor.py`(~80 行):

| 测 | 验证 |
|---|---|
| `test_transaction_commit_on_success` | commit 路径 |
| `test_transaction_rollback_on_exception` | rollback 路径(显式 raise) |
| `test_delete_database_cascade_atomicity` | 模拟 `rag.keyword_index.delete_by_db_prefix` 抛异常,验证 `databases` 表行**还在** |
| `test_keyword_index_delete_by_db_prefix` | 新公开函数行为 |
| `test_init_db_three_steps_idempotent` | init_db_core / init_db_migrate / init_db_post 各跑两次不报错 |

共享 `tmp_db_path` fixture,~20 行代码。

### 7. PR 边界:双 PR

- **PR #1**:结构拆分 + transaction + init_db 3 步 + rag.keyword_index 改动 + 新测试 + 临时 re-export shim(保持 12 调用点零改)。~12 文件变更。
- **PR #2**:12 个调用点从 `from backend.core.sqlite import X` 改写为 `from backend.core.sqlite.X_repo import X`,删 `__init__.py` 的 re-exports。~10 文件变更。

PR #1 是"行为不变重构",CHANGELOG v1.3.0 段写"内部重构,零行为变更"。
PR #2 是"清理",CHANGELOG v1.3.0 段写"清理 import 路径"。
两个 PR 都在 v1.3.0 release commit 前合并。

---

## Consequences

### 正面

- **locality 提升**:改 tag 表只动 `tags_repo.py`;改 keyword_index schema 只动 `rag/keyword_index.py`
- **测试隔离**:mock 范围从 1064 行降到目标 repo 行数;现有 252 测不变
- **原子性修复**:`delete_database(cascade=True)` 中途崩溃不再留脏状态(v1.1.0 PR#1 cascade 设计的本意)
- **schema-CRD 同模块**:`keyword_index` 改 schema 不再跨包同步
- **seam 显式化**:`delete_database` 不再写裸 SQL,而是调 `rag.keyword_index.delete_by_db_prefix(...)` —— 跨包依赖变成命名 API
- **v1.3.0 cost_repo seam**:cost_log 表自然落在新结构(届时再加 `cost_repo.py` + 在 `_REPOS` 列表加一项)
- **未来 P2 友好**:REQ-15 多用户隔离、REQ-12 conversation search、REQ-14 video understanding 都将加新表,每张表有自己的 repo

### 负面

- **boot.py 一次回滚**:12 调用点中任何一个 `import` 出错会阻断 `init_db()`;必须确保 PR #1 re-export 完整
- **`recover_orphans` 实施时需手动套 `transaction()` 模式**:跨 `processing_state` + `degradation_events` 两表写,迁移到 `databases_repo` 后必须用 `with transaction() as conn:` 包住
- **`bulk_assign_documents_to_database` 同样**:跨 `databases` + `keyword_index` 两表写,改用 `rag.keyword_index.rewrite_source_prefix(..., conn=conn)`
- **PR #1 临时 shim 是中间状态**:PR #2 必须立刻清掉,否则变成"永久维护"
- **函数签名带 `conn=None` 参数**:~30 个 repo 函数多 1 行 boilerplate(虽然 `optional_conn()` helper 收敛到 ~3 行,但调用方看到的是 `def X(..., *, conn=None)`)

### 中性

- **接口文件数从 1 增到 7**:开发者查"X 函数在哪"时,需要知道它在哪个 repo(命名约定 `_repo.py` 后缀)
- **执行时间持平**:拆包不引入运行时开销,Python import 路径略长但无 IO 差异
- **文档分散**:CHANGELOG v1.3.0 段需引用 ADR-0001 + 配套 spec,verifier 跳转路径变长

---

## Alternatives Considered

### Q1 · keyword_index schema 归属

| 选项 | 描述 | 否决理由 |
|---|---|---|
| A | 留在 `core/sqlite/keyword_repo.py`,维持现状(只 CREATE,CRUD 在 rag 层) | schema-CRD split 持续;seam 漏洞(`delete_database` 裸 SQL)留着 |
| **B ✓** | 移到 `core/rag/keyword_index.py`,schema + CRUD 同模块 | 表与代码同包,locality 最高;`core/sqlite` interface 收缩 |
| C | `core/sqlite/keyword_repo.py` 抽薄 CRUD wrapper,读留 rag 写走 sqlite | 三处 split,下次加列要改 3 处 |

### Q2 · sessions vs messages 合并还是拆开

| 选项 | 描述 | 否决理由 |
|---|---|---|
| A | 合并为 `chat_repo.py`(sessions + messages) | `count_messages`(SSE soft_warning 热路径)被冷路径代码包围,locality 差 |
| **B ✓** | 拆成 `sessions_repo.py` + `messages_repo.py` | FK 在 DB 层,Python 不需耦合;测试隔离自然成立;hot/cold 路径分开 |

### Q3 · 跨表操作原子性

| 选项 | 描述 | 否决理由 |
|---|---|---|
| A | 维持现状(每函数自管 conn + 单独 commit) | 已知非原子 bug(`delete_database` cascade 中途崩溃)留着 |
| **B ✓** | 提供 `transaction()` context manager | 95% 调用点不变,跨 repo 显式 `with transaction()`;修已知 bug |
| C | 全部 repo 函数改 signature 接 `conn: Connection` | 强制 route 层懂 conn 管理,推得太远 |

### Q4 · init_db 与 boot.py schema_migration 契约

| 选项 | 描述 | 否决理由 |
|---|---|---|
| A | 单 `init_db()` 函数 | boot.py 文案硬编码版本,加新表时不知如何扩展 |
| **B ✓** | 拆 3 步:`init_db_core / init_db_migrate / init_db_post` | 与 boot.py SSE 阶段契合;v1.3.0 加 cost_log 只需 `init_db_migrate` 多一步 |
| C | 引入 migrations 表 + 版本号 | 远超 v1.3.0 scope;是 v1.4+ 任务(到时把每个 `init_db_migrate_xxx` 转成 `(version, up_sql)` 记录) |

### Q5 · re-export 兼容层去留

| 选项 | 描述 | 否决理由 |
|---|---|---|
| A | 永久 re-export shim | 永久 sync 成本;v1.3.0 后没人用旧 import,但 shim 还要维护 |
| B | 临时 shim + deprecation warning | 个人项目 warning 是噪音;没人按 warning 主动迁移 |
| **C ✓** | 一次性切换,无 shim(PR #2 完成) | 12 调用点一次改写;`__init__.py` 只剩 orchestrator |

### Q6 · repo 函数 conn 管理模式

| 选项 | 描述 | 否决理由 |
|---|---|---|
| **A ✓** | 所有函数接受 `conn: Connection \| None = None` + helper | 现状调用点零改;跨 repo 显式 `with transaction() as conn:`;接口一致 |
| B | 两套 API:top-level 自管,low-level 接 conn | 每个函数 ×2 = 函数数量翻倍,维护负担显著 |
| C | 强制 DI,每个函数接 conn | route 层(`/api/knowledge` 等)不该懂 conn 管理,推得太远 |

### Q7 · 测试策略

| 选项 | 描述 | 否决理由 |
|---|---|---|
| A | 全覆盖 4 类新行为,~15 新测 | 边际效用低;`init_db_migrate` 在每个 repo 上的行为是原 ALTER 搬迁,旧测试覆盖 |
| **B ✓** | 5 个精准测(transaction + cascade + delete_by_db_prefix + 3-step idempotent) | 精准打新风险点;fixture 共享 ~80 行 |
| C | 只测 init_db 集成 | `transaction()` 单独行为无测试,新基础设施必须有 rollback 断言 |
| D | 不加测试,依赖 252 测 | 改了 conn 管理语义,没有回归网;v1.3.0 cost_repo 落地时无 baseline |

### Q8 · PR 边界

| 选项 | 描述 | 否决理由 |
|---|---|---|
| A | 单 PR,~18 文件 | PR 体积大,reviewer 疲劳;关键风险(transaction rollback)被淹没在 mechanical diff |
| **B ✓** | 双 PR(结构+transaction / 调用方迁移+删 shim) | PR #1 是"行为不变重构",零用户感知;PR #2 是清理;rebase 干净 |
| C | 三 PR(纯搬结构 / 加基础设施 / 改调用方+清 shim) | PR #2 进行中,撞上其他 PR 会处理"新结构+旧签名"混乱 |

---

## Open Questions(实施时定,不阻塞本 ADR)

1. **`recover_orphans()` 具体归属**:`databases_repo.py` 内 vs 独立 `lifecycle.py`?
   - 倾向:留在 `databases_repo.py`(已有 `processing_state` 相关代码)
   - 实施要求:必须用 `with transaction() as conn:` 包住,UPDATE `processing_state` + INSERT `degradation_events` 原子
2. **`bulk_assign_documents_to_database` 是否拆为独立模块**?
   - 倾向:留在 `databases_repo.py`(只是改写为调 `rag.keyword_index.rewrite_source_prefix(...)`,逻辑不复杂)
3. **`init_db_post` 后续是否扩**?v1.3.0 cost_log 加进来时,`init_db_migrate` 加 cost_log 的 schema,`init_db_post` 是否要 cost_repo 默认行?(目前没有"cost_log 默认行"概念,倾向不加)

---

## References

- **Spec**:`E:/docs/superpowers/specs/2026-07-21-v1.3-ops-hardening-design.md` §2.4(cost-alert 数据流提到 `atomic_append_jsonl` 借用 `core/atomic_io.py` 模式,本 ADR 是该模式在 DB 层的对偶)
- **架构报告**:用户私有 `<private>/architecture-validation-report.md` Part 2 §9(改进 TODO 索引,本 ADR 与 #5 "scripts 平铺"教训同源)
- **AGENTS.md**:§3 #5 "Get-EnvVar 用 lib/ 公共库"—— 本 ADR 是该原则在 DB 层的实践
- **历史教训**:v0.8.11 P1.3 借鉴 Yuxi-Know `base.py:524-555` 抽 `atomic_io.py`(治 FMEA F11/F13),本 ADR 是同源思路在 sqlite 层的延伸
- **Skill 来源**:`improve-codebase-architecture` skill 建议 sqlite.py 是高密度 god 模块;`grilling` skill 走 8 轮决策树
- **ADR 模板**:MADR(Markdown Architectural Decision Records)风格

---

*本 ADR 是 KB-AI 第一篇 ADR。后续 v1.4 / v1.5 / P2 决策追加 `0002-...` `0003-...` 等。*