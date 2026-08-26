<#
.SYNOPSIS
  KB-AI · .env 文件加载公共库(M3c 抽离,v0.7.1 迁入 scripts/lib/)

.DESCRIPTION
  ### 职责
    统一"参数 > 环境变量 > .env 文件 > 兜底"四档优先级读取,避免每个脚本重复实现。
    现有 chat.ps1 / embed-and-ingest.ps1 / batch-images.ps1 / status-bar.ps1 /
    websearch.ps1 都内嵌了 Get-EnvVar 函数,本脚本抽离为公共函数,所有调用方
    统一通过 dot-source 引用 scripts/lib/load-env.ps1。

  ### 函数清单
    - Get-EnvVar       :从指定 .env 文件读取 KEY(忽略 # 注释 / 空行)
    - Resolve-ApiKey   :四档优先级解析 API Key(参数 > 环境变量 > .env > 占位符)
    - Load-KBAIEnv     :批量加载多个 KEY 到 hashtable(用于批量场景)
    - Test-IsPlaceholder:判断字符串是否是占位符

  ### 优先级(自上而下)
    1. 显式传入的参数值(非 null 且非空字符串)
    2. $env:<NAME> 环境变量
    3. .env 文件(走 Get-EnvVar)
    4. 占位符判断:如果读出的是 "sk-PLEASE-FILL-IN" / "tvly-PLEASE-FILL-IN" 等,
       返回 $null(让调用方走"未提供"的错误路径)

  ### 用法(从其他脚本 dot-source)
    . (Join-Path $PSScriptRoot 'lib/load-env.ps1')
    $key = Resolve-ApiKey -Name "ALIYUN_BAILIAN_API_KEY" -Explicit $ApiKey -EnvPath $envPath

.PARAMETER EnvPath
  可选:.env 文件绝对路径(默认调用方传)。

.NOTES
  PowerShell 5.1 兼容(避免 PS 6+ 专属特性)。
  UTF-8 无 BOM(.NET WriteAllText + UTF8Encoding($false))。
  dot-source 守卫:$MyInvocation.InvocationName -eq '.' → return。
  v0.7.1 路径变更:从 scripts/load-env.ps1 → scripts/lib/load-env.ps1。
#>

[CmdletBinding()]
param(
    [string]$EnvPath
)

$ErrorActionPreference = "Stop"

# ----------------------------------------------------------------------
# 占位符列表:这些值表示"未填写",应当作 $null 处理
# ----------------------------------------------------------------------

$script:PlaceholderPatterns = @(
    'PLEASE-FILL-IN',
    'sk-PLEASE-FILL-IN',
    'sk-PLEASE-FILL-IN-YOUR-ALIYUN-BAILIAN-API-KEY',
    'tvly-PLEASE-FILL-IN',
    'changeme'
)

# ----------------------------------------------------------------------
# 函数:Get-EnvVar
# ----------------------------------------------------------------------

function Get-EnvVar {
    <#
    .SYNOPSIS
      从 .env 文件读取指定 KEY 的值。
    .DESCRIPTION
      - 忽略空行和以 # 开头的注释
      - 格式:KEY=value(value 允许包含 = 和特殊字符,正则非贪婪取到行尾)
      - 大小写敏感(KEY 必须完全匹配)
    .PARAMETER EnvPath
      .env 文件绝对路径(不存在则返回 $null)
    .PARAMETER Name
      要读取的 KEY 名(不带 $env: 前缀)
    .OUTPUTS
      [string] 或 $null
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)] [string]$EnvPath,
        [Parameter(Mandatory = $true)] [string]$Name
    )
    if (-not (Test-Path -LiteralPath $EnvPath)) { return $null }
    # 按行读(不要 -Raw,避免多行匹配)
    $lines = Get-Content -LiteralPath $EnvPath -Encoding UTF8
    foreach ($line in $lines) {
        $trimmed = $line.Trim()
        if ([string]::IsNullOrWhiteSpace($trimmed)) { continue }
        if ($trimmed.StartsWith("#")) { continue }
        # 匹配 KEY=value(value 取整行剩余部分)
        if ($trimmed -match "^$([regex]::Escape($Name))\s*=\s*(.+)$") {
            $val = $Matches[1].Trim()
            # 去掉尾部 # 注释(若有):仅当 # 前有空格分隔
            if ($val -match '^(.*?)\s+#\s') {
                $val = $Matches[1].Trim()
            }
            return $val
        }
    }
    return $null
}

# ----------------------------------------------------------------------
# 函数:Resolve-ApiKey
# ----------------------------------------------------------------------

function Resolve-ApiKey {
    <#
    .SYNOPSIS
      按四档优先级解析 API Key。
    .DESCRIPTION
      优先级:显式参数 > 环境变量 > .env 文件 > $null
      占位符(PLACEHOLDER / PLEASE-FILL-IN)一律视为 $null。
    .PARAMETER Name
      KEY 名,如 "ALIYUN_BAILIAN_API_KEY"
    .PARAMETER Explicit
      调用方显式传入的值(通常对应 -ApiKey 参数;为空则跳过该档)
    .PARAMETER EnvPath
      .env 文件绝对路径
    .OUTPUTS
      [string] 或 $null
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)] [string]$Name,
        [string]$Explicit = "",
        [string]$EnvPath = ""
    )
    # 档 1:显式参数
    if ($Explicit -and $Explicit.Trim()) {
        $val = $Explicit.Trim()
        if (-not (Test-IsPlaceholder -Value $val)) {
            return $val
        }
    }
    # 档 2:环境变量
    $envVal = [Environment]::GetEnvironmentVariable($Name)
    if ($envVal -and $envVal.Trim() -and -not (Test-IsPlaceholder -Value $envVal.Trim())) {
        return $envVal.Trim()
    }
    # 档 3:.env 文件
    if ($EnvPath -and (Test-Path -LiteralPath $EnvPath)) {
        $fileVal = Get-EnvVar -EnvPath $EnvPath -Name $Name
        if ($fileVal -and -not (Test-IsPlaceholder -Value $fileVal)) {
            return $fileVal
        }
    }
    return $null
}

# ----------------------------------------------------------------------
# 函数:Test-IsPlaceholder
# ----------------------------------------------------------------------

function Test-IsPlaceholder {
    <#
    .SYNOPSIS
      判断字符串是否是占位符(如 PLEASE-FILL-IN)。
    .OUTPUTS
      [bool]
    #>
    [CmdletBinding()]
    param([string]$Value)
    if (-not $Value) { return $true }
    foreach ($p in $script:PlaceholderPatterns) {
        if ($Value -eq $p) { return $true }
        if ($Value -like "$p*") { return $true }
    }
    return $false
}

# ----------------------------------------------------------------------
# 函数:Load-KBAIEnv
# ----------------------------------------------------------------------

function Load-KBAIEnv {
    <#
    .SYNOPSIS
      批量从 .env 加载多个 KEY 到 hashtable。
    .PARAMETER EnvPath
      .env 文件绝对路径
    .PARAMETER Keys
      要读取的 KEY 名数组
    .OUTPUTS
      [hashtable] @{<KEY> = <value> 或 $null}
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)] [string]$EnvPath,
        [Parameter(Mandatory = $true)] [string[]]$Keys
    )
    $ht = @{}
    foreach ($k in $Keys) {
        $v = Get-EnvVar -EnvPath $EnvPath -Name $k
        if ($v -and (Test-IsPlaceholder -Value $v)) { $v = $null }
        $ht[$k] = $v
    }
    return $ht
}

# ----------------------------------------------------------------------
# dot-source 守卫
# ----------------------------------------------------------------------

if ($MyInvocation.InvocationName -eq '.') {
    return
}

# ----------------------------------------------------------------------
# CLI 模式:列出 .env 中所有非占位符 KEY
# ----------------------------------------------------------------------

if (-not $EnvPath) {
    Write-Host "用法:pwsh -File scripts/lib/load-env.ps1 -EnvPath <.env 路径>" -ForegroundColor Yellow
    Write-Host "      或 dot-source 后调用 Get-EnvVar / Resolve-ApiKey"
    exit 1
}

if (-not (Test-Path -LiteralPath $EnvPath)) {
    Write-Host "[ERROR] 找不到 .env: $EnvPath" -ForegroundColor Red
    exit 1
}

Write-Host "[$(Get-Date -Format 'HH:mm:ss')] .env: $EnvPath" -ForegroundColor Cyan
$lines = Get-Content -LiteralPath $EnvPath -Encoding UTF8
foreach ($line in $lines) {
    $trimmed = $line.Trim()
    if ([string]::IsNullOrWhiteSpace($trimmed)) { continue }
    if ($trimmed.StartsWith("#")) { continue }
    if ($trimmed -match "^([A-Z_][A-Z0-9_]*)\s*=\s*(.+)$") {
        $k = $Matches[1]
        $v = $Matches[2].Trim()
        $placeholder = Test-IsPlaceholder -Value $v
        $marker = if ($placeholder) { "[PLACEHOLDER]" } else { "[OK]" }
        $color = if ($placeholder) { "Yellow" } else { "Green" }
        # 修复 2.12:CLI 模式下截断到前 4 字符(原前 8 字符泄漏过多),与 sk- 前缀长度对齐
        $vDisplay = if ($v.Length -gt 8) { $v.Substring(0, 4) + "****" } else { $v }
        Write-Host ("  {0,-15} {1,-14} {2}" -f $k, $marker, $vDisplay) -ForegroundColor $color
    }
}
exit 0