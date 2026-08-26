<#
.SYNOPSIS
  KB-AI · SQLite via Python 子进程封装(v0.7.1 从 chat.ps1:139-209 抽离)

.DESCRIPTION
  ### 职责
    提供一个统一入口让 PowerShell 调用 SQLite,通过临时 .py 子进程走 stdio JSON 协议。
    避免每个用到 SQLite 的脚本重复实现 Python sqlite3 + JSON 编码的样板代码。
    替代方案(原生 PS 6+ System.Data.SQLite)未采用,原因是:
    - 保持 PS 5.1 兼容(M1 锁版)
    - parse-doc.ps1 已依赖 python,基础设施已就位

  ### 协议
    stdin (JSON): {db, sql, params}
    stdout (JSON):
      - SELECT: [{col1: val, col2: val, ...}, ...]
      - INSERT/UPDATE/DELETE: {affected: N}
    stderr: PYERR: <repr(exc)>

  ### 函数清单
    - Invoke-SqliteExec :统一 SQLite 调用入口
    - $SqliteHelper     :Python 内嵌脚本(模块级,首次调用生成临时 .py)

  ### 用法
    . (Join-Path $PSScriptRoot 'lib/Invoke-SqliteExec.ps1')
    $rows = Invoke-SqliteExec -DbPath "<private>\KB-AI\data\sessions.db" `
                              -Sql "SELECT * FROM sessions WHERE session_id = ?" `
                              -Params @($sessionId)

.NOTES
  PowerShell 5.1 兼容。
  P0 修复:ConvertTo-Json 把 1-元素数组 unwrap 成标量导致 sqlite3 绑定失败,
  已用 ArrayList 强制数组语义。
#>

$ErrorActionPreference = "Stop"

# ----------------------------------------------------------------------
# Python helper script (模块级常量,首次调用写临时文件)
# ----------------------------------------------------------------------

$SqliteHelper = @'
import sqlite3, json, sys

# v0.7.2: 支持从文件路径读命令(JSON 文件避免 pipe 编码问题)
# 用法 1: python helper.py <cmd.json> (推荐,避免中文 Windows GBK 乱码)
# 用法 2: python helper.py          (兼容旧 stdin JSON)
if len(sys.argv) > 1:
    with open(sys.argv[1], 'r', encoding='utf-8-sig') as f:
        raw = f.read()
else:
    raw = sys.stdin.read()
if raw and raw[0] == "\ufeff":
    raw = raw[1:]
cmd = json.loads(raw)
db = cmd["db"]
sql = cmd["sql"]
params = cmd.get("params", [])

conn = sqlite3.connect(db)
conn.row_factory = sqlite3.Row
cur = conn.cursor()
try:
    # v0.7.2:支持 executemany(二维 params 数组),用于 keyword_index 批量写入
    if params and isinstance(params, list) and len(params) > 0 and isinstance(params[0], list):
        cur.executemany(sql, params)
    elif sql.strip().upper().startswith("SELECT"):
        cur.execute(sql, params)
    else:
        # DDL/DML 无参数时,若 sqlite3 报"one statement at a time",回退到 executescript
        try:
            cur.execute(sql, params)
        except sqlite3.ProgrammingError as pe:
            if "one statement" in str(pe).lower():
                cur.executescript(sql)
            else:
                raise
    if cur.description:
        cols = [d[0] for d in cur.description]
        rows = []
        for r in cur.fetchall():
            rows.append({c: r[c] for c in cols})
        sys.stdout.write(json.dumps(rows, ensure_ascii=False))
    else:
        conn.commit()
        sys.stdout.write(json.dumps({"affected": cur.rowcount}, ensure_ascii=False))
except Exception as e:
    sys.stderr.write("PYERR: " + repr(e) + "\n")
    sys.exit(1)
finally:
    conn.close()
'@

# ----------------------------------------------------------------------
# 函数:Invoke-SqliteExec
# ----------------------------------------------------------------------

function Invoke-SqliteExec {
    <#
    .SYNOPSIS
      统一 SQLite 调用入口(走 Python 子进程 + stdio JSON)。
    .PARAMETER DbPath
      SQLite 数据库文件绝对路径。
    .PARAMETER Sql
      SQL 语句,参数用 ? 占位。
    .PARAMETER Params
      SQL 参数数组(顺序与 ? 一一对应)。
    .OUTPUTS
      - SELECT: PSCustomObject 数组(或 $null)
      - INSERT/UPDATE/DELETE: PSCustomObject {affected: N}
      - 失败 throw
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)] [string]$DbPath,
        [Parameter(Mandatory = $true)] [string]$Sql,
        [object[]]$Params = @()
    )
    # v0.7.2: 探测可用的 Python 解释器(python 优先,失败则回退 py -3)
    # 某些 Windows 环境 python 是 Windows Store stub,返回 9009,py -3 反而可用
    $pythonExe = $null
    $pythonArgs = @()
    $probe = & python -c "print('OK')" 2>&1
    if ($LASTEXITCODE -eq 0 -and $probe -eq "OK") {
        $pythonExe = "python"
    } else {
        $probe = & py -3 -c "print('OK')" 2>&1
        if ($LASTEXITCODE -eq 0 -and $probe -eq "OK") {
            $pythonExe = "py"
            $pythonArgs = @("-3")
        }
    }
    if (-not $pythonExe) {
        throw "python/py 未安装;SQLite 操作需要 python(已在 parse-doc.ps1 文档列为依赖)"
    }
    $tmp = [System.IO.Path]::Combine([System.IO.Path]::GetTempPath(), "kb_ai_sqlite_" + [System.IO.Path]::GetRandomFileName() + ".py")
    $jsonTmp = [System.IO.Path]::Combine([System.IO.Path]::GetTempPath(), "kb_ai_sqlite_cmd_" + [System.IO.Path]::GetRandomFileName() + ".json")
    [System.IO.File]::WriteAllText($tmp, $SqliteHelper, [System.Text.UTF8Encoding]::new($false))
    try {
        # P0 修复(verifier 抓到的崩溃):ConvertTo-Json 会把 1-元素数组 unwrap 成标量,
        # 导致 Python sqlite3 收到 str 而不是 list,绑定失败。用 ArrayList 强制数组语义。
        $paramsList = New-Object System.Collections.ArrayList
        if ($null -ne $Params) {
            foreach ($p in $Params) { [void]$paramsList.Add($p) }
        }
        $cmd = @{
            db     = $DbPath
            sql    = $Sql
            params = $paramsList
        }
        $cmdJson = $cmd | ConvertTo-Json -Compress -Depth 8
        # v0.7.2: 将 JSON 命令写入临时文件(UTF-8 无 BOM),通过文件路径传给 Python,
        # 彻底规避中文 Windows 下 PowerShell pipe 到外部程序的 GBK 编码问题
        [System.IO.File]::WriteAllText($jsonTmp, $cmdJson, [System.Text.UTF8Encoding]::new($false))
        & $pythonExe @pythonArgs $tmp $jsonTmp 2>&1 | Tee-Object -Variable out | Out-Null
        if ($LASTEXITCODE -ne 0) {
            throw "sqlite exec 失败(python exit=$LASTEXITCODE): $out"
        }
        $outText = ($out | Out-String).Trim()
        if (-not $outText) { return $null }
        return $outText | ConvertFrom-Json
    } finally {
        Remove-Item $tmp -Force -ErrorAction SilentlyContinue
        Remove-Item $jsonTmp -Force -ErrorAction SilentlyContinue
    }
}

# ----------------------------------------------------------------------
# dot-source 守卫
# ----------------------------------------------------------------------

if ($MyInvocation.InvocationName -eq '.') {
    return
}