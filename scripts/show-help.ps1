<#
.SYNOPSIS
  KB-AI · 终端命令速查(总览)

.DESCRIPTION
  ### 用途
    第一次接触 KB-AI 的用户在终端敲 `pwsh -File scripts/show-help.ps1`,
    一屏看到所有可用的命令 + 用途 + 用法示例。

  ### 设计原则
    - 极简:不依赖外部 README / Web UI,完全离线
    - 中文:i18n zh-CN
    - ASCII 兼容:终端宽度 80 字符,无 Unicode 全角符号(banner 用 ─)
    - 数据源:Get-UsbRoot 找根,再读 scripts/ 目录列 .ps1 / 顶层 .bat
    - 退出码:0 成功;非 0 表示目录扫描异常

  ### 输出示例(实际内容动态生成):
      KB-AI 终端命令速查
      ────────────────────────────────────────────
      启动  start.bat          启动 Dify + Qdrant + MinerU
      停止  stop.bat           停止全部容器(SQLite 已落盘)
      对话  chat.ps1           进入 AI 问答(单轮 / 多轮)
      弹出  safe-eject.ps1     安全弹出 U 盘(5 秒倒计时)
      状态  status-bar.ps1     实时状态(ONLINE/OFFLINE/Credits)
      容量  disk-alert.ps1     U 盘容量 5 级告警
      索引  show-help.ps1      本帮助页
      版本  version.ps1        版本 + 健康度 1 行总览
      ────────────────────────────────────────────
      详细:打开 README.md  ·  数据:<root>/data

.OUTPUTS
  None(直接 Write-Host 到 stdout)

.NOTES
  PowerShell 5.1 兼容;UTF-8 无 BOM。
  无外部依赖(纯 Get-ChildItem + Get-UsbRoot dot-source)。
#>

[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"

# ----------------------------------------------------------------------
# 路径解析(用 Get-UsbRoot 跨平台定位)
# ----------------------------------------------------------------------

. (Join-Path $PSScriptRoot 'get-usb-root.ps1')
$RootDir = Get-UsbRoot

# ----------------------------------------------------------------------
# 命令清单(可后续 PR 维护)
# ----------------------------------------------------------------------

$Commands = @(
    @{ Verb = "启动"; Cmd = "start.bat";          Desc = "启动 Dify + Qdrant + MinerU" },
    @{ Verb = "停止"; Cmd = "stop.bat";           Desc = "停止全部容器(SQLite 已落盘)" },
    @{ Verb = "对话"; Cmd = "chat.ps1";           Desc = "进入 AI 问答(单轮 / 多轮)" },
    @{ Verb = "弹出"; Cmd = "safe-eject.ps1";     Desc = "安全弹出 U 盘(5 秒倒计时)" },
    @{ Verb = "状态"; Cmd = "status-bar.ps1";     Desc = "实时状态(ONLINE/OFFLINE/Credits)" },
    @{ Verb = "容量"; Cmd = "disk-alert.ps1";     Desc = "U 盘容量 5 级告警" },
    @{ Verb = "版本"; Cmd = "version.ps1";        Desc = "版本 + 健康度 1 行总览" },
    @{ Verb = "索引"; Cmd = "show-help.ps1";      Desc = "本帮助页" }
)

# ----------------------------------------------------------------------
# 动态校验:已存在 → 绿色;缺失 → 灰色 (仅展示,不报错)
# ----------------------------------------------------------------------

function Get-CmdColor {
    param([string]$Root, [string]$CmdName)
    $p = if ($CmdName -match '\.bat$') {
        Join-Path $Root $CmdName
    } else {
        Join-Path (Join-Path $Root 'scripts') $CmdName
    }
    if (Test-Path -LiteralPath $p) { return "Green" } else { return "DarkGray" }
}

# ----------------------------------------------------------------------
# 渲染
# ----------------------------------------------------------------------

Write-Host ""
Write-Host "  KB-AI 终端命令速查" -ForegroundColor Cyan
Write-Host "  ----------------------------------------------------------" -ForegroundColor DarkCyan
Write-Host ""

foreach ($c in $Commands) {
    $color = Get-CmdColor -Root $RootDir -CmdName $c.Cmd
    $line = ("  {0}  {1,-18} {2}" -f $c.Verb, $c.Cmd, $c.Desc)
    Write-Host $line -ForegroundColor $color
}

Write-Host ""
Write-Host "  ----------------------------------------------------------" -ForegroundColor DarkCyan
Write-Host "  详细:打开 README.md  ·  数据:$RootDir\data" -ForegroundColor Gray
Write-Host ""

exit 0