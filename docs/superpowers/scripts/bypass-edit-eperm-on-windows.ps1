$path = 'E:\AGENTS.md'
$content = [System.IO.File]::ReadAllText($path, [System.Text.UTF8Encoding]::new($false))

# Edit 1: Remove the `backend/static/` line from §1 file tree
$lineToRemove1 = "│   ├── static/               # 内置前端(可选);主前端在 frontend/dist`r`n"
if ($content.Contains($lineToRemove1)) {
    $content = $content.Replace($lineToRemove1, '')
    Write-Host "Edit 1 applied: removed backend/static/ line"
} else {
    Write-Host "Edit 1 SKIPPED: target line not found (may already be removed)"
}

# Edit 2: §5 row 10 — change 8080 to 8000 + append v0.8.10 note
$lineToReplace2 = '| 10 | **前端:Dify Web UI → 自建 React 前端**(v0.8.2) | `frontend/dist/` vs `http://localhost:8080` | ✅ start.bat 改开 localhost:8000 |'
$newLine2 = '| 10 | **前端:Dify Web UI → 自建 React 前端**(v0.8.2) | `frontend/dist/` vs `http://localhost:8000` | ✅ start.bat 改开 localhost:8000;v0.8.10 删除 `backend/static/` 旧快照后,`frontend/dist/` 成为唯一前端 |'
if ($content.Contains($lineToReplace2)) {
    $content = $content.Replace($lineToReplace2, $newLine2)
    Write-Host "Edit 2 applied: §5 row 10 updated"
} else {
    Write-Host "Edit 2 SKIPPED: target line not found"
}

# Edit 3: §12.2 "已应用" → "已部署"
$lineToReplace3 = '  - **已应用**:`backend/static/index.html`'
$newLine3 = '  - **已部署**:由 `backend/main.py` 挂载 `frontend/dist/` 至 :8000;设计真实载体是 `frontend/src/`(`backend/static/` 已于 v0.8.10 删除)'
if ($content.Contains($lineToReplace3)) {
    $content = $content.Replace($lineToReplace3, $newLine3)
    Write-Host "Edit 3 applied: §12.2 wording updated"
} else {
    Write-Host "Edit 3 SKIPPED: target line not found"
}

[System.IO.File]::WriteAllText($path, $content, [System.Text.UTF8Encoding]::new($false))
Write-Host "AGENTS.md written (UTF-8 no BOM)"