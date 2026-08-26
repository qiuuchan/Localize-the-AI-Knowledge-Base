# KB-AI · Git Hooks (v1.3.0)

## 概览

| Hook | 触发时机 | 跑什么 | 阻塞? |
|---|---|---|---|
| `pre-commit` | `git commit` | `ruff check backend/ tests/` | ✗ 失败 abort |
| `pre-push` | `git push` | `scripts/run-checks.ps1`(ruff + pytest + eslint + vite build) | ✗ 失败 abort |

## 安装

```powershell
pwsh -File scripts/install-hooks.ps1
```

安装器会执行 `git config core.hooksPath scripts/hooks`,把仓库 hooks 路径指向本目录。
新克隆后只需执行一次。

## 卸载

```powershell
pwsh -File scripts/install-hooks.ps1 -Uninstall
```

## 降级

`pwsh`(PowerShell 7+)不在 PATH 时,`pre-push` 输出警告 + exit 0(可推送但未跑全检)。
这种情况下手动 `powershell -File scripts/run-checks.ps1` 验证。

## 不覆盖什么

- 不扫 `scripts/` 顶层 .ps1(ruff 不支持 PS)
- 不扫 `scripts/hooks/*.bash`(bash,不是 ruff 目标)
- 不跑 pytest / eslint / vite 在 pre-commit(慢,留给 pre-push)