<#
.SYNOPSIS
  KB-AI · 跨平台小工具 (v1.7.0 · Mac 支持)

.DESCRIPTION
  ### 职责
    提供 9 个跨平台小工具函数,给 dot-source 调用,统一 Windows / macOS / Linux
    行为差异。所有函数 PS 5.1 兼容(不用 $IsMacOS / $IsLinux / $IsWindows 自动
    变量,改用 uname + $env:OS 判定)。

  ### 函数清单
    平台检测 (1)
      Get-KBAIPlatform                       :返回 'Windows' / 'macOS' / 'Linux' / 'Unknown'

    venv 路径 (3)
      Get-KBAIPythonVenvPath                 :.venv 下的 python(Win: Scripts\python.exe,Mac: bin/python)
      Get-KBAIPythonVenvPip                  :.venv 下的 pip(同上模式)
      Get-KBAIPythonVenvUvicorn              :.venv 下的 uvicorn(同上模式)

    系统交互 (2)
      Open-KBAIUrl                           :用默认浏览器打开 URL(Win: Start-Process,Mac: open)
      Show-KBAINotice                        :弹系统通知对话框(Win: WinForms,Mac: osascript heredoc)

    硬件探测 (4)
      Get-KBAICpuVirtualization              :@ { Supported, Detail }
      Get-KBAIOSVersion                      :string("14.5" / "10.0.19041" 等)
      Get-KBAIDiskFreeGB -Path <p>           :double(GB)
      Get-KBAIMemoryGB                       :double(GB)

    平台专属 (1)
      Test-KBAISIPStatus                     :@ { Enabled, Status } — macOS SIP

  ### 设计哲学
    - 函数而非 $script: 变量(避免 dot-source 作用域污染,见 plan §十 #2)
    - 失败兜底:所有函数永 throw 不出去(失败返回空值 / false / 0)
    - PS 5.1 兼容:不依赖 PS 6+ 自动变量
    - UTF-8 无 BOM(.NET WriteAllText 范式)

.EXAMPLE
  . (Join-Path $PSScriptRoot 'lib/platform-utils.ps1')
  $platform = Get-KBAIPlatform
  $py = Get-KBAIPythonVenvPath -BackendDir "$root/backend"
  Show-KBAINotice -Message "启动完成" -Title "KB-AI"

.NOTES
  PowerShell 5.1 兼容(不用 $IsMacOS / $IsLinux / $IsWindows)。
  UTF-8 无 BOM(.NET WriteAllText + UTF8Encoding $false)。
  dot-source 守卫:$MyInvocation.InvocationName -eq '.' → return。
#>


# ----------------------------------------------------------------------
# 1) Get-KBAIPlatform
# ----------------------------------------------------------------------

function Get-KBAIPlatform {
    <#
    .SYNOPSIS
      返回当前平台标识。
    .DESCRIPTION
      PS 5.1 兼容:不依赖 $IsMacOS / $IsLinux / $IsWindows(PS 6+ 自动变量,PS 5.1 上是 $null)。
      - Windows:$env:OS = 'Windows_NT' → 'Windows'
      - macOS:  uname -s 输出含 'Darwin' → 'macOS'
      - Linux:  uname -s 输出含 'Linux' → 'Linux'
      - 其他:   → 'Unknown'(包括 uname 不可用 / 未识别)
    .OUTPUTS
      [string] 'Windows' | 'macOS' | 'Linux' | 'Unknown'
    #>
    [CmdletBinding()]
    param()

    # Windows:PS 5.1 / 7 都可用
    if ($env:OS -eq 'Windows_NT') { return 'Windows' }

    # Unix-like:uname -s 区分
    # 用 cmd /c 兜底,确保 PS 5.1 也能跑
    try {
        $uname = (& uname -s 2>$null) | Out-String
        if ($uname -match 'Darwin') { return 'macOS' }
        if ($uname -match 'Linux')  { return 'Linux' }
    } catch {
        # uname 不存在(罕见:Windows MSYS / Cygwin 缺 uname)
    }

    return 'Unknown'
}


# ----------------------------------------------------------------------
# 2-4) venv 路径三件套(Windows / macOS 自动切换)
# ----------------------------------------------------------------------

function Get-KBAIPythonVenvPath {
    <#
    .SYNOPSIS
      跨平台解析 backend/.venv 下的 python 可执行文件路径。
    .PARAMETER BackendDir
      backend 目录绝对路径。
    .OUTPUTS
      [string] 路径字符串(Win: .venv/Scripts/python.exe,Mac/Linux: .venv/bin/python)
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory = $true)][string]$BackendDir)

    if ((Get-KBAIPlatform) -eq 'Windows') {
        return (Join-Path $BackendDir '.venv/Scripts/python.exe')
    }
    # macOS / Linux / Unknown 一律走 .venv/bin/python(未知平台兜底)
    return (Join-Path $BackendDir '.venv/bin/python')
}


function Get-KBAIPythonVenvPip {
    <#
    .SYNOPSIS
      跨平台解析 backend/.venv 下的 pip 路径。
    .PARAMETER BackendDir
      backend 目录绝对路径。
    .OUTPUTS
      [string] 路径字符串
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory = $true)][string]$BackendDir)

    if ((Get-KBAIPlatform) -eq 'Windows') {
        return (Join-Path $BackendDir '.venv/Scripts/pip.exe')
    }
    return (Join-Path $BackendDir '.venv/bin/pip')
}


function Get-KBAIPythonVenvUvicorn {
    <#
    .SYNOPSIS
      跨平台解析 backend/.venv 下的 uvicorn 路径。
    .PARAMETER BackendDir
      backend 目录绝对路径。
    .OUTPUTS
      [string] 路径字符串
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory = $true)][string]$BackendDir)

    if ((Get-KBAIPlatform) -eq 'Windows') {
        return (Join-Path $BackendDir '.venv/Scripts/uvicorn.exe')
    }
    return (Join-Path $BackendDir '.venv/bin/uvicorn')
}


# ----------------------------------------------------------------------
# 5) Open-KBAIUrl
# ----------------------------------------------------------------------

function Open-KBAIUrl {
    <#
    .SYNOPSIS
      用系统默认浏览器打开 URL(跨平台)。
    .PARAMETER Url
      要打开的 URL(必须含 http:// 或 https://)。
    .NOTES
      - Windows:Start-Process <url>(系统走 ShellExec)
      - macOS:  Start-Process 'open' <url>(macOS 的 open 命令)
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory = $true)][string]$Url)

    if ((Get-KBAIPlatform) -eq 'macOS') {
        Start-Process -FilePath 'open' -ArgumentList $Url -ErrorAction SilentlyContinue
    } else {
        Start-Process -FilePath $Url -ErrorAction SilentlyContinue
    }
}


# ----------------------------------------------------------------------
# 6) Show-KBAINotice
# ----------------------------------------------------------------------

function Show-KBAINotice {
    <#
    .SYNOPSIS
      弹系统通知对话框(跨平台)。
    .PARAMETER Message
      通知内容(支持中文、多行)。
    .PARAMETER Title
      对话框标题,默认 'KB-AI'。
    .NOTES
      关键设计:不走 osascript -e "..."(中文/换行/单引号 escape 噩梦),
      改用 stdin + heredoc(AppleScript 文档推荐,支持完整多行对话框)。

      失败兜底:
      - Windows:无 GUI 会话 → 终端打印
      - macOS:无 GUI / SIP 阻挡 osascript → 终端打印
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)][string]$Message,
        [string]$Title = 'KB-AI'
    )

    if ((Get-KBAIPlatform) -eq 'macOS') {
        # AppleScript display dialog 不接受裸换行 → 替换为空格
        $msgSafe = ($Message -replace "`r?`n", ' ')
        # AppleScript 字符串内的双引号 / 反斜杠需转义
        $msgSafe = $msgSafe -replace '\\', '\\\\' -replace '"', '\\"'
        $titleSafe = $Title -replace '\\', '\\\\' -replace '"', '\\"'
        $script = @"
tell application "System Events"
    display dialog "$msgSafe" with title "$titleSafe" buttons {"OK"} default button "OK"
end tell
"@
        # 用 stdin 喂(避免 -e 参数 escape 灾难);-l AppleScript 显式声明语言
        $script | & osascript -l AppleScript 2>&1 | Out-Null
        if ($LASTEXITCODE -ne 0) {
            # osascript 失败(SIP / 无 GUI 会话)→ 终端降级
            Write-Host "[$Title] $Message"
        }
        return
    }

    # Windows:Windows Forms MessageBox
    if (-not ('System.Windows.Forms.MessageBox' -as [type])) {
        try {
            Add-Type -AssemblyName System.Windows.Forms -ErrorAction Stop
        } catch {
            # 无 GUI 会话(SSH / Server Core)→ 终端降级
            Write-Host "[$Title] $Message"
            return
        }
    }
    [System.Windows.Forms.MessageBox]::Show($Message, $Title, 'OK', 'Information') | Out-Null
}


# ----------------------------------------------------------------------
# 7) Get-KBAICpuVirtualization
# ----------------------------------------------------------------------

function Get-KBAICpuVirtualization {
    <#
    .SYNOPSIS
      检测 CPU 虚拟化支持(跨平台)。
    .OUTPUTS
      [hashtable] @{ Supported = [bool]; Detail = [string] }
    .NOTES
      - Windows:Get-CimInstance Win32_Processor.VirtualizationFirmwareEnabled
      - macOS:  Apple Silicon(arm64)永远支持;Intel Mac 查 sysctl hw.optional.hv
    #>
    [CmdletBinding()]
    param()

    $platform = Get-KBAIPlatform

    if ($platform -eq 'macOS') {
        $arch = (& uname -m 2>$null) | Out-String
        if ($arch -match 'arm64') {
            return @{ Supported = $true; Detail = 'Apple Silicon (arm64) = native ARM virtualization' }
        }
        $hw = (& sysctl -n hw.optional.hv 2>$null) | Out-String
        $hwTrim = if ($hw) { $hw.Trim() } else { '' }
        return @{ Supported = ($hwTrim -eq '1'); Detail = "Intel + hw.optional.hv=$hwTrim" }
    }

    if ($platform -eq 'Windows') {
        try {
            $fw = (Get-CimInstance Win32_Processor).VirtualizationFirmwareEnabled
            return @{ Supported = [bool]$fw; Detail = "FirmwareEnabled=$fw" }
        } catch {
            return @{ Supported = $false; Detail = "Win32_Processor 不可用" }
        }
    }

    # Linux:简化 — 检 /dev/kvm 存在
    $kvm = Test-Path -LiteralPath '/dev/kvm' -ErrorAction SilentlyContinue
    return @{ Supported = $kvm; Detail = "Linux /dev/kvm=$kvm" }
}


# ----------------------------------------------------------------------
# 8) Get-KBAIOSVersion
# ----------------------------------------------------------------------

function Get-KBAIOSVersion {
    <#
    .SYNOPSIS
      返回操作系统版本字符串(跨平台)。
    .OUTPUTS
      [string] "14.5" / "10.0.19041" / "6.1.0-13-amd64" / "Unknown"
    .NOTES
      - Windows:Get-CimInstance Win32_OperatingSystem.Version
      - macOS:  sw_vers -productVersion
      - Linux:  uname -r(简化)
    #>
    [CmdletBinding()]
    param()

    $platform = Get-KBAIPlatform

    if ($platform -eq 'macOS') {
        $v = (& sw_vers -productVersion 2>$null) | Out-String
        if ($v) { return $v.Trim() }
        return 'Unknown'
    }

    if ($platform -eq 'Windows') {
        try {
            return (Get-CimInstance Win32_OperatingSystem).Version
        } catch {
            return 'Unknown'
        }
    }

    if ($platform -eq 'Linux') {
        $v = (& uname -r 2>$null) | Out-String
        if ($v) { return $v.Trim() }
        return 'Unknown'
    }

    return 'Unknown'
}


# ----------------------------------------------------------------------
# 9) Get-KBAIDiskFreeGB
# ----------------------------------------------------------------------

function Get-KBAIDiskFreeGB {
    <#
    .SYNOPSIS
      返回指定路径所在磁盘分区的剩余空间(GB)。
    .PARAMETER Path
      任意路径(用于定位所在分区)。
    .OUTPUTS
      [double] 剩余空间(GB),失败返回 0。
    .NOTES
      - Windows:Get-PSDrive 取 Free,转 GB
      - macOS:  df -k 取第 4 字段(Available KB),转 GB
      - Linux:  同 macOS(df 行为一致)
    #>
    [CmdletBinding()]
    param([Parameter(Mandatory = $true)][string]$Path)

    $platform = Get-KBAIPlatform

    if ($platform -eq 'macOS' -or $platform -eq 'Linux') {
        try {
            # df -k 输出格式:Filesystem 1024-blocks Used Available Capacity iused ifree %iused Mounted
            $dfOutput = & df -k "$Path" 2>$null
            if ($dfOutput -and $dfOutput.Count -ge 2) {
                $lastLine = $dfOutput[-1]
                $fields = $lastLine -split '\s+'
                if ($fields.Count -ge 4) {
                    $kbFree = [long]$fields[3]
                    return [math]::Round($kbFree / 1MB, 2)   # KB → GB
                }
            }
        } catch {
            return 0
        }
        return 0
    }

    if ($platform -eq 'Windows') {
        try {
            $drive = [System.IO.Path]::GetPathRoot([System.IO.Path]::GetFullPath($Path))
            $driveLetter = $drive.TrimEnd('\').TrimEnd(':')
            $free = (Get-PSDrive -Name $driveLetter -ErrorAction SilentlyContinue).Free
            if ($free) {
                return [math]::Round($free / 1GB, 2)
            }
        } catch {
            return 0
        }
        return 0
    }

    return 0
}


# ----------------------------------------------------------------------
# 10) Get-KBAIMemoryGB
# ----------------------------------------------------------------------

function Get-KBAIMemoryGB {
    <#
    .SYNOPSIS
      返回系统总物理内存(GB)。
    .OUTPUTS
      [double] 内存(GB),失败返回 0。
    .NOTES
      - Windows:Get-CimInstance Win32_ComputerSystem.TotalPhysicalMemory
      - macOS:  sysctl -n hw.memsize
      - Linux:  /proc/meminfo MemTotal
    #>
    [CmdletBinding()]
    param()

    $platform = Get-KBAIPlatform

    if ($platform -eq 'macOS') {
        try {
            $bytes = [long](& sysctl -n hw.memsize 2>$null | Out-String | ForEach-Object { $_.Trim() })
            if ($bytes -gt 0) {
                return [math]::Round($bytes / 1GB, 2)
            }
        } catch {
            return 0
        }
        return 0
    }

    if ($platform -eq 'Windows') {
        try {
            $bytes = (Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory
            if ($bytes) {
                return [math]::Round($bytes / 1GB, 2)
            }
        } catch {
            return 0
        }
        return 0
    }

    if ($platform -eq 'Linux') {
        try {
            $meminfo = Get-Content -LiteralPath '/proc/meminfo' -ErrorAction Stop
            foreach ($line in $meminfo) {
                if ($line -match '^MemTotal:\s+(\d+)\s+kB') {
                    $kb = [long]$Matches[1]
                    return [math]::Round(($kb * 1024) / 1GB, 2)
                }
            }
        } catch {
            return 0
        }
        return 0
    }

    return 0
}


# ----------------------------------------------------------------------
# 11) Test-KBAISIPStatus
# ----------------------------------------------------------------------

function Test-KBAISIPStatus {
    <#
    .SYNOPSIS
      macOS System Integrity Protection 状态(其他平台返回 N/A)。
    .OUTPUTS
      [hashtable] @{ Enabled = [bool]; Status = [string] }
    .NOTES
      SIP 关闭会让 Docker Desktop 行为异常;precheck 用此函数做非阻断警告。
    #>
    [CmdletBinding()]
    param()

    if ((Get-KBAIPlatform) -ne 'macOS') {
        return @{ Enabled = $true; Status = 'N/A' }
    }

    try {
        $output = (& csrutil status 2>&1 | Out-String)
        if ($output -match 'enabled') {
            return @{ Enabled = $true; Status = 'enabled' }
        } elseif ($output -match 'disabled') {
            return @{ Enabled = $false; Status = 'disabled' }
        }
    } catch {
        return @{ Enabled = $true; Status = 'unknown' }
    }

    return @{ Enabled = $true; Status = 'unknown' }
}


# ----------------------------------------------------------------------
# dot-source 守卫:被 dot-source 时仅暴露函数,跳过主流程
# ----------------------------------------------------------------------

if ($MyInvocation.InvocationName -eq '.') {
    return
}

# ----------------------------------------------------------------------
# CLI 模式:打印当前平台 + 关键信息(便于 shell 拼装 / 调试)
# ----------------------------------------------------------------------

Write-Host "[platform-utils] 平台检测:$(Get-KBAIPlatform)"
Write-Host "[platform-utils] OS 版本:$(Get-KBAIOSVersion)"
Write-Host "[platform-utils] 内存:$(Get-KBAIMemoryGB) GB"
Write-Host "[platform-utils] CPU 虚拟化:$(Get-KBAICpuVirtualization.Detail)"
exit 0
