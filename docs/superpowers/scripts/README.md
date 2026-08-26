# 辅助脚本存档

> 存放 v0.8.10 cleanup 期间用过的辅助 PowerShell 脚本,供未来类似场景参考。

## bypass-edit-eperm-on-windows.ps1

**场景**:Claude Code 的 Edit 工具在 Windows 上偶发 `EPERM: operation not permitted, mkdir 'E:\'`,无法修改某些文件(如 AGENTS.md、package.bat、CHANGELOG.md)。

**绕过方式**:
1. 把修改逻辑写成 PowerShell 脚本保存到 `tmp/`
2. 用 `powershell -ExecutionPolicy Bypass -File <script>.ps1` 执行
3. 写文件统一用 `[System.IO.File]::WriteAllText($path, $content, [System.Text.UTF8Encoding]::new($false))`(UTF-8 无 BOM)

**注意事项**:
- **`Set-Content -Encoding UTF8` 会加 BOM**,会污染 .bat/.ps1/.cmd 的第一行(@echo off 前会被插入 U+FEFF),必须用 .NET API 替代。
- **PowerShell 双引号 here-string `@"..."@` 会解释反引号**:`\`b` → 退格(0x08)吃下一字符。含反引号内容用单引号 here-string `@'...'@`。
- 写完务必 `od -A x -t x1z -N 8` 验 BOM。

**存档原因**:v0.8.10 cleanup 中 AGENTS.md、CHANGELOG.md、package.bat 三次踩坑,经验值得保留。