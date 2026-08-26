<#
.SYNOPSIS
    KB-AI · PS 脚本日志共享助手 (v1.5.4)

.DESCRIPTION
    提供 3 个函数给 dot-source 调用:
        Initialize-LogFile -ScriptName "health-full"   # 初始化 + 保留策略
        Write-LogHost -Message "..."                   # Write-Host + 追加到 $Script:LogFile
        Close-LogFile                                  # 写退出摘要

    失败兜底:U 盘只读时静默跳过 — Write-LogHost 退化为纯 Write-Host,不抛异常。

    设计哲学:
        - 共享助手位置:`scripts/lib/`(沿用 v1.3.1 CostLog-Rotate.ps1 约定)
        - 时间戳:PS 端用 `(Get-Date).ToString("yyyyMMdd-HHmmss")` 一行,无需 wmic
        - 保留策略:复用 v1.5.2 §3.1 方案 — 保留最近 20 个 `<script>-*.log`

.EXAMPLE
    . (Join-Path $PSScriptRoot 'lib/Write-Log.ps1')
    Initialize-LogFile -ScriptName "health-full"
    Write-LogHost "Hello" -ForegroundColor Green
    Close-LogFile

.NOTES
    PowerShell 5.1 兼容;UTF-8 无 BOM(.NET WriteAllText + UTF8Encoding $false)。
#>


function Initialize-LogFile {
    <#
    .SYNOPSIS
        初始化 PS 脚本日志文件。失败兜底:$Script:LogFile = $null,后续 Write-LogHost 退化为纯 console。
    .PARAMETER ScriptName
        脚本名(用于日志文件名前缀,例:"health-full")。
    #>
    param(
        [Parameter(Mandatory = $true)]
        [string]$ScriptName
    )

    # 日志目录 = KB-AI/logs/(即 $PSScriptRoot 的上两级 + /logs;scripts/lib 在 scripts/lib/ 故上 1 级是 scripts/,再上 1 级是 KB-AI 根)
    $logDir = Join-Path $PSScriptRoot "..\..\logs"
    $logDir = [System.IO.Path]::GetFullPath($logDir)

    if (-not (Test-Path -LiteralPath $logDir)) {
        try {
            New-Item -ItemType Directory -Path $logDir -Force | Out-Null
        } catch {
            Write-Warning "[Write-Log] 创建日志目录失败 · $($_.Exception.Message) · 不影响运行流程"
            $Script:LogFile = $null
            return
        }
    }

    # 时间戳 = yyyyMMdd-HHmmss(与 v1.5.2 start.bat / v1.5.3 stop.bat 一致)
    $timestamp = (Get-Date).ToString("yyyyMMdd-HHmmss")
    $Script:LogFile = Join-Path $logDir "$ScriptName-$timestamp.log"
    $Script:LogScriptName = $ScriptName

    try {
        $banner = "=== KB-AI $ScriptName.ps1 v1.5.4 日志 $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') ==="
        Set-Content -LiteralPath $Script:LogFile -Value $banner -Encoding UTF8 -ErrorAction Stop
    } catch {
        Write-Warning "[Write-Log] 日志创建失败 · 可能 U 盘只读 · 不影响运行流程"
        $Script:LogFile = $null
        return
    }

    Write-Host "日志: $Script:LogFile" -ForegroundColor Cyan

    # 保留最近 20 个 $ScriptName-*.log(沿用 v1.5.2 dir /b /o-d + skip=20 方案)
    try {
        Get-ChildItem -LiteralPath $logDir -Filter "$ScriptName-*.log" -File -ErrorAction SilentlyContinue |
            Sort-Object LastWriteTime -Descending |
            Select-Object -Skip 20 |
            ForEach-Object { Remove-Item -LiteralPath $_.FullName -Force -ErrorAction SilentlyContinue }
    } catch {
        # 保留策略失败不阻断主流程
    }
}


function Write-LogHost {
    <#
    .SYNOPSIS
        Write-Host + 追加到 $Script:LogFile(若已初始化)。失败兜底:不阻断 console 输出。
    .PARAMETER Message
        要输出的文本。
    .PARAMETER ForegroundColor
        Write-Host 颜色(默认 White)。
    .PARAMETER NoNewline
        透传 Write-Host -NoNewline(日志文件始终按完整行写入)。
    #>
    param(
        [Parameter(Mandatory = $true, Position = 0)]
        [AllowEmptyString()]
        [string]$Message,
        [string]$ForegroundColor = "White",
        [switch]$NoNewline = $false
    )

    if ($NoNewline) {
        Write-Host $Message -ForegroundColor $ForegroundColor -NoNewline
    } else {
        Write-Host $Message -ForegroundColor $ForegroundColor
    }

    if ($Script:LogFile) {
        try {
            # 日志文件始终按完整行写入(无论 console -NoNewline)
            Add-Content -LiteralPath $Script:LogFile -Value $Message -Encoding UTF8 -ErrorAction Stop
        } catch {
            # 兜底:不阻断 console 输出
        }
    }
}


function Close-LogFile {
    <#
    .SYNOPSIS
        关闭日志流 + 写退出摘要(便于检索本次运行的边界)。
    #>
    if ($Script:LogFile) {
        try {
            $exitCode = if ($LASTEXITCODE) { $LASTEXITCODE } else { 0 }
            $name = if ($Script:LogScriptName) { $Script:LogScriptName } else { "script" }
            $footer = "=== $name 退出 (exit=$exitCode) $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') ==="
            Add-Content -LiteralPath $Script:LogFile -Value $footer -Encoding UTF8 -ErrorAction Stop
        } catch {
            # 兜底
        }
    }
}