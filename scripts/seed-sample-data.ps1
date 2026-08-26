<#
.SYNOPSIS
  上传 1-2 个示例 docx 到 data/samples/,调 parse + embed-and-ingest,验证端到端可跑通。

.DESCRIPTION
  步骤:
    1. 检查 docker / qdrant / mineru 容器是否启动(若没起 → 提示用户先跑 start.bat)
    2. 把内置示例 txt 复制到 data/samples/(无需依赖外部 docx 资源)
    3. parse-doc.ps1 → cache/parsed/<doc-id>/chunks.jsonl
    4. embed-and-ingest.ps1 → Qdrant collection
    5. 可选:用 chat.ps1 跑 1-2 个示例问题,确认可检索到内容

.PARAMETER SampleName
  可选:示例文件名(不带后缀);缺省 "餐饮经营手册"。

.PARAMETER Collection
  可选:Qdrant collection 名;缺省 "kb_ai_chunks"。

.PARAMETER SkipChat
  开关:跳过末尾 chat 演示。

.EXAMPLE
  pwsh -File scripts/seed-sample-data.ps1

.NOTES
  - PowerShell 7+ 兼容
  - 不会自动启动 docker compose(留给 start.bat)
#>

[CmdletBinding()]
param(
    [string]$SampleName = "餐饮经营手册",
    [string]$Collection = "kb_ai_chunks",
    [switch]$SkipChat = $false
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "Continue"

# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------

function Write-Step { param([string]$Msg) Write-Host "[$(Get-Date -Format 'HH:mm:ss')] $Msg" -ForegroundColor Cyan }
function Write-Warn { param([string]$Msg) Write-Host "[$(Get-Date -Format 'HH:mm:ss')] [WARN] $Msg" -ForegroundColor Yellow }
function Write-Err  { param([string]$Msg) Write-Host "[$(Get-Date -Format 'HH:mm:ss')] [ERROR] $Msg" -ForegroundColor Red }

function Write-Utf8NoBom {
    param([string]$Path, [string]$Content)
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($Path, $Content, $utf8NoBom)
}

# ----------------------------------------------------------------------
# 路径 + 容器检查
# ----------------------------------------------------------------------

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$rootDir = Split-Path -Parent $scriptDir
$samplesDir = Join-Path $rootDir "data\samples"
$cacheDir = Join-Path $rootDir "cache\parsed"
$envPath = Join-Path $rootDir ".env"

# 1. 检查 docker 是否启动
Write-Step "[1/5] 检查 Docker 容器状态"
$dockerOk = $false
try {
    $null = docker info 2>&1
    if ($LASTEXITCODE -eq 0) { $dockerOk = $true }
} catch { }
if (-not $dockerOk) {
    Write-Err "Docker Desktop 未运行,请先双击 start.bat"
    exit 1
}

# 2. 检查 Qdrant 容器是否 healthy
$qdrantOk = $false
try {
    $null = docker ps --filter "name=kb-ai-qdrant" --filter "status=running" --format "{{.Names}}" 2>&1
    if ($LASTEXITCODE -eq 0 -and ($null -match "kb-ai-qdrant")) {
        $qdrantOk = $true
    }
} catch { }
if (-not $qdrantOk) {
    Write-Warn "Qdrant 容器未运行;请先双击 start.bat"
    $confirm = Read-Host "是否继续(只生成示例文件,不实际入库)? [y/N]"
    if ($confirm -ne "y") { exit 1 }
}

# 3. 检查 .env
if (-not (Test-Path $envPath)) {
    Write-Err "找不到 .env 文件,请先复制 .env.example 并填入 ALIYUN_BAILIAN_API_KEY"
    exit 1
}

# ----------------------------------------------------------------------
# 生成示例 txt(避免依赖外部 docx 资源;后续若需要真 docx 可手拖进来)
# ----------------------------------------------------------------------

if (-not (Test-Path $samplesDir)) {
    New-Item -ItemType Directory -Force -Path $samplesDir | Out-Null
}

$sampleTxtPath = Join-Path $samplesDir "$SampleName.txt"
$sampleContent = @"
# 餐饮分公司经营手册(示例数据)

## §1 门店 SOP

### §1.1 早班流程
1. 7:00 到店,开灯开空调
2. 检查食材新鲜度(蔬菜、肉类、海鲜分区检查)
3. 擦拭桌椅、地面、台面
4. 准备当日食材、半成品
5. 7:30 员工到位,开早会(5 分钟)
6. 8:00 开门营业

### §1.2 晚班流程
1. 17:00 开始准备晚市
2. 19:00-21:00 高峰期,全员在前厅
3. 21:30 开始清场
4. 22:00 打烊盘点
5. 22:30 关灯关门,员工下班

## §2 菜品标准化

### §2.1 招牌菜:红烧肉
- 原料:五花肉 500g、老抽 30ml、冰糖 20g、八角 2 颗
- 步骤:
  1. 五花肉切 3cm 见方块,冷水下锅焯水
  2. 热锅冷油,下冰糖小火炒至枣红色
  3. 下肉块翻炒上色
  4. 加老抽、热水、八角,大火烧开转小火炖 60 分钟
  5. 大火收汁,出锅

### §2.2 招牌菜:宫保鸡丁
- 原料:鸡腿肉 300g、花生米 50g、干辣椒 10g、花椒 5g
- 步骤:
  1. 鸡腿肉切丁,用料酒、生抽、淀粉腌 15 分钟
  2. 热锅宽油,下鸡丁滑炒至变色盛出
  3. 锅内留底油,下干辣椒、花椒爆香
  4. 下鸡丁、花生米、葱白翻炒
  5. 加调味料(糖、醋、生抽)勾薄芡出锅

## §3 员工培训

### §3.1 新员工入职
- 第 1 周:熟悉店面 + 跟岗学习
- 第 2 周:上手简单岗位(传菜、收银)
- 第 3 周:上手主岗位(切配、炒锅)
- 第 4 周:考核 + 定岗

### §3.2 服务态度
- 主动招呼、微笑服务
- 投诉处理三步法:倾听 → 致歉 → 解决
- 不与顾客争辩

## §4 营销话术

### §4.1 顾客说"菜太咸"
- 不对的回:「那是你口味重」→ 引起冲突
- 正确的回:「抱歉,我让后厨再给您做一份,马上来」→ 解决

### §4.2 顾客要求打折
- 不对的回:「不能打折」→ 失去顾客
- 正确的回:「今天这单给您免单小菜,下次再来我给您申请会员价」→ 留住顾客

## §5 监管合规

### §5.1 食品安全
- 食材采购:必须从有资质的供应商进货,留采购凭证 ≥ 2 年
- 食材储存:生熟分开,冷藏 ≤ 4°C,冷冻 ≤ -18°C
- 食品加工:中心温度 ≥ 70°C,烧熟煮透
- 餐具消毒:蒸汽消毒 ≥ 100°C 10 分钟,或消毒柜 ≥ 120°C 15 分钟

### §5.2 消防安全
- 每月检查灭火器压力
- 每季度演练一次疏散
- 厨房油烟机每周清洗
- 员工人人会使用灭火器
"@

Write-Step "[2/5] 写入示例数据: $sampleTxtPath"
Write-Utf8NoBom -Path $sampleTxtPath -Content $sampleContent

# 也再放一份 markdown(.md 后缀,parse-doc 直接读)
$sampleMdPath = Join-Path $samplesDir "$SampleName.md"
Write-Utf8NoBom -Path $sampleMdPath -Content $sampleContent
Write-Step "  → $sampleMdPath"

# ----------------------------------------------------------------------
# 解析
# ----------------------------------------------------------------------

Write-Step "[3/5] 解析示例文档(parse-doc.ps1)"
$parseScript = Join-Path $scriptDir "parse-doc.ps1"
$parsedDocId = (Get-FileHash -Algorithm SHA256 -Path $sampleTxtPath).Hash.Substring(0, 16)
$chunksPath = Join-Path $cacheDir "$parsedDocId\chunks.jsonl"

# 修复 2.11:去除 `"$parseScript"` 等字面引号,让 PowerShell 自动转义(原写法:路径含空格时 pwsh 拆错)
$parseArgs = @(
    "-NoProfile", "-File", $parseScript,
    "-InputFile", $sampleTxtPath,
    "-OutputDir", $cacheDir,
    "-DocId", $parsedDocId
)
$parseCmd = "pwsh $($parseArgs -join ' ')"
Write-Step "  cmd: $parseCmd"
& pwsh @parseArgs
if ($LASTEXITCODE -ne 0) {
    Write-Err "parse-doc.ps1 失败"
    exit 1
}

# ----------------------------------------------------------------------
# Embedding + 入库
# ----------------------------------------------------------------------

if ($qdrantOk) {
    Write-Step "[4/5] Embedding + 入库(embed-and-ingest.ps1)"
    $embedScript = Join-Path $scriptDir "embed-and-ingest.ps1"
    # 修复 2.11:同 parseArgs 修复,去除字面引号
    $embedArgs = @(
        "-NoProfile", "-File", $embedScript,
        "-ChunksFile", $chunksPath,
        "-Collection", $Collection
    )
    & pwsh @embedArgs
    if ($LASTEXITCODE -ne 0) {
        Write-Err "embed-and-ingest.ps1 失败"
        exit 1
    }
} else {
    Write-Warn "[4/5] 跳过 Embedding + 入库(Qdrant 未起)"
}

# ----------------------------------------------------------------------
# 可选 chat 演示
# ----------------------------------------------------------------------

if (-not $SkipChat -and $qdrantOk) {
    Write-Step "[5/5] 示例问答演示(chat.ps1)"
    $chatScript = Join-Path $scriptDir "chat.ps1"
    $chatArgs = @(
        "-NoProfile", "-File", "`"$chatScript`"",
        "-Question", "`"招牌菜红烧肉怎么做?`"",
        "-Collection", "`"$Collection`""
    )
    & pwsh @chatArgs
    if ($LASTEXITCODE -ne 0) {
        Write-Warn "chat.ps1 演示失败(可能 API Key 无效)"
    }
} else {
    Write-Step "[5/5] 跳过 chat 演示(SkipChat 或 Qdrant 未起)"
}

Write-Host ""
Write-Host "============================================================" -ForegroundColor Green
Write-Host "  示例数据 seed 完成" -ForegroundColor Green
Write-Host "  - 文档:$sampleTxtPath" -ForegroundColor Green
Write-Host "  - Chunks:$chunksPath" -ForegroundColor Green
if ($qdrantOk) {
    Write-Host "  - Qdrant collection: $Collection" -ForegroundColor Green
    if (-not $SkipChat) {
        Write-Host "  - 已用 chat.ps1 跑 1 个示例问题" -ForegroundColor Green
    }
}
Write-Host ""
Write-Host "  下一步可手动尝试:" -ForegroundColor Yellow
Write-Host "    pwsh -File scripts/chat.ps1 -Question '员工培训怎么安排?' -Collection '$Collection'" -ForegroundColor Yellow
Write-Host "============================================================" -ForegroundColor Green

exit 0