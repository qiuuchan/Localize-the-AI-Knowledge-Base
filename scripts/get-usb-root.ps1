<#
.SYNOPSIS
  KB-AI · 跨平台 U 盘根目录定位函数库

.DESCRIPTION
  ### 职责
    提供单一导出函数 Get-UsbRoot,供所有 scripts/ 下脚本 dot-source 后调用,
    解决"用户换 U 盘盘符 / 在 Mac/Linux 上 / 第一次接触 KB-AI"三种定位场景。

  ### 优先级(自上而下)
    1. 环境变量 $env:KB_AI_ROOT(显式覆盖;最高优先级,用于 CI/测试)
    2. 卷标 'AIAssistant' 定位:
         - Windows: Get-Volume -FileSystemLabel 'AIAssistant' + DriveLetter
         - Linux:   /proc/mounts 第 2 字段含 AIAssistant
         - macOS:   mount 输出含 AIAssistant
    3. 父目录链上的哨兵文件 .kb-ai-root(从 $PSScriptRoot 上溯)
    4. 父目录链上的 docker-compose.yml(M1 标志性文件)
    5. 兜底:返回 $PSScriptRoot 的父目录(向后兼容 M2a/M2b/M3a 既有调用)

  ### 用法
    . (Join-Path $PSScriptRoot 'get-usb-root.ps1')   # 仅加载函数
    $root = Get-UsbRoot

  ### 直接调用
    powershell -File scripts/get-usb-root.ps1        # stdout 输出根路径

.PARAMETER ProbeDir
  可选:起始探测目录(默认 $PSScriptRoot,通常用于测试场景)

.OUTPUTS
  [string] 绝对路径字符串(无尾部反斜杠,除非 Windows 卷标路径 X:\)

.NOTES
  PowerShell 5.1 兼容(避免 $IsWindows / Select-String -Path 等 PS 6+ 特性)。
  UTF-8 无 BOM(.NET [System.IO.File]::WriteAllText + UTF8Encoding($false))。
  dot-source 守卫:$MyInvocation.InvocationName -eq '.' → return
#>

[CmdletBinding()]
param(
    [string]$ProbeDir
)

$ErrorActionPreference = "Stop"

# ----------------------------------------------------------------------
# 平台判定(兼容 PS 5.1 — 不依赖 $IsWindows)
# ----------------------------------------------------------------------

$script:IsWindowsPlatform = ($PSVersionTable.PSVersion.Major -lt 6) -or ($env:OS -eq 'Windows_NT')
$script:IsLinuxPlatform   = ($PSVersionTable.PSVersion.Major -ge 6) -and $IsLinux
$script:IsMacPlatform     = ($PSVersionTable.PSVersion.Major -ge 6) -and $IsMacOS

# ----------------------------------------------------------------------
# 函数:Get-UsbRoot
# ----------------------------------------------------------------------

function Get-UsbRoot {
    <#
    .SYNOPSIS
      跨平台定位 KB-AI U 盘根目录。
    .DESCRIPTION
      见文件头注释。优先级 1 → 5 依次回退。
    .PARAMETER ProbeDir
      起始探测目录(默认 $PSScriptRoot 的父目录兜底;哨兵/docker-compose 上溯时用)
    .OUTPUTS
      [string]
    #>
    [CmdletBinding()]
    param(
        [string]$ProbeDir
    )

    # 起始探测点(未指定 → 当前调用者所在目录)
    if (-not $ProbeDir) {
        $caller = if ($PSScriptRoot) { $PSScriptRoot } else { (Get-Location).Path }
        $startDir = $caller
    } else {
        $startDir = $ProbeDir
    }

    # ===== 1. 环境变量优先 =====
    if ($env:KB_AI_ROOT -and $env:KB_AI_ROOT.Trim()) {
        $candidate = $env:KB_AI_ROOT.Trim()
        if (Test-Path $candidate) {
            try {
                $resolved = (Resolve-Path -LiteralPath $candidate -ErrorAction Stop).Path
                return $resolved
            } catch {
                # Resolve-Path 失败(罕见:盘符被拔),降级直接返回原值
                return $candidate
            }
        }
    }

    # ===== 2. 卷标定位 =====
    if ($script:IsWindowsPlatform) {
        try {
            $vol = Get-Volume -FileSystemLabel 'AIAssistant' -ErrorAction SilentlyContinue |
                   Where-Object { $_.DriveLetter } |
                   Select-Object -First 1
            if ($vol -and $vol.DriveLetter) {
                $driveRoot = ($vol.DriveLetter.ToString()) + ':\'
                if (Test-Path $driveRoot) {
                    return $driveRoot
                }
            }
        } catch {
            # Get-Volume 在非 Win / Server Core 缺失,静默降级
        }
    }
    elseif ($script:IsLinuxPlatform) {
        # /proc/mounts 第 2 字段是挂载点
        $mountsFile = '/proc/mounts'
        if (Test-Path $mountsFile) {
            try {
                $lines = Get-Content -LiteralPath $mountsFile -ErrorAction Stop
                $hit = $null
                foreach ($ln in $lines) {
                    if ($ln -match 'AIAssistant') {
                        $hit = $ln
                        break
                    }
                }
                if ($hit) {
                    $parts = $hit -split '\s+'
                    if ($parts.Count -ge 2) {
                        $candidate = $parts[1]
                        if (Test-Path $candidate) {
                            return $candidate
                        }
                    }
                }
            } catch { }
        }
    }
    elseif ($script:IsMacPlatform) {
        # macOS mount 输出格式:dev on /Volumes/AIAssistant (msdos, ...)
        try {
            $mountOutput = & mount 2>$null
            if ($mountOutput) {
                foreach ($ln in $mountOutput) {
                    if ($ln -match 'AIAssistant') {
                        # 提取 "on /path" 之间的部分
                        if ($ln -match '\son\s+(\S+)') {
                            $candidate = $Matches[1]
                            if (Test-Path $candidate) {
                                return $candidate
                            }
                        }
                    }
                }
            }
        } catch { }
    }

    # ===== 3. 哨兵文件 .kb-ai-root 上溯 =====
    $probe = $startDir
    while ($probe) {
        $sentinel = Join-Path $probe '.kb-ai-root'
        if (Test-Path -LiteralPath $sentinel) {
            return $probe
        }
        $parent = Split-Path -Parent $probe
        if (-not $parent -or $parent -eq $probe) { break }
        $probe = $parent
    }

    # ===== 4. docker-compose.yml 上溯(M1 标志性文件) =====
    $probe = $startDir
    while ($probe) {
        $composeFile = Join-Path $probe 'docker-compose.yml'
        if (Test-Path -LiteralPath $composeFile) {
            return $probe
        }
        $parent = Split-Path -Parent $probe
        if (-not $parent -or $parent -eq $probe) { break }
        $probe = $parent
    }

    # ===== 5. 兜底:startDir 的父目录 =====
    $parent = Split-Path -Parent $startDir
    if ($parent) { return $parent }
    return $startDir
}

# ----------------------------------------------------------------------
# 函数:Get-UsbRootProbe(仅用于单元测试 — 接受显式 ProbeDir)
# ----------------------------------------------------------------------
# 说明:本函数已在 Get-UsbRoot 内部实现,这里重导出以便测试覆盖。
function Get-UsbRootProbe {
    [CmdletBinding()]
    param([string]$ProbeDir)
    return (Get-UsbRoot -ProbeDir $ProbeDir)
}

# ----------------------------------------------------------------------
# dot-source 守卫:被 dot-source 时仅暴露函数,跳过主流程
# ----------------------------------------------------------------------
if ($MyInvocation.InvocationName -eq '.') {
    return
}

# ----------------------------------------------------------------------
# 主流程:命令行调用时输出根路径到 stdout(便于 shell 拼装)
# ----------------------------------------------------------------------

$root = Get-UsbRoot
Write-Host $root
exit 0