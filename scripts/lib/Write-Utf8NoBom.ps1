<#
.SYNOPSIS
  KB-AI · 日志输出 + UTF-8 NoBOM 文件工具(v0.7.1 从 chat.ps1 / embed-and-ingest.ps1 抽离)

.DESCRIPTION
  ### 职责
    统一日志输出格式 + UTF-8 无 BOM 文件追加 + SHA256 短哈希工具,避免每个
    脚本重复实现这些小工具。原内嵌于 chat.ps1:120-122 / 124-132 与
    embed-and-ingest.ps1:59-94,本脚本抽离为公共函数。

  ### 函数清单
    - Write-Step         :[HH:mm:ss] 时间戳 + Cyan 日志(主流程进度)
    - Write-Warn         :[HH:mm:ss] [WARN] + Yellow 警告
    - Write-Err          :[HH:mm:ss] [ERROR] + Red 错误
    - Add-Utf8NoBomLine  :UTF-8 无 BOM 写入一行(创建或追加)
    - Get-Sha256Short    :SHA256 前 N 位十六进制(默认 32)

  ### 用法
    . (Join-Path $PSScriptRoot 'lib/Write-Utf8NoBom.ps1')
    Write-Step "启动 chat"
    Add-Utf8NoBomLine -Path "<private>\KB-AI\cache\out.jsonl" -Line $entry

.NOTES
  PowerShell 5.1 兼容。
#>

$ErrorActionPreference = "Stop"

# ----------------------------------------------------------------------
# 函数:Write-Step / Write-Warn / Write-Err
# ----------------------------------------------------------------------

function Write-Step {
    <#
    .SYNOPSIS
      [HH:mm:ss] 时间戳 + Cyan 日志(主流程进度)。
    #>
    [CmdletBinding()]
    param([string]$Msg)
    Write-Host "[$(Get-Date -Format 'HH:mm:ss')] $Msg" -ForegroundColor Cyan
}

function Write-Warn {
    <#
    .SYNOPSIS
      [HH:mm:ss] [WARN] + Yellow 警告。
    #>
    [CmdletBinding()]
    param([string]$Msg)
    Write-Host "[$(Get-Date -Format 'HH:mm:ss')] [WARN] $Msg" -ForegroundColor Yellow
}

function Write-Err {
    <#
    .SYNOPSIS
      [HH:mm:ss] [ERROR] + Red 错误。
    #>
    [CmdletBinding()]
    param([string]$Msg)
    Write-Host "[$(Get-Date -Format 'HH:mm:ss')] [ERROR] $Msg" -ForegroundColor Red
}

# ----------------------------------------------------------------------
# 函数:Redact-Bearer(修复 3.1:HTTP 错误 body 中可能含 Bearer token,throw 前替换为 ***)
# ----------------------------------------------------------------------

function Redact-Bearer {
    <#
    .SYNOPSIS
      把 HTTP 错误响应 body 中的 Bearer token 替换为 ***,防止 throw 时泄漏。
    .DESCRIPTION
      阿里云百炼 / Tavily / Bing 公开 API 当前错误体不含 Authorization header,
      但未来若上游改格式(回显请求头)会立即泄漏。本函数是防御性 redact。
    .PARAMETER Text
      原始 body 字符串。
    .OUTPUTS
      [string] 脱敏后的字符串
    #>
    [CmdletBinding()]
    param([string]$Text)
    if (-not $Text) { return $Text }
    return ($Text -replace 'Bearer\s+[A-Za-z0-9_\-]+', 'Bearer ***')
}

# ----------------------------------------------------------------------
# 函数:Add-Utf8NoBomLine
# ----------------------------------------------------------------------

function Add-Utf8NoBomLine {
    <#
    .SYNOPSIS
      UTF-8 无 BOM 写入一行(创建或追加)。用于 jsonl / cache 等纯文本追加场景。
    .PARAMETER Path
      文件绝对路径(不存在则创建,含父目录需预建)。
    .PARAMETER Line
      要写入的一行内容(本函数自动追加换行符)。
    #>
    [CmdletBinding()]
    param([string]$Path, [string]$Line)
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    if (-not (Test-Path $Path)) {
        [System.IO.File]::WriteAllText($Path, $Line + "`n", $utf8NoBom)
    } else {
        [System.IO.File]::AppendAllText($Path, $Line + "`n", $utf8NoBom)
    }
}

# ----------------------------------------------------------------------
# 函数:Get-Sha256Short
# ----------------------------------------------------------------------

function Get-Sha256Short {
    <#
    .SYNOPSIS
      计算字符串 SHA256 哈希,返回前 N 位十六进制(默认 32)。
    .DESCRIPTION
      用于生成 Qdrant point id(幂等 upsert key):sha256(source|chunk_index)[:32]。
      注意:Qdrant v1.7.0 只接受 integer 或 UUID 格式字符串作为 point id,因此通常
      需要再经过 Format-AsUuid 转换。
    .PARAMETER Text
      输入字符串。
    .PARAMETER Len
      返回十六进制字符数(默认 32)。
    #>
    [CmdletBinding()]
    param([string]$Text, [int]$Len = 32)
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($Text)
    $sha = [System.Security.Cryptography.SHA256]::Create()
    $hash = $sha.ComputeHash($bytes)
    $sb = New-Object System.Text.StringBuilder
    foreach ($b in $hash) { [void]$sb.Append($b.ToString("x2")) }
    return $sb.ToString().Substring(0, $Len)
}

# ----------------------------------------------------------------------
# 函数:Format-AsUuid
# ----------------------------------------------------------------------

function Format-AsUuid {
    <#
    .SYNOPSIS
      将 32 位十六进制字符串格式化为 UUID 字符串。
    .DESCRIPTION
      Qdrant v1.7.0 的 point id 只接受 integer 或 UUID 格式字符串。
      本函数把 Get-Sha256Short 输出的 32 位十六进制串转成 8-4-4-4-12 的 UUID 格式,
      保证内容哈希的幂等性不变。
    .PARAMETER Hex
      32 位十六进制字符串(不区分大小写,允许含或不含连字符)。
    #>
    [CmdletBinding()]
    param([string]$Hex)
    $h = $Hex.Replace("-", "").ToLowerInvariant()
    if ($h.Length -lt 32) { $h = $h.PadRight(32, '0') }
    return "{0}-{1}-{2}-{3}-{4}" -f $h.Substring(0,8), $h.Substring(8,4), $h.Substring(12,4), $h.Substring(16,4), $h.Substring(20,12)
}

# ----------------------------------------------------------------------
# 函数:Read-ResponseAsUtf8
# ----------------------------------------------------------------------
# v0.7.2: PowerShell 5.1 的 Invoke-WebRequest 在服务端未返回 charset 时,
# 会把 UTF-8 响应错误解码为 Latin-1/Windows-1252,导致中文乱码。
# 本函数从 RawContentStream 读取原始字节并按 UTF-8 解码。
function Read-ResponseAsUtf8 {
    [CmdletBinding()]
    param([Parameter(Mandatory = $true)] [Microsoft.PowerShell.Commands.WebResponseObject]$Response)
    if ($Response.RawContentStream) {
        $bytes = New-Object byte[] $Response.RawContentStream.Length
        $Response.RawContentStream.Position = 0
        [void]$Response.RawContentStream.Read($bytes, 0, $bytes.Length)
        return [System.Text.Encoding]::UTF8.GetString($bytes)
    }
    # 兜底:Content 已经是字符串,尝试重新解码
    $bytes = [System.Text.Encoding]::GetEncoding("iso-8859-1").GetBytes($Response.Content)
    return [System.Text.Encoding]::UTF8.GetString($bytes)
}

# ----------------------------------------------------------------------
# dot-source 守卫
# ----------------------------------------------------------------------

if ($MyInvocation.InvocationName -eq '.') {
    return
}