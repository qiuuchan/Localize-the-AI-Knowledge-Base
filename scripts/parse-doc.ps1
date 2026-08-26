<#
.SYNOPSIS
  解析 .docx/.pdf/.pptx/.xlsx → markdown chunks,供 embed-and-ingest.ps1 入库。

.DESCRIPTION
  - .docx  → pandoc(MinerU 不擅长 docx)
  - .pdf   → MinerU 容器 HTTP API(MinerU 8001 端口);失败回退 pandoc
  - .pptx  → MinerU 容器 HTTP API;失败回退 python-pptx → 文本
  - .xlsx  → openpyxl → 每个 sheet 一段 markdown 表
  - .txt / .md → 直接读
  - chunks 按段落/表格切片;每片附 source 标注(文件名 + §段号)

.PARAMETER InputFile
  必填:待解析的源文件绝对路径(.docx/.pdf/.pptx/.xlsx/.txt/.md)。

.PARAMETER OutputDir
  必填:输出目录,会创建 <OutputDir>\<doc-id>\chunks.jsonl
       每行一个 chunk: {"id":"...","text":"...","source":"...","meta":{...}}

.PARAMETER DocId
  可选:文档唯一 ID;缺省 = sha256(absolute path)[:16]。

.PARAMETER MineruUrl
  可选:MinerU HTTP 服务地址;缺省 http://localhost:8001。

.PARAMETER UseCache
  开关:开启后若 chunks.jsonl 已存在则跳过解析(幂等)。

.EXAMPLE
  pwsh -File scripts/parse-doc.ps1 `
       -InputFile "<private>\KB-AI\data\samples\经营手册.docx" `
       -OutputDir "<private>\KB-AI\cache\parsed"

.NOTES
  - PowerShell 7+ 兼容(utf8NoBOM 编码输出)
  - pandoc / python-pptx / openpyxl 需预装(PowerShell 默认无;文档说明)
  - MinerU 通过 Docker 容器运行(8001 端口)
  - 不依赖真实 API,可作为离线工具调用(嵌入了 mock 入口供测试)
#>

[CmdletBinding()]
param(
    [string]$InputFile = "",
    [string]$OutputDir = "",
    [string]$DocId,
    [string]$MineruUrl = "http://localhost:8001",
    [switch]$UseCache = $false,
    [switch]$NoMineruPdf = $false,
    [switch]$NoMineruPptx = $false,
    [string]$CaptionModel = "qwen-vl-max"
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "Continue"

# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------

function Write-Step {
    param([string]$Msg)
    Write-Host "[$(Get-Date -Format 'HH:mm:ss')] $Msg" -ForegroundColor Cyan
}

function Write-Warn {
    param([string]$Msg)
    Write-Host "[$(Get-Date -Format 'HH:mm:ss')] [WARN] $Msg" -ForegroundColor Yellow
}

function Write-Err {
    param([string]$Msg)
    Write-Host "[$(Get-Date -Format 'HH:mm:ss')] [ERROR] $Msg" -ForegroundColor Red
}

function Get-Sha256Short {
    param([string]$Text, [int]$Len = 16)
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($Text)
    $sha = [System.Security.Cryptography.SHA256]::Create()
    $hash = $sha.ComputeHash($bytes)
    $sb = New-Object System.Text.StringBuilder
    foreach ($b in $hash) {
        [void]$sb.Append($b.ToString("x2"))
    }
    return $sb.ToString().Substring(0, $Len)
}

function Ensure-Dir {
    param([string]$Path)
    if (-not (Test-Path $Path)) {
        New-Item -ItemType Directory -Force -Path $Path | Out-Null
    }
}

# 写入 UTF-8 no BOM
function Write-Utf8NoBom {
    param([string]$Path, [string]$Content)
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($Path, $Content, $utf8NoBom)
}

# 追加行到文件(UTF-8 no BOM)
function Add-Utf8NoBomLine {
    param([string]$Path, [string]$Line)
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    if (-not (Test-Path $Path)) {
        [System.IO.File]::WriteAllText($Path, $Line + "`n", $utf8NoBom)
    } else {
        [System.IO.File]::AppendAllText($Path, $Line + "`n", $utf8NoBom)
    }
}

# T-RAG-7: 防御性 chunk 长度保护(embedding 接口上限 8192,留余量 4000)
function Split-LongChunks {
    param(
        [System.Collections.Generic.List[object]]$Chunks,
        [int]$MaxLen = 4000
    )
    $out = New-Object System.Collections.Generic.List[object]
    foreach ($c in $Chunks) {
        $txt = $c.text
        if ($txt.Length -le $MaxLen) {
            [void]$out.Add($c)
            continue
        }
        # 按行拆分,尽量保持语义
        $lines = $txt -split "`r?`n"
        $buf = New-Object System.Text.StringBuilder
        $seq = 0
        function local:Flush-Chunk {
            if ($buf.Length -eq 0) { return }
            $piece = $buf.ToString().Trim()
            if ([string]::IsNullOrWhiteSpace($piece)) { [void]$buf.Clear(); return }
            $seq++
            $newMeta = @{}
            foreach ($k in $c.meta.Keys) { $newMeta[$k] = $c.meta[$k] }
            $newMeta['chunk_type'] = ($newMeta['chunk_type'] + '_split').Trim('_')
            [void]$out.Add(@{
                id     = (Get-Sha256Short "$($c.id)|split|$seq|$piece")
                text   = $piece
                source = $c.source
                meta   = $newMeta
            })
            [void]$buf.Clear()
        }
        foreach ($ln in $lines) {
            if (($buf.Length + $ln.Length + 2) -gt $MaxLen) {
                Flush-Chunk
            }
            [void]$buf.AppendLine($ln)
        }
        Flush-Chunk
    }
    return ,$out
}

# ----------------------------------------------------------------------
# MinerU HTTP 调用(8001 端口,容器内 http://localhost:8001)
# ----------------------------------------------------------------------

function Test-MineruReachable {
    param([string]$Url)
    try {
        $r = Invoke-WebRequest -Uri "$Url/health" -Method Get -TimeoutSec 5 -UseBasicParsing -ErrorAction Stop
        return ($r.StatusCode -eq 200)
    } catch {
        return $false
    }
}

function Invoke-MineruParse {
    <#
    .SYNOPSIS  调 MinerU HTTP API(8001 端口)解析 PDF/PPT;返回 markdown 文本
    #>
    param(
        [Parameter(Mandatory = $true)] [string]$FilePath,
        [Parameter(Mandatory = $true)] [string]$Url
    )
    # 修复 1.7:大文件内存爆炸保护(MinerU 走 ReadAllBytes → Base64 → JSON,完整文件 +
    # 多个字符串副本同时驻留内存,500MB 文件可能瞬时占用数 GB)
    $maxBytes = 200MB
    $fileInfo = Get-Item -LiteralPath $FilePath
    if ($fileInfo.Length -gt $maxBytes) {
        throw "文件过大($([math]::Round($fileInfo.Length / 1MB, 1)) MB > 200 MB),MinerU 路径暂不支持(避免内存爆炸)。请先拆分文档"
    }
    $bytes = [System.IO.File]::ReadAllBytes($FilePath)
    $b64 = [Convert]::ToBase64String($bytes)
    $body = @{
        file = $b64
        backend = "pipeline"
        parse_method = "auto"
        language = "ch"
    } | ConvertTo-Json -Depth 5

    $headers = @{ "Content-Type" = "application/json" }
    $resp = Invoke-WebRequest -Uri "$Url/file_parse" -Method Post `
             -Headers $headers -Body $body -TimeoutSec 3600 -UseBasicParsing
    if ($resp.StatusCode -ne 200) {
        throw "MinerU 返回 HTTP $($resp.StatusCode)"
    }
    $j = $resp.Content | ConvertFrom-Json
    # MinerU 响应含 md / content 字段,这里取 md;若无则 fallback content
    if ($j.md) { return $j.md }
    if ($j.content) { return ($j.content -join "`n") }
    throw "MinerU 响应格式异常,既无 md 也无 content"
}

# ----------------------------------------------------------------------
# pandoc(.docx fallback)
# ----------------------------------------------------------------------

function Invoke-PandocConvert {
    param([string]$FilePath, [string]$Format = "docx")
    $pandoc = Get-Command pandoc -ErrorAction SilentlyContinue
    $pandocExe = $null
    if ($pandoc) {
        $pandocExe = $pandoc.Source
    } elseif (Test-Path "E:\tools\pandoc\pandoc.exe") {
        $pandocExe = "E:\tools\pandoc\pandoc.exe"
    }
    if (-not $pandocExe) {
        throw "pandoc 未安装;请先安装 pandoc(https://pandoc.org/)"
    }
    $args = @($FilePath, "-t", "markdown", "--wrap=none")
    $out = & $pandocExe @args 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "pandoc 退出码 ${LASTEXITCODE}:`n$out"
    }
    return ($out -join "`n")
}

# ----------------------------------------------------------------------
# Office COM 转换(.doc → .docx / .ppt → .pptx)
# 依赖本机已安装的 Microsoft Word / PowerPoint
# ----------------------------------------------------------------------
function Convert-OfficeFormatViaCom {
    param([string]$FilePath, [string]$TargetExt)
    $comName = switch ($TargetExt.ToLower()) {
        ".docx" { "Word.Application" }
        ".pptx" { "PowerPoint.Application" }
        default { throw "不支持的 COM 转换目标格式: $TargetExt" }
    }
    $app = $null
    $doc = $null
    $tmpFile = [System.IO.Path]::Combine(
        [System.IO.Path]::GetTempPath(),
        ([System.IO.Path]::GetFileNameWithoutExtension($FilePath) + "_" + [Guid]::NewGuid().ToString("N").Substring(0, 8) + $TargetExt)
    )
    try {
        $app = New-Object -ComObject $comName -ErrorAction Stop
        $app.Visible = $false
        $app.DisplayAlerts = 0  # ppAlertsNone / wdAlertsNone
        switch ($TargetExt.ToLower()) {
            ".docx" {
                $doc = $app.Documents.Open($FilePath, $false, $true)
                # FileFormat=16 = wdFormatXMLDocument (.docx)
                $doc.SaveAs2($tmpFile, 16)
            }
            ".pptx" {
                $doc = $app.Presentations.Open($FilePath, $true, $false, $false)
                # FileFormat=11 = ppSaveAsOpenXMLPresentation
                $doc.SaveAs($tmpFile, 11)
            }
        }
        return $tmpFile
    } catch {
        throw "Office COM 转换失败($comName): $_"
    } finally {
        if ($doc) { try { $doc.Close() } catch {} }
        if ($app) { try { $app.Quit() } catch {} }
        [System.GC]::Collect()
        [System.GC]::WaitForPendingFinalizers()
    }
}

# ----------------------------------------------------------------------
# pdftotext(PDF 快速回退;MinerU 太慢或不可用)
# ----------------------------------------------------------------------
function Invoke-PdfTextFallback {
    param([string]$FilePath)
    $candidates = @(
        (Get-Command pdftotext -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source),
        "E:\tools\poppler\bin\pdftotext.exe",
        "D:\pjz-learn\Git\mingw64\bin\pdftotext.exe"
    )
    $exe = $candidates | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1
    if (-not $exe) {
        throw "pdftotext 未找到;请安装 poppler-utils 或把 pdftotext.exe 放到 PATH"
    }
    $oldEAP = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    $out = & $exe @("-layout", "-enc", "UTF-8", $FilePath, "-") 2>&1
    $ErrorActionPreference = $oldEAP
    if ($LASTEXITCODE -ne 0) {
        throw "pdftotext 退出码 ${LASTEXITCODE}:`n$out"
    }
    return ($out -join "`n")
}

# ----------------------------------------------------------------------
# python-pptx(回退 .pptx)
# ----------------------------------------------------------------------

function Invoke-PptxFallback {
    param([string]$FilePath)
    $py = Get-Command python -ErrorAction SilentlyContinue
    if (-not $py) { throw "python 未安装;无法回退解析 pptx" }
    $script = @'
import sys, zipfile, os, re, subprocess, tempfile, shutil, traceback
from xml.etree import ElementTree as ET

pptx = sys.argv[1]

def safe_cell_text(cell):
    try:
        if cell is None:
            return ""
        txt = cell.text
        return txt.replace("\n", " ").strip() if txt else ""
    except Exception:
        return ""

def safe_run_text(run):
    try:
        if run is None:
            return ""
        txt = run.text
        return txt if txt else ""
    except Exception:
        return ""

def extract_text_from_xml(xml_path):
    try:
        tree = ET.parse(xml_path)
        texts = []
        for elem in tree.iter():
            if elem.tag.endswith('}t') and elem.text:
                texts.append(elem.text)
        return ''.join(texts)
    except Exception:
        return ''

try:
    from pptx import Presentation
    p = Presentation(pptx)
    out = []
    for i, slide in enumerate(p.slides, 1):
        out.append(f"\n## Slide {i}\n")
        try:
            shapes = list(slide.shapes)
        except Exception as e:
            out.append(f"[解析本页形状失败: {e}]")
            continue
        for shape in shapes:
            if shape is None:
                continue
            try:
                if getattr(shape, 'has_text_frame', False):
                    tf = getattr(shape, 'text_frame', None)
                    if tf is not None:
                        try:
                            paras = list(tf.paragraphs)
                        except Exception:
                            paras = []
                        for para in paras:
                            if para is None:
                                continue
                            try:
                                runs = list(para.runs)
                            except Exception:
                                runs = []
                            txt = "".join(safe_run_text(r) for r in runs).strip()
                            if txt:
                                out.append(txt)
                if getattr(shape, 'has_table', False):
                    tbl = getattr(shape, 'table', None)
                    if tbl is not None:
                        try:
                            rows = list(tbl.rows)
                        except Exception:
                            rows = []
                        if rows:
                            try:
                                first_cells = list(rows[0].cells)
                                ncols = len(first_cells)
                            except Exception:
                                ncols = 0
                            if ncols > 0:
                                out.append("| " + " | ".join(["---"] * ncols) + " |")
                            for row in rows:
                                try:
                                    cells = list(row.cells)
                                except Exception:
                                    cells = []
                                if cells:
                                    out.append("| " + " | ".join(safe_cell_text(c) for c in cells) + " |")
            except Exception as e:
                # 单个 shape 失败不影响整页
                out.append(f"[解析形状失败: {e}]")
                continue
    result = "\n".join(out)
    if result.strip():
        print(result)
        sys.exit(0)
    else:
        print("python-pptx extracted no text", file=sys.stderr)
except Exception as e:
    print(f"python-pptx failed: {e}", file=sys.stderr)
    traceback.print_exc(file=sys.stderr)

# Fallback: unzip + parse slide XML(处理 CRC 损坏等异常)
tmpdir = tempfile.mkdtemp()
try:
    subprocess.run(["unzip", "-o", pptx, "-d", tmpdir], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    slides_dir = os.path.join(tmpdir, "ppt", "slides")
    if not os.path.isdir(slides_dir):
        raise Exception("No ppt/slides directory found; file may be severely corrupted")
    out = []
    for fname in sorted(os.listdir(slides_dir)):
        if fname.endswith('.xml'):
            slide_num = re.findall(r'\d+', fname)[0] if re.findall(r'\d+', fname) else fname
            txt = extract_text_from_xml(os.path.join(slides_dir, fname))
            if txt.strip():
                out.append(f"\n## Slide {slide_num}\n")
                out.append(txt)
    result = "\n".join(out)
    if not result.strip():
        raise Exception("unzip fallback extracted no text")
    print(result)
finally:
    shutil.rmtree(tmpdir, ignore_errors=True)
'@
    $tmpScript = [System.IO.Path]::GetTempFileName() + ".py"
    Write-Utf8NoBom -Path $tmpScript -Content $script
    try {
        $oldEAP = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        # 分别捕获 stdout / stderr,便于定位 python-pptx 内部错误
        $stdout = & python $tmpScript $FilePath 2> (Join-Path $env:TEMP "pptx_fallback_err.txt")
        $stderr = ""
        $errFile = Join-Path $env:TEMP "pptx_fallback_err.txt"
        if (Test-Path $errFile) {
            $stderr = Get-Content -LiteralPath $errFile -Raw -Encoding UTF8
            Remove-Item -Force -ErrorAction SilentlyContinue $errFile
        }
        $ErrorActionPreference = $oldEAP
        if ($LASTEXITCODE -ne 0) {
            throw "python-pptx/unzip 退出 ${LASTEXITCODE}; stderr:`n$stderr`nstdout:`n$stdout"
        }
        if ($stderr -and -not ($stdout -join "").Trim()) {
            # python 退出码 0 但只输出到 stderr,视为失败并暴露详细错误
            throw "python-pptx 未输出文本; stderr:`n$stderr"
        }
        return (($stdout -join "`n") + "`n" + $stderr).Trim()
    } finally {
        Remove-Item -Force -ErrorAction SilentlyContinue $tmpScript
    }
}

# ----------------------------------------------------------------------
# openpyxl(.xlsx)
# ----------------------------------------------------------------------

function Invoke-XlsxParse {
    param([string]$FilePath)
    $py = Get-Command python -ErrorAction SilentlyContinue
    if (-not $py) { throw "python 未安装;无法解析 xlsx" }
    $script = @'
import sys
from openpyxl import load_workbook
wb = load_workbook(sys.argv[1], data_only=True, read_only=True)
out = []
for sname in wb.sheetnames:
    ws = wb[sname]
    out.append(f"\n## Sheet: {sname}\n")
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        continue
    ncols = max(len(r) for r in rows)
    header = list(rows[0]) + [""] * (ncols - len(rows[0]))
    out.append("| " + " | ".join(str(c) if c is not None else "" for c in header) + " |")
    out.append("| " + " | ".join(["---"] * ncols) + " |")
    for row in rows[1:]:
        cells = list(row) + [""] * (ncols - len(row))
        out.append("| " + " | ".join(str(c) if c is not None else "" for c in cells) + " |")
print("\n".join(out))
'@
    $tmpScript = [System.IO.Path]::GetTempFileName() + ".py"
    Write-Utf8NoBom -Path $tmpScript -Content $script
    try {
        $oldEAP = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        $out = & python $tmpScript $FilePath 2>&1
        $ErrorActionPreference = $oldEAP
        if ($LASTEXITCODE -ne 0) {
            throw "openpyxl 退出 ${LASTEXITCODE}:`n$out"
        }
        return ($out -join "`n")
    } finally {
        Remove-Item -Force -ErrorAction SilentlyContinue $tmpScript
    }
}

# ----------------------------------------------------------------------
# 事实/观点标签(T-RAG-6 P2 生成层)
# ----------------------------------------------------------------------
. (Join-Path $PSScriptRoot 'lib/CertaintyTagger.ps1')

# ----------------------------------------------------------------------
# Markdown 标题切段(T-RAG-2):按 # / ## / ### 切大段,维护 header_path
# ----------------------------------------------------------------------

function Split-ByHeaders {
    <#
    .SYNOPSIS  按 markdown 标题切大段,返回 sections 列表(每段含 header_path / level / text)
    .DESCRIPTION
      - 维护 pathStack 模拟 heading 层级
      - 遇到 # → 推入栈顶;遇到 ## → pop 顶级 + 推入 ## 标题
      - 每段 text 包含 header 行本身(便于 chunk 上下文)
    #>
    param([string]$Text)

    $sections = New-Object System.Collections.Generic.List[object]
    $pathStack = New-Object System.Collections.Generic.List[string]
    $buf = New-Object System.Text.StringBuilder

    $lines = $Text -split "`r?`n"
    foreach ($line in $lines) {
        if ($line -match "^(#{1,6})\s+(.+)$") {
            # Flush 当前 buffer
            if ($buf.Length -gt 0) {
                $sections.Add(@{
                    header_path = ($pathStack -join " > ")
                    level       = if ($pathStack.Count -gt 0) { $pathStack.Count } else { 0 }
                    text        = $buf.ToString().TrimEnd()
                })
                [void]$buf.Clear()
            }
            # 更新 header path stack
            $level = $Matches[1].Length
            $title = $Matches[2].Trim()
            while ($pathStack.Count -ge $level) {
                $pathStack.RemoveAt($pathStack.Count - 1)
            }
            $pathStack.Add($title)
            # header 行作为新段的开头
            [void]$buf.AppendLine($line)
        } else {
            [void]$buf.AppendLine($line)
        }
    }
    # Flush trailing buffer
    if ($buf.Length -gt 0) {
        $sections.Add(@{
            header_path = ($pathStack -join " > ")
            level       = if ($pathStack.Count -gt 0) { $pathStack.Count } else { 0 }
            text        = $buf.ToString().TrimEnd()
        })
    }
    return ,$sections
}

# ----------------------------------------------------------------------
# Frontmatter 提取(T-RAG-4):从 .md/.txt 顶部 YAML frontmatter 提取元数据
# 支持字段:title, date, source, type, tags;缺失时用文件名/当前日期补全
# ----------------------------------------------------------------------

function Get-Frontmatter {
    <#
    .SYNOPSIS  提取 markdown 顶部 YAML frontmatter 并返回元数据 + 去除 frontmatter 后的正文
    #>
    param(
        [string]$Text,
        [string]$Source,
        [string]$DefaultDate = ""
    )
    $fm = @{
        title = ""
        date  = ""
        source = ""
        type  = ""
        tags  = @()
    }
    $rest = $Text
    if ($Text -match '^\s*---\s*\r?\n([\s\S]*?)\r?\n---\s*\r?\n') {
        $fmMatch = $Matches
        $yaml = $fmMatch[1]
        $inTags = $false
        foreach ($line in $yaml -split "`r?`n") {
            $line = $line.Trim()
            if (-not $line) { continue }
            if ($line -match '^(title|date|source|type):\s*(.*)$') {
                $val = $Matches[2].Trim()
                $val = $val.Trim([char]34).Trim([char]39)
                $fm[$Matches[1]] = $val
                $inTags = $false
            } elseif ($line -match '^tags:\s*\[(.*)\]\s*$') {
                $fm.tags = $Matches[1].Split(',') | ForEach-Object { $_.Trim().Trim([char]34).Trim([char]39) } | Where-Object { $_ }
                $inTags = $false
            } elseif ($line -match '^tags:\s*$') {
                $inTags = $true
                $fm.tags = @()
            } elseif ($inTags -and $line -match '^-\s*(.+)$') {
                $fm.tags += $Matches[1].Trim().Trim([char]34).Trim([char]39)
            } else {
                $inTags = $false
            }
        }
        $rest = $Text.Substring($fmMatch[0].Length)
    }
    # 默认值
    if (-not $fm.title) {
        $fm.title = [System.IO.Path]::GetFileNameWithoutExtension($Source)
    }
    if (-not $fm.date -and $DefaultDate) {
        $fm.date = $DefaultDate
    }
    if (-not $fm.source) {
        $fm.source = $Source
    }
    if (-not $fm.type) {
        $fm.type = [System.IO.Path]::GetExtension($Source).TrimStart('.').ToLower()
    }
    return [pscustomobject]@{ fm = $fm; rest = $rest }
}

# ----------------------------------------------------------------------
# 时间加权辅助(T-RAG-6 P2 生成层):从 frontmatter 日期或默认日期计算 days_old
# ----------------------------------------------------------------------

function Get-DaysOld {
    <#
    .SYNOPSIS  计算 date 字符串距今的天数
    .PARAMETER DateStr
      日期字符串,支持 yyyy-MM-dd / yyyy/MM/dd / yyyy年MM月dd日 等常见格式
    .OUTPUTS   int 天数(解析失败返回 0)
    #>
    param([string]$DateStr)
    if ([string]::IsNullOrWhiteSpace($DateStr)) { return 0 }
    $date = $null
    # 尝试常见格式
    $formats = @(
        'yyyy-MM-dd', 'yyyy/MM/dd', 'yyyy年MM月dd日',
        'yyyy-MM', 'yyyy/MM', 'yyyy年MM月',
        'yyyyMMdd', 'yyyyMM'
    )
    foreach ($fmt in $formats) {
        try {
            $date = [datetime]::ParseExact($DateStr.Trim(), $fmt, [System.Globalization.CultureInfo]::InvariantCulture)
            break
        } catch {
            $date = $null
        }
    }
    if (-not $date) {
        # 兜底:TryParse
        try {
            $date = [datetime]::Parse($DateStr.Trim())
        } catch {
            return 0
        }
    }
    $span = [datetime]::Now - $date
    if ($span.Days -lt 0) { return 0 }
    return $span.Days
}

# ----------------------------------------------------------------------
# Markdown 特殊块保护(T-RAG-5):把 fenced code block 与 markdown 表格识别为原子块,
# 防止在代码/表格中间切开;后续分块时单独成 chunk 并打 chunk_type 标签
# ----------------------------------------------------------------------

function Get-MarkdownSegments {
    <#
    .SYNOPSIS  把 markdown 文本拆分为 normal / code / table 三种原子段
    #>
    param([string]$Text)
    $segments = New-Object System.Collections.Generic.List[object]
    if ([string]::IsNullOrWhiteSpace($Text)) { return ,$segments }
    $lines = $Text -split "`r?`n"
    $i = 0
    while ($i -lt $lines.Count) {
        $line = $lines[$i]
        if ($line -match '^```') {
            $start = $i
            $i++
            while ($i -lt $lines.Count -and $lines[$i] -notmatch '^```') { $i++ }
            $end = $i
            $block = ($lines[$start..$end] -join "`n")
            $segments.Add([pscustomobject]@{ kind = 'code'; text = $block })
            $i++
        } elseif ($line -match '^\s*\|') {
            $start = $i
            $i++
            while ($i -lt $lines.Count -and $lines[$i].Trim() -ne '' -and $lines[$i] -match '^\s*\|') { $i++ }
            $end = $i - 1
            $block = ($lines[$start..$end] -join "`n")
            $segments.Add([pscustomobject]@{ kind = 'table'; text = $block })
        } else {
            $start = $i
            while ($i -lt $lines.Count -and $lines[$i] -notmatch '^```' -and $lines[$i] -notmatch '^\s*\|') { $i++ }
            $end = $i - 1
            if ($end -ge $start) {
                $block = ($lines[$start..$end] -join "`n")
                if (-not [string]::IsNullOrWhiteSpace($block)) {
                    $segments.Add([pscustomobject]@{ kind = 'normal'; text = $block })
                }
            }
        }
    }
    return ,$segments
}

# ----------------------------------------------------------------------
# Chunking:把 markdown 切成 ≤ MaxLen 的段落块(header-aware + overlap + 原子块保护)
# T-RAG-2:HeaderAware 默认开,按 markdown 标题切大段,header_path 进 meta
# T-RAG-3:Overlap 默认 150,chunk 之间保留 150 字符重叠修复边界丢失
# T-RAG-5:代码块/表格作为原子块,不内部切开,并记录 chunk_type
# ----------------------------------------------------------------------

function Split-IntoChunks {
    <#
    .SYNOPSIS  把 markdown text 切成 chunks,带 header 感知 + overlap + 原子块保护 + 事实/观点标签
    .PARAMETER Text        原始 markdown 文本
    .PARAMETER Source      来源文件名(用于 chunk 的 source 字段)
    .PARAMETER MaxLen      单 chunk 最大字符数(默认 800)
    .PARAMETER Overlap     chunk 之间重叠字符数(默认 150;0 = 关闭)
    .PARAMETER HeaderAware 是否按 markdown 标题切大段(默认 $true;$false = 旧行为)
    .PARAMETER DefaultDate 默认日期(文件 mtime),用于补全 frontmatter 的 date 字段
    #>
    param(
        [string]$Text,
        [string]$Source,
        [int]$MaxLen = 800,
        [int]$Overlap = 150,
        [bool]$HeaderAware = $true,
        [string]$DefaultDate = ""
    )

    # T-RAG-4: 提取 frontmatter 元数据,正文去掉 frontmatter
    $fmResult = Get-Frontmatter -Text $Text -Source $Source -DefaultDate $DefaultDate
    $fm = $fmResult.fm
    $bodyText = $fmResult.rest

    # T-RAG-6: 计算文档距今天数,用于时间加权
    $script:docDaysOld = Get-DaysOld -DateStr ($fm.date)

    # Step 1: 按 header 切大段(T-RAG-2)
    if ($HeaderAware) {
        $sections = Split-ByHeaders -Text $bodyText
    } else {
        $sections = ,(@{
            header_path = ""
            level       = 0
            text        = $bodyText
        })
    }

    $chunks = New-Object System.Collections.Generic.List[object]

    function local:Build-ChunkMeta {
        <#
        .SYNOPSIS  构造统一 meta,含 certainty / days_old / date
        #>
        param(
            [string]$Text,
            [string]$ChunkType
        )
        return @{
            section      = $curLevel
            source_file  = $Source
            header_path  = $curHeaderPath
            header_level = $curLevel
            title        = $fm.title
            date         = $fm.date
            days_old     = $script:docDaysOld
            doc_source   = $fm.source
            doc_type     = $fm.type
            tags         = ($fm.tags -join ",")
            chunk_type   = $ChunkType
            certainty    = (Get-Certainty -Text $Text)
        }
    }

    function local:Flush-NormalBuffer {
        if ($buf.Length -gt 0) {
            $src = if ([string]::IsNullOrEmpty($curHeaderPath)) { $Source } else { "$Source §$curHeaderPath" }
            $txt = $buf.ToString().Trim()
            $chunks.Add(@{
                id     = (Get-Sha256Short "$Source|$txt")
                text   = $txt
                source = $src
                meta   = (Build-ChunkMeta -Text $txt -ChunkType 'text')
            })
            if ($Overlap -gt 0 -and $buf.Length -gt $Overlap) {
                $tail = $buf.ToString().Substring($buf.Length - $Overlap)
                [void]$buf.Clear()
                [void]$buf.Append($tail)
            } else {
                [void]$buf.Clear()
            }
        }
    }

    foreach ($section in $sections) {
        $curHeaderPath = $section.header_path
        $curLevel = $section.level
        $buf = New-Object System.Text.StringBuilder

        # T-RAG-5: 把 section 拆成 normal / code / table 三种原子段
        $segments = Get-MarkdownSegments -Text $section.text

        foreach ($seg in $segments) {
            if ($seg.kind -ne 'normal') {
                Flush-NormalBuffer
                $src = if ([string]::IsNullOrEmpty($curHeaderPath)) { $Source } else { "$Source §$curHeaderPath" }
                $txt = $seg.text.Trim()
                $chunks.Add(@{
                    id     = (Get-Sha256Short "$Source|$txt")
                    text   = $txt
                    source = $src
                    meta   = (Build-ChunkMeta -Text $txt -ChunkType $seg.kind)
                })
                continue
            }

            # normal 段继续按段落合并
            $paragraphs = $seg.text -split "(\r?\n){2,}"
            foreach ($p in $paragraphs) {
                $pp = $p.Trim()
                if ([string]::IsNullOrWhiteSpace($pp)) { continue }

                # 超长单段滑窗切片
                if ($pp.Length -gt $MaxLen) {
                    Flush-NormalBuffer
                    $step = $MaxLen - $Overlap
                    if ($step -le 0) { $step = $MaxLen }
                    for ($off = 0; $off -lt $pp.Length; $off += $step) {
                        $piece = $pp.Substring($off, [Math]::Min($MaxLen, $pp.Length - $off))
                        $srcWin = if ([string]::IsNullOrEmpty($curHeaderPath)) { $Source } else { "$Source §$curHeaderPath" }
                        $chunks.Add(@{
                            id     = (Get-Sha256Short "$Source|$piece")
                            text   = $piece
                            source = $srcWin
                            meta   = (Build-ChunkMeta -Text $piece -ChunkType 'text')
                        })
                    }
                    continue
                }

                if ($buf.Length -gt 0 -and ($buf.Length + $pp.Length + 2) -gt $MaxLen) {
                    Flush-NormalBuffer
                }
                [void]$buf.AppendLine($pp)
                [void]$buf.AppendLine()
            }
        }

        Flush-NormalBuffer
    }

    return ,$chunks
}

# ----------------------------------------------------------------------
# 导出函数(供 embed-and-ingest.ps1 / test_m2a.ps1 调用)
# ----------------------------------------------------------------------

function Invoke-ParseDocument {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)] [string]$InputFile,
        [Parameter(Mandatory = $true)] [string]$OutputDir,
        [string]$DocId,
        [string]$MineruUrl = "http://localhost:8001",
        [switch]$UseCache
    )
    if (-not (Test-Path -LiteralPath $InputFile)) {
        throw "找不到输入文件: $InputFile"
    }
    if (-not $DocId) {
        $DocId = Get-Sha256Short (Resolve-Path -LiteralPath $InputFile).Path
    }
    Ensure-Dir $OutputDir | Out-Null
    $docDir = Join-Path $OutputDir $DocId
    Ensure-Dir $docDir | Out-Null
    $chunksPath = Join-Path $docDir "chunks.jsonl"

    if ($UseCache -and (Test-Path $chunksPath)) {
        Write-Step "UseCache 命中,跳过解析: $chunksPath"
        return $chunksPath
    }

    $ext = [System.IO.Path]::GetExtension($InputFile).ToLower()
    $fileName = [System.IO.Path]::GetFileName($InputFile)
    $markdown = $null

    switch ($ext) {
        ".docx" {
            Write-Step "检测到 .docx → 调 pandoc"
            $markdown = Invoke-PandocConvert -FilePath $InputFile -Format "docx"
        }
        ".doc" {
            $ok = Test-MineruReachable -Url $MineruUrl
            if ($ok) {
                Write-Step "检测到 .doc → MinerU"
                $markdown = Invoke-MineruParse -FilePath $InputFile -Url $MineruUrl
            } else {
                Write-Step "检测到 .doc → 尝试 Office COM 转 .docx"
                $tmpDocx = Convert-OfficeFormatViaCom -FilePath $InputFile -TargetExt ".docx"
                try {
                    $markdown = Invoke-PandocConvert -FilePath $tmpDocx -Format "docx"
                } finally {
                    Remove-Item -Force -ErrorAction SilentlyContinue $tmpDocx
                }
            }
        }
        ".pdf" {
            $ok = Test-MineruReachable -Url $MineruUrl
            if ($ok -and -not $NoMineruPdf) {
                Write-Step "检测到 .pdf → MinerU ($MineruUrl)"
                $markdown = Invoke-MineruParse -FilePath $InputFile -Url $MineruUrl
            } else {
                if ($NoMineruPdf) { Write-Step "检测到 .pdf → 直接 pdftotext(NoMineruPdf)" }
                else { Write-Warn "MinerU 不可达($MineruUrl),回退 pdftotext" }
                $markdown = Invoke-PdfTextFallback -FilePath $InputFile
            }
        }
        ".ppt" {
            $ok = Test-MineruReachable -Url $MineruUrl
            if ($ok) {
                Write-Step "检测到 .ppt → MinerU"
                $markdown = Invoke-MineruParse -FilePath $InputFile -Url $MineruUrl
            } else {
                Write-Step "检测到 .ppt → 尝试 Office COM 转 .pptx"
                $tmpPptx = Convert-OfficeFormatViaCom -FilePath $InputFile -TargetExt ".pptx"
                try {
                    $markdown = Invoke-PptxFallback -FilePath $tmpPptx
                } finally {
                    Remove-Item -Force -ErrorAction SilentlyContinue $tmpPptx
                }
            }
        }
        ".pptx" {
            $ok = Test-MineruReachable -Url $MineruUrl
            if ($ok -and -not $NoMineruPptx) {
                Write-Step "检测到 .pptx → MinerU"
                $markdown = Invoke-MineruParse -FilePath $InputFile -Url $MineruUrl
            } else {
                if ($NoMineruPptx) { Write-Step "检测到 .pptx → 直接 python-pptx(NoMineruPptx)" }
                else { Write-Warn "MinerU 不可达,回退 python-pptx" }
                $markdown = Invoke-PptxFallback -FilePath $InputFile
            }
        }
        ".xlsx" {
            Write-Step "检测到 .xlsx → openpyxl"
            $markdown = Invoke-XlsxParse -FilePath $InputFile
        }
        { @(".txt", ".md") -contains $_ } {
            Write-Step "检测到文本文件 → 直接读"
            $markdown = Get-Content -LiteralPath $InputFile -Raw -Encoding UTF8
        }
        { @(".png", ".jpg", ".jpeg", ".bmp", ".webp", ".gif") -contains $_ } {
            Write-Step "检测到图片 → 百炼 Qwen-VL ($CaptionModel)"
            $captionScript = Join-Path $PSScriptRoot 'image-caption.ps1'
            $oldEAP = $ErrorActionPreference
            $ErrorActionPreference = "Continue"
            $caption = & powershell -ExecutionPolicy Bypass -File $captionScript `
                -ImagePath $InputFile -Model $CaptionModel 2>&1
            $ErrorActionPreference = $oldEAP
            if ($LASTEXITCODE -ne 0) {
                throw "图片描述生成失败:`n$caption"
            }
            $markdown = $caption -join "`n"
        }
        default {
            throw "不支持的文件类型: $ext (仅 .doc/.docx/.ppt/.pptx/.pdf/.xlsx/.txt/.md/.png/.jpg/.jpeg/.bmp/.webp/.gif)"
        }
    }

    if ([string]::IsNullOrWhiteSpace($markdown)) {
        throw "解析结果为空:$InputFile"
    }
    $fileInfo = Get-Item -LiteralPath $InputFile
    $defaultDate = $fileInfo.LastWriteTime.ToString("yyyy-MM-dd")
    $chunks = Split-IntoChunks -Text $markdown -Source $fileName -DefaultDate $defaultDate
    $chunks = Split-LongChunks -Chunks $chunks -MaxLen 4000
    Write-Step "切分结果:$($chunks.Count) chunks"

    # 清空旧 chunks.jsonl(避免重复)
    if (Test-Path $chunksPath) { Remove-Item -Force $chunksPath }
    foreach ($c in $chunks) {
        $line = $c | ConvertTo-Json -Compress -Depth 5
        Add-Utf8NoBomLine -Path $chunksPath -Line $line
    }
    Write-Step "写入 chunks: $chunksPath"
    return $chunksPath
}

# ----------------------------------------------------------------------
# 入口
# ----------------------------------------------------------------------

# dot-source 时只暴露函数,不执行主流程
if ($MyInvocation.InvocationName -eq '.') { return }

try {
    $result = Invoke-ParseDocument -InputFile $InputFile -OutputDir $OutputDir `
        -DocId $DocId -MineruUrl $MineruUrl -UseCache:$UseCache
    Write-Host ""
    Write-Host "============================================================" -ForegroundColor Green
    Write-Host "  解析完成: $result" -ForegroundColor Green
    Write-Host "============================================================" -ForegroundColor Green
    exit 0
} catch {
    Write-Err $_.Exception.Message
    exit 1
}