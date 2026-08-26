# =====================================================================
# KB-AI · CertaintyTagger 单元验收
# 用途: 验证事实/观点/草稿标签规则(v0.8.2 P2 生成层)
# 运行:  pwsh -File tests/test_certainty.ps1
# =====================================================================

$ErrorActionPreference = 'Stop'
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RootDir = Split-Path -Parent $ScriptDir

. (Join-Path $RootDir 'scripts/lib/CertaintyTagger.ps1')

function Write-Pass { param($msg) Write-Host "[PASS] $msg" -ForegroundColor Green }
function Write-Fail { param($msg) Write-Host "[FAIL] $msg" -ForegroundColor Red }
function Write-Info { param($msg) Write-Host "[INFO] $msg" -ForegroundColor Cyan }

$Failed = 0
$Total  = 0

function Assert-Equal {
    param($Actual, $Expected, $Name)
    $script:Total++
    if ($Actual -eq $Expected) {
        Write-Pass "$Name -> '$Expected'"
    } else {
        Write-Fail "$Name 期望 '$Expected', 实际 '$Actual'"
        $script:Failed++
    }
}

Write-Host ""
Write-Host "============================================================" -ForegroundColor Yellow
Write-Host "  KB-AI CertaintyTagger 验收" -ForegroundColor Yellow
Write-Host "  Root: $RootDir" -ForegroundColor Yellow
Write-Host "  Run:  $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" -ForegroundColor Yellow
Write-Host "============================================================" -ForegroundColor Yellow
Write-Host ""

# 1. 事实:含数字与指标
Assert-Equal -Actual (Get-Certainty -Text "2024年11月会员新增3200人,储值18.6万元,核销率42%。") -Expected "fact" -Name "事实-数字指标"

# 2. 事实:无主观词的客观描述(长度需超过30字阈值,且不含数字)
Assert-Equal -Actual (Get-Certainty -Text "示例海鲜酒楼位于深圳市南山区科技园,主营粤菜,门店装修风格为现代中式,适合商务宴请。") -Expected "neutral" -Name "事实-客观描述默认neutral"

# 3. 观点:建议型
Assert-Equal -Actual (Get-Certainty -Text "我建议优先优化储值激励方案,并加强员工培训,让员工更熟悉会员权益和操作流程。") -Expected "opinion" -Name "观点-建议"

# 4. 观点:可能性判断
Assert-Equal -Actual (Get-Certainty -Text "这次活动如果执行到位,可能会带来20%左右的客流增长,但具体效果还要看落地情况。") -Expected "opinion" -Name "观点-可能性"

# 5. 观点优先于事实(单数字)
Assert-Equal -Actual (Get-Certainty -Text "我认为 5% 的月度转化率对于新上线门店来说,已经是一个可以接受的水平。") -Expected "opinion" -Name "观点优先-单数字"

# 6. 事实优先于观点(多数字)
Assert-Equal -Actual (Get-Certainty -Text "建议目标:11月新增5000会员,储值30万元,核销率提升至50%。") -Expected "fact" -Name "事实优先-多数字"

# 7. 草稿:过短
Assert-Equal -Actual (Get-Certainty -Text "待补充") -Expected "draft" -Name "草稿-过短"

# 8. 草稿:标记词
Assert-Equal -Actual (Get-Certainty -Text "这里还需要再确认一下具体数字(TODO)。") -Expected "draft" -Name "草稿-标记词"

# 9. 统计功能
$chunks = @(
    @{ meta = @{ certainty = 'fact' } },
    @{ meta = @{ certainty = 'opinion' } },
    @{ meta = @{ certainty = 'fact' } },
    @{ meta = @{ certainty = 'draft' } }
)
$stats = Get-CertaintyStats -Chunks $chunks
Assert-Equal -Actual $stats.total -Expected 4 -Name "统计-总数"
Assert-Equal -Actual $stats.fact -Expected 2 -Name "统计-fact数"
Assert-Equal -Actual $stats.opinion -Expected 1 -Name "统计-opinion数"
Assert-Equal -Actual $stats.draft -Expected 1 -Name "统计-draft数"

Write-Host ""
Write-Host "============================================================" -ForegroundColor Yellow
if ($Failed -eq 0) {
    Write-Host "  [ALL PASS] $Total/$Total 通过" -ForegroundColor Green
} else {
    Write-Host "  [FAIL] $Failed/$Total 失败" -ForegroundColor Red
}
Write-Host "============================================================" -ForegroundColor Yellow
Write-Host ""

exit $Failed
