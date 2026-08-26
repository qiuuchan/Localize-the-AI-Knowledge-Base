<#
.SYNOPSIS
  KB-AI · 轻量事实/观点/草稿标签器(v0.8.2 P2 生成层)

.DESCRIPTION
  基于规则启发式为每个 chunk 打上 certainty 标签:
  - fact:   包含可验证的客观信息(数字、日期、金额、指标词等)
  - opinion:包含主观判断或建议(我认为、建议、可能、应该等)
  - draft:  明显未完成的草稿或文本过短
  - neutral:以上均不命中(默认视为事实性描述)

  规则式设计的好处:零额外 LLM 调用、确定性高、成本低。
  后续可升级为 LLM 二阶段打标,但当前接口保持不变。

.NOTES
  PowerShell 5.1 兼容;不使用外部 NLP 库。
#>

$ErrorActionPreference = "Stop"

# ----------------------------------------------------------------------
# 信号词表
# ----------------------------------------------------------------------

# 事实信号:数字、日期、金额、指标、比例等客观表达
$script:FactSignals = @(
    # 数字/单位/货币
    '\d+', '元', '万元', '亿元', '¥', '\$', '%', '百分之', '百分点',
    # 日期/时间
    '\d{4}年', '\d{4}-\d{2}', '\d{4}/\d{2}', '\d{1,2}月', '\d{1,2}日',
    # 餐饮/经营指标
    '营收', '收入', '利润', '成本', '客单价', '人均', '翻台率', '上座率',
    '会员数', '新增会员', '复购率', '留存率', '转化率', '核销率',
    '曝光量', '点击量', '播放量', '点赞', '转发', '评论',
    '同比', '环比', '增长', '下降', '上升', '减少', '增加',
    # 数量/规模
    '家', '个', '人', '次', '单', '桌', '间', '项', '条', '份'
)

# 观点信号:主观判断、建议、推测
$script:OpinionSignals = @(
    '我认为', '我觉得', '我相信', '我判断', '我的看法', '个人观点',
    '建议', '我们建议', '推荐', '强烈建议', '不妨', '建议尝试', '值得',
    '可能', '也许', '大概', '或许', '应该', '应当', '最好', '优先',
    '需要', '必须', '务必', '关键', '重要', '核心', '尤其', '特别是',
    '更适合', '更有利', '更有效', '更好', '较差', '较优', '首选'
)

# 草稿信号:未完成、待确认、占位
$script:DraftSignals = @(
    'TODO', 'FIXME', '待确认', '待补充', '待完善', '待核实', '待讨论',
    '草案', '初稿', '草稿', '占位', '预留', '暂缺', '暂无', '未确定'
)

# ----------------------------------------------------------------------
# 内部辅助函数
# ----------------------------------------------------------------------

function Test-ContainsAny {
    <#
    .SYNOPSIS
      检查文本是否包含任一模式(支持正则)。
    #>
    param(
        [string]$Text,
        [string[]]$Patterns
    )
    if ([string]::IsNullOrWhiteSpace($Text)) { return $false }
    foreach ($p in $Patterns) {
        if ($Text -match $p) { return $true }
    }
    return $false
}

function Test-HasNumericEvidence {
    <#
    .SYNOPSIS
      检查文本是否包含可作为事实证据的数字/日期/百分比。
    #>
    param([string]$Text)
    if ([string]::IsNullOrWhiteSpace($Text)) { return $false }
    # 简单数字(排除单独的年份像 2024 这种可能泛滥,但保留百分比/金额)
    if ($Text -match '\d+\.?\d*\s*%') { return $true }
    if ($Text -match '\d+\.?\d*\s*[万亿]?元') { return $true }
    if ($Text -match '\d{4}[-/]\d{1,2}[-/]\d{1,2}') { return $true }
    if ($Text -match '\d+\s*个|\d+\s*人|\d+\s*家|\d+\s*次|\d+\s*单') { return $true }
    return $false
}

# ----------------------------------------------------------------------
# 公共函数
# ----------------------------------------------------------------------

function Get-Certainty {
    <#
    .SYNOPSIS
      根据文本内容返回 certainty 标签。
    .PARAMETER Text
      chunk 文本。
    .OUTPUTS
      "fact" | "opinion" | "draft" | "neutral"
    #>
    [CmdletBinding()]
    param([string]$Text)

    if ([string]::IsNullOrWhiteSpace($Text)) { return "draft" }

    $t = $Text.Trim()

    # 1. 草稿最优先(避免把 TODO 类短文本误判)
    if ($t.Length -lt 30 -or (Test-ContainsAny -Text $t -Patterns $script:DraftSignals)) {
        return "draft"
    }

    # 2. 事实信号:含数字/日期/金额/指标等客观证据
    $hasFact = (Test-ContainsAny -Text $t -Patterns $script:FactSignals) -or
               (Test-HasNumericEvidence -Text $t)

    # 3. 观点信号:含主观判断或建议
    $hasOpinion = Test-ContainsAny -Text $t -Patterns $script:OpinionSignals

    # 决策:事实证据强于主观信号 → fact; 否则 subjective 更强 → opinion
    if ($hasFact -and -not $hasOpinion) { return "fact" }
    if ($hasOpinion -and -not $hasFact) { return "opinion" }
    if ($hasFact -and $hasOpinion) {
        # 同时存在时,看哪种信号更密集。简单规则:观点词通常出现在句首/结论位置,
        # 若文本中数字证据不少于 2 处仍判为 fact,否则 opinion。
        $numericMatches = ([regex]::Matches($t, '\d+')).Count
        if ($numericMatches -ge 2) { return "fact" }
        return "opinion"
    }

    # 4. 默认:无明确主观信号的长文本视为事实性描述
    return "neutral"
}

function Get-CertaintyStats {
    <#
    .SYNOPSIS
      统计 chunk 列表的 certainty 分布。
    .PARAMETER Chunks
      chunk 对象数组(每个对象需有 meta.certainty)。
    #>
    [CmdletBinding()]
    param([array]$Chunks)
    $stats = @{ fact = 0; opinion = 0; draft = 0; neutral = 0; total = 0 }
    foreach ($c in $Chunks) {
        $stats.total++
        $cat = if ($c.meta -and $c.meta.certainty) { $c.meta.certainty } else { "neutral" }
        if (-not $stats.ContainsKey($cat)) { $cat = "neutral" }
        $stats[$cat]++
    }
    return $stats
}

# ----------------------------------------------------------------------
# dot-source 守卫
# ----------------------------------------------------------------------
if ($MyInvocation.InvocationName -eq '.') {
    return
}
