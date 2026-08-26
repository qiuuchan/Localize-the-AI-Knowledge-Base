<#
.SYNOPSIS
  KB-AI · 轻量分词公共库(v0.7.2 Hybrid Search)

.DESCRIPTION
  为关键词倒排索引提供零依赖分词。
  - 中文(CJK)按单字切分,使"宫保""鸡丁"都能单独命中
  - 英文/数字按非字母数字字符分割
  - 过滤停用词与空/过短/过长 token
  - 返回结果去重

.NOTES
  PowerShell 5.1 兼容;不使用任何外部 NLP 库。
#>

$ErrorActionPreference = "Stop"

# ----------------------------------------------------------------------
# 停用词表(保持最小集,避免误伤专业术语)
# ----------------------------------------------------------------------
$script:StopWords = @(
    # 中文常见停用词
    '的','是','了','在','和','或','我','你','他','它','们','这','那','有','个',
    '为','之','与','及','等','从','到','对','给','就','让','向','往','于','而',
    '但','也','都','要','会','能','可','很','非常','比较','以及','还是','或者',
    '什么','怎么','怎样','如何','哪些','哪个','谁','哪','吗','呢','吧','啊','哦','嗯'
    # 英文常见停用词
    'the','a','an','is','are','was','were','be','been','being','have','has','had',
    'do','does','did','will','would','could','should','may','might','must','can',
    'this','that','these','those','i','you','he','she','it','we','they','me','him',
    'her','us','them','my','your','his','its','our','their','and','or','but','in',
    'on','at','to','for','of','with','by','from','as','about','into','through',
    'during','before','after','above','below','between','under','again','further',
    'then','once','here','there','when','where','why','how','all','any','both',
    'each','few','more','most','other','some','such','no','nor','not','only','own',
    'same','so','than','too','very','just'
)

function Get-Tokens {
    <#
    .SYNOPSIS
      对文本进行轻量分词。
    .PARAMETER Text
      输入文本。
    .PARAMETER MinLength
      token 最小长度(默认 1)。
    .PARAMETER MaxLength
      token 最大长度(默认 32)。
    .OUTPUTS
      string[] 去重后的 token 数组(保持首次出现顺序)。
    #>
    [CmdletBinding()]
    param(
        [string]$Text,
        [int]$MinLength = 1,
        [int]$MaxLength = 32
    )
    if ([string]::IsNullOrWhiteSpace($Text)) { return @() }

    $tokens = New-Object System.Collections.Generic.List[string]
    $lowerText = $Text.ToLowerInvariant()

    # 英文/数字:按非字母数字字符分割
    $alnumParts = [regex]::Split($lowerText, '[^a-z0-9]+')
    foreach ($part in $alnumParts) {
        $p = $part.Trim()
        if ($p.Length -lt $MinLength -or $p.Length -gt $MaxLength) { continue }
        if ($script:StopWords -contains $p) { continue }
        if (-not $tokens.Contains($p)) { [void]$tokens.Add($p) }
    }

    # 中文(CJK):按单字切分
    for ($i = 0; $i -lt $lowerText.Length; $i++) {
        $ch = $lowerText[$i]
        $code = [int][char]$ch
        $isCjk = ($code -ge 0x4E00 -and $code -le 0x9FFF) -or
                 ($code -ge 0x3400 -and $code -le 0x4DBF) -or
                 ($code -ge 0xF900 -and $code -le 0xFAFF)
        if (-not $isCjk) { continue }
        if ($script:StopWords -contains $ch) { continue }
        if (-not $tokens.Contains($ch)) { [void]$tokens.Add($ch) }
    }

    return ,$tokens.ToArray()
}

function Get-TopTokens {
    <#
    .SYNOPSIS
      对文本分词并限制最大 token 数(查询侧使用,避免 SQL IN 子句过长)。
    .PARAMETER Text
      输入文本。
    .PARAMETER MaxN
      最大返回 token 数(默认 20)。
    #>
    [CmdletBinding()]
    param(
        [string]$Text,
        [int]$MaxN = 20
    )
    $all = Get-Tokens -Text $Text
    if ($all.Count -eq 0) { return @() }
    if ($all.Count -le $MaxN) { return ,$all }
    return ,$all[0..($MaxN - 1)]
}

# ----------------------------------------------------------------------
# dot-source 守卫
# ----------------------------------------------------------------------
if ($MyInvocation.InvocationName -eq '.') {
    return
}
