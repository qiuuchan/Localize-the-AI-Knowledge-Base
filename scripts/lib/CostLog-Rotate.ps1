<#
.SYNOPSIS
  KB-AI · cost_log.jsonl 日志轮转 + UTC 规范化 (v1.3.1)

.DESCRIPTION
  PS 5.1 dot-source 库。导出 3 个函数:
    - Rotate-CostLog                — 50MB 阈值,gzip 归档 + 截断
    - Get-MonthlyCostFromAllSources — 累加当前 + 同月所有 .gz 归档
    - Get-CanonicalUtcMonth         — ISO8601 → UTC yyyy-MM 规范化

.NOTES
  PowerShell 5.1 兼容。所有异常 try/catch + Write-Warning,不抛。
#>

$ErrorActionPreference = "Continue"

# 阈值常量
$script:CostLogRotateBytesDefault = 50 * 1024 * 1024

function Rotate-CostLog {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,

        [Parameter(Mandatory = $false)]
        [int]$ThresholdBytes = $script:CostLogRotateBytesDefault
    )

    if (-not (Test-Path $Path)) {
        Write-Warning "Rotate-CostLog: $Path 不存在,跳过"
        return
    }

    $file = Get-Item $Path
    if ($file.Length -lt $ThresholdBytes) {
        return  # 未超阈值,no-op
    }

    $dir = Split-Path -Parent $Path
    $base = Split-Path -Leaf $Path
    # 归档名格式: <base>.<UTC-YYYY-MM>.gz (同月重复追加 -N)
    $utcNow = [DateTimeOffset]::UtcNow
    $ym = $utcNow.ToString("yyyy-MM")
    $archiveBase = "$base.$ym"

    $archivePath = Join-Path $dir "$archiveBase.gz"
    $suffix = 2
    while (Test-Path $archivePath) {
        $archivePath = Join-Path $dir "$archiveBase-$suffix.gz"
        $suffix++
    }

    try {
        $sourceBytes = [System.IO.File]::ReadAllBytes($Path)
        $gzStream = [System.IO.File]::Create($archivePath)
        try {
            $gzip = New-Object System.IO.Compression.GZipStream($gzStream, [System.IO.Compression.CompressionMode]::Compress)
            try {
                $gzip.Write($sourceBytes, 0, $sourceBytes.Length)
            } finally {
                $gzip.Dispose()
            }
        } finally {
            $gzStream.Dispose()
        }
        # 截断原文件为空(UTF-8 无 BOM)
        [System.IO.File]::WriteAllText($Path, "", [System.Text.UTF8Encoding]::new($false))
        Write-Host "[Rotate-CostLog] archived to $archivePath ($([math]::Round($file.Length / 1MB, 1)) MB)" -ForegroundColor Green
    } catch {
        Write-Warning "Rotate-CostLog: 归档失败,保留原文件 - $($_.Exception.Message)"
    }
}

function Get-MonthlyCostFromAllSources {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string]$DataDir,

        [Parameter(Mandatory = $true)]
        [string]$YearMonth
    )

    $result = @{
        input_tokens = 0
        output_tokens = 0
        today_yuan = 0.0
        month_yuan = 0.0
        today_count = 0
        month_count = 0
        sources = @()
    }

    $todayDate = [DateTimeOffset]::UtcNow.ToString("yyyy-MM-dd")
    $priceTable = @{
        "qwen3.6-plus"      = @{ input = 4.0;   output = 12.0 }
        "qwen3.7-max"       = @{ input = 12.0;  output = 36.0 }
        "text-embedding-v3" = @{ input = 0.7;   output = 0.0  }
    }

    # 1. 当前 cost_log.jsonl
    $currentPath = Join-Path $DataDir "cost_log.jsonl"
    $sources = @($currentPath)
    # 2. 同月所有 .gz 归档(YYYY-MM[-N])
    Get-ChildItem -Path $DataDir -Filter "cost_log.jsonl.$YearMonth*.gz" -ErrorAction SilentlyContinue | ForEach-Object {
        $sources += $_.FullName
    }

    foreach ($src in $sources) {
        if (-not (Test-Path $src)) { continue }
        $result.sources += $src
        $content = $null
        try {
            if ($src.EndsWith(".gz")) {
                $gzStream = [System.IO.File]::OpenRead($src)
                try {
                    $gzip = New-Object System.IO.Compression.GZipStream($gzStream, [System.IO.Compression.CompressionMode]::Decompress)
                    try {
                        $reader = New-Object System.IO.StreamReader($gzip, [System.Text.UTF8Encoding]::new($false))
                        try {
                            $content = $reader.ReadToEnd()
                        } finally {
                            $reader.Dispose()
                        }
                    } finally {
                        $gzip.Dispose()
                    }
                } finally {
                    $gzStream.Dispose()
                }
            } else {
                $content = Get-Content $src -Raw -ErrorAction Stop
            }
        } catch {
            Write-Warning "Get-MonthlyCostFromAllSources: 读 $src 失败 - $($_.Exception.Message)"
            continue
        }

        if (-not $content) { continue }

        foreach ($line in ($content -split "`n")) {
            if ([string]::IsNullOrWhiteSpace($line)) { continue }
            try {
                $entry = $line.Trim() | ConvertFrom-Json -ErrorAction Stop
            } catch {
                continue  # 跳过损坏行
            }
            if (-not $entry.model -or $null -eq $entry.in -or $null -eq $entry.out) { continue }
            $price = $priceTable[$entry.model]
            if (-not $price) { continue }

            $entryMonth = Get-CanonicalUtcMonth -Timestamp $entry.ts
            $entryDate = ""
            try {
                $entryDate = ([DateTimeOffset]::Parse($entry.ts).ToUniversalTime()).ToString("yyyy-MM-dd")
            } catch {
                $entryDate = ""
            }

            $cost = ($entry.in / 1000000.0) * $price.input + ($entry.out / 1000000.0) * $price.output

            if ($entryMonth -eq $YearMonth) {
                $result.input_tokens += [int]$entry.in
                $result.output_tokens += [int]$entry.out
                $result.month_yuan += $cost
                $result.month_count++
            }
            if ($entryDate -eq $todayDate) {
                $result.today_yuan += $cost
                $result.today_count++
            }
        }
    }

    return $result
}

function Get-CanonicalUtcMonth {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [AllowEmptyString()]
        [string]$Timestamp
    )
    if ([string]::IsNullOrWhiteSpace($Timestamp)) {
        return [DateTimeOffset]::UtcNow.ToString("yyyy-MM")
    }
    try {
        $dto = [DateTimeOffset]::Parse($Timestamp).ToUniversalTime()
        return $dto.ToString("yyyy-MM")
    } catch {
        Write-Warning "Get-CanonicalUtcMonth: unparseable ts '$Timestamp', fallback to current UTC month"
        return [DateTimeOffset]::UtcNow.ToString("yyyy-MM")
    }
}
