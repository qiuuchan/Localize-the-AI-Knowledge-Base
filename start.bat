@echo off
REM ====================================================================
REM KB-AI · Windows 启动脚本 (v1.5.0+ shipping)
REM 用途: 双击启动 5 个 Docker 容器(含 kb-ai-backend v1.5.0+) + React 前端
REM 部署: 1TB USB SSD(随盘带镜像/模型/Docker 安装包)+ Windows 10/11
REM 时间: 冷启动约 60-90 秒;首次运行需加载预置镜像(1-2 分钟)
REM 默认入口: http://localhost:8000 (KB-AI 前端;FastAPI 提供)
REM 兼容入口: http://localhost:8080 (Dify Web UI;v0.8 之前的主入口)
REM
REM v1.5.1 shipping 改造点:
REM   - [1/8] 预置 Docker 镜像从 tools\kb-ai-images.tar 加载(秒级,免去 5-10 分钟 docker pull)
REM   - [2/8] HF 模型从 models\huggingface\ 复制到 %USERPROFILE%\.cache\huggingface\(首次)
REM   - [3/8] Docker Desktop 未装时自动从 tools\DockerDesktopInstaller.exe 安装
REM   - [4/8] .env 占位符检查用 /B 行首匹配,避开注释里的 "PLEASE-FILL-IN" 误命中
REM   - [5/8] WAL 文件检测,提示上次未正常退出(不阻断)
REM   - [6/8] 浏览器只开 1 次(去掉 3 次重试,避免多标签页打扰客户)
REM   - [7/8] 错误提示不再引用 "客户支持卡"(项目不附带),改为让客户拍照发微信
REM ====================================================================

REM 中文编码兼容 Windows cmd
chcp 65001 >nul
setlocal EnableExtensions EnableDelayedExpansion

REM 切到脚本所在目录(即 U 盘 KB-AI 根目录)
cd /d "%~dp0"

REM ============================================================
REM v1.5.2.1 · 客户机预检(5 项 5 秒判断能否跑 KB-AI)
REM 不通过直接 exit /b 1,不会启动 Docker / 加载镜像
REM ============================================================
call "%~dp0precheck.bat"
if errorlevel 1 (
    echo    [错误] 客户机预检未通过,KB-AI 无法启动
    pause
    exit /b 1
)

REM ============================================================
REM v1.5.2 · 启动日志初始化(为同事电脑闪退取证用)
REM 路径:  E:\logs\start-YYYYMMDD-HHMMSS.log
REM 失败兜底:U 盘只读时静默跳过,不阻断启动流程
REM ============================================================
set "LOG_DIR=%~dp0logs"
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%" >nul 2>&1
REM 用 wmic os get localdatetime 拿到纯数字时间戳(20260722235549),
REM 避开 %date% 在中文 locale 含 "周三" 这种 day-of-week,文件名更干净
for /f "tokens=2 delims==" %%i in ('wmic os get localdatetime /value 2^>nul') do set "LOG_TIMESTAMP=%%i"
if not defined LOG_TIMESTAMP (
    REM 兜底:某些精简系统无 wmic → 用 %date% %time% 拼
    set "LOG_TIMESTAMP=%date:~0,4%%date:~5,2%%date:~8,2%%time:~0,2%%time:~3,2%%time:~6,2%"
    set "LOG_TIMESTAMP=%LOG_TIMESTAMP: =0%"
)
set "LOG_FILE=%LOG_DIR%\start-%LOG_TIMESTAMP:~0,8%-%LOG_TIMESTAMP:~8,6%.log"
echo === KB-AI start.bat v1.5.2 启动日志 %date% %time% Win=%OS% === > "%LOG_FILE%" 2>nul
if not exist "%LOG_FILE%" (
    REM 关键:echo 内容里用全角中文括号(影响启动流程),不能是 ASCII 圆括号,
    REM 否则 CMD 会把它当成 IF 块的边界,语法炸 ↗ process exits.
    echo    [警告] 启动日志创建失败 · 可能 U 盘只读 · 不影响启动流程
) else (
    echo    启动日志: %LOG_FILE%
)

REM ----- v1.5.2:保留最近 20 个 start-*.log -----
for /f "skip=20 delims=" %%f in ('dir /b /o-d "%LOG_DIR%\start-*.log" 2^>nul') do del "%LOG_DIR%\%%f" >nul 2>&1

cls
echo. >> "%LOG_FILE%"
echo ============================================================ >> "%LOG_FILE%" & echo ============================================================
echo    KB-AI  启动中...  (请不要关闭此窗口) >> "%LOG_FILE%" & echo    KB-AI  启动中...  (请不要关闭此窗口)
echo    部署形态: 1TB USB SSD + Docker Desktop >> "%LOG_FILE%" & echo    部署形态: 1TB USB SSD + Docker Desktop
echo    AI 模型:  Qwen3.6-Plus (默认) / Qwen3.7-Max (复杂) >> "%LOG_FILE%" & echo    AI 模型:  Qwen3.6-Plus (默认) / Qwen3.7-Max (复杂)
echo    前端入口: http://localhost:8000 >> "%LOG_FILE%" & echo    前端入口: http://localhost:8000
echo ============================================================ >> "%LOG_FILE%" & echo ============================================================
echo. >> "%LOG_FILE%"

REM ----- [1/8] USB SSD 根目录 + 磁盘空间 + PowerShell 策略 -----
echo [1/8] USB SSD 根目录: %cd% >> "%LOG_FILE%" & echo [1/8] USB SSD 根目录: %cd%

REM 自动放宽 PowerShell 执行策略(只对当前进程生效,不修改系统策略)
powershell -NoProfile -Command "Set-ExecutionPolicy Bypass -Scope Process -Force" >nul 2>&1

REM ----- [2/8] Docker Desktop 检查 / 安装 / 启动(v1.5.2.1.2) -----
REM 改进点:
REM   - retry 机制(3 次,每次 30 秒)
REM   - 失败时读 installer 日志(给客户看具体原因)
REM   - 失败处理用 PowerShell Write-Host(避免 cmd 中文 echo 兼容)
REM   - 5 条常见原因 + maintainer 联系方式
echo [2/8] 检查 Docker Desktop... >> "%LOG_FILE%" & echo [2/8] 检查 Docker Desktop...

REM 检查是否已安装 Docker
where docker >nul 2>&1
if not errorlevel 1 goto docker_skip_install

echo    Docker 未安装,正在自动安装 · 约 1-3 分钟... >> "%LOG_FILE%" & echo    Docker 未安装,正在自动安装 · 约 1-3 分钟...

if not exist "tools\DockerDesktopInstaller.exe" goto docker_no_installer

echo    [步骤] 弹出 UAC 窗口,请点"是"(如未点,会失败) >> "%LOG_FILE%" & echo    [步骤] 弹出 UAC 窗口,请点"是"(如未点,会失败)

REM 第 1 次安装尝试
"tools\DockerDesktopInstaller.exe" install --quiet --accept-license
if not errorlevel 1 goto docker_install_ok

REM 第 1 次失败:读 installer 日志
echo. >> "%LOG_FILE%"
echo [步骤] 第一次安装失败,读取 installer 日志... >> "%LOG_FILE%"
if exist "%TEMP%\Docker Desktop Installer.log" (
    echo    --- installer 日志最后 10 行 --- >> "%LOG_FILE%"
    powershell -NoProfile -Command "Get-Content '%TEMP%\Docker Desktop Installer.log' -Tail 10" >> "%LOG_FILE%" 2>nul
    echo    --- 日志结束 --- >> "%LOG_FILE%"
)

REM 重试机制(3 次,共 1 + 2 = 3)
set /a DOCKER_RETRY=1
goto docker_retry_check
:docker_retry_loop
set /a DOCKER_RETRY=DOCKER_RETRY+1
echo    [重试 %DOCKER_RETRY%/3] 等待 30 秒后重试... >> "%LOG_FILE%" & echo    [重试 %DOCKER_RETRY%/3] 等待 30 秒后重试...
timeout /t 30 /nobreak >nul
"tools\DockerDesktopInstaller.exe" install --quiet --accept-license
if not errorlevel 1 goto docker_install_ok
:docker_retry_check
if %DOCKER_RETRY% gtr 2 goto docker_install_failed
goto docker_retry_loop

:docker_install_ok
echo    Docker Desktop 安装完成,正在启动... >> "%LOG_FILE%" & echo    Docker Desktop 安装完成,正在启动...
goto docker_after_install

:docker_install_failed
echo. >> "%LOG_FILE%"
echo [错误] Docker Desktop 自动安装 3 次均失败 >> "%LOG_FILE%"
echo. >> "%LOG_FILE%"
echo    常见原因及解决: >> "%LOG_FILE%"
echo    1. CPU 虚拟化未开 → BIOS 里开 VT-x / AMD-SVM(重启电脑) >> "%LOG_FILE%"
echo    2. Windows Defender / 杀软拦截 → 临时关闭后重试 >> "%LOG_FILE%"
echo    3. 磁盘空间不够(至少 4 GB) >> "%LOG_FILE%"
echo    4. installer 文件损坏 → 检查 tools\DockerDesktopInstaller.exe 大小 >> "%LOG_FILE%"
echo    5. 系统不是 Win10 1809+ / Win11 >> "%LOG_FILE%"
echo. >> "%LOG_FILE%"
echo    KB-AI 无法自动完成安装。请联系发盘人(maintainer)远程处理。 >> "%LOG_FILE%"

REM 屏幕输出用 PowerShell(避免 cmd 中文 echo 兼容问题)
REM v1.5.2.1.3 改进(2026-07-23 终端用户反馈):先 dump 当前机器虚拟化诊断
REM 让客户能直接看到"虚拟化未开"是根因(不用问发盘人)
powershell -NoProfile -Command "$fw=(Get-CimInstance Win32_Processor).VirtualizationFirmwareEnabled; $hp=(Get-CimInstance Win32_ComputerSystem).HypervisorPresent; Write-Host (''您电脑的虚拟化状态: firmware='' + $fw + '', hypervisor='' + $hp); if (-not $fw -and $hp) { Write-Host ''** 这就是问题:WSL2 装了 docker-desktop 让 hypervisor 看着 True,但 BIOS 虚拟化未开,Docker Desktop 跑不起来 **'' } elseif (-not $fw) { Write-Host ''** BIOS 虚拟化未开(Docker Desktop 必需) ** 请重启电脑进 BIOS 开 VT-x / AMD-SVM'' }"
powershell -NoProfile -Command "Write-Host ''"
powershell -NoProfile -Command "Write-Host '============================================================'"
powershell -NoProfile -Command "Write-Host '[错误] Docker Desktop 自动安装 3 次均失败'"
powershell -NoProfile -Command "Write-Host ''"
powershell -NoProfile -Command "Write-Host '    常见原因及解决:'"
powershell -NoProfile -Command "Write-Host '    1. CPU 虚拟化未开 → BIOS 里开 VT-x / AMD-SVM(重启电脑)'"
powershell -NoProfile -Command "Write-Host '    2. Windows Defender / 杀软拦截 → 临时关闭后重试'"
powershell -NoProfile -Command "Write-Host '    3. 磁盘空间不够(至少 4 GB)'"
powershell -NoProfile -Command "Write-Host '    4. installer 文件损坏 → 检查 tools\DockerDesktopInstaller.exe 大小'"
powershell -NoProfile -Command "Write-Host '    5. 系统不是 Win10 1809+ / Win11'"
powershell -NoProfile -Command "Write-Host ''"
powershell -NoProfile -Command "Write-Host 'KB-AI 无法自动完成安装。请联系发盘人(maintainer)远程处理。'"
powershell -NoProfile -Command "Write-Host '============================================================'"
REM v1.5.2.1.3: dump installer 日志最后 5 行到屏幕(不只写 log)
powershell -NoProfile -Command "if (Test-Path '%TEMP%\Docker Desktop Installer.log') { Write-Host '--- installer 日志最后 5 行 ---'; Get-Content '%TEMP%\Docker Desktop Installer.log' -Tail 5 | ForEach-Object { Write-Host $_ }; Write-Host '--- 日志结束 ---' } else { Write-Host '(无 installer 日志)' }"

pause
exit /b 1

:docker_no_installer
echo [错误] 找不到离线安装包 tools\DockerDesktopInstaller.exe >> "%LOG_FILE%"

REM 屏幕用 PowerShell 输出
powershell -NoProfile -Command "Write-Host '[错误] 找不到离线安装包 tools\DockerDesktopInstaller.exe'"
powershell -NoProfile -Command "Write-Host '请联系发盘人补发 U 盘或安装包'"

pause
exit /b 1

:docker_skip_install
echo    Docker Desktop 已安装,跳过自动安装 >> "%LOG_FILE%" & echo    Docker Desktop 已安装,跳过自动安装
:docker_after_install
goto docker_ready


REM 检查 Docker Desktop 是否在运行
docker info >nul 2>&1
if not errorlevel 1 goto docker_ready

echo    Docker Desktop 未运行,正在后台启动(首次需 30-60 秒)... >> "%LOG_FILE%" & echo    Docker Desktop 未运行,正在后台启动(首次需 30-60 秒)...
start "" "C:\Program Files\Docker\Docker\Docker Desktop.exe"

set /a wait_count=0
:wait_docker
set /a wait_count+=1
if !wait_count! gtr 18 (
    echo. >> "%LOG_FILE%"
    echo [错误] Docker Desktop 启动超时 · 90 秒,请检查: >> "%LOG_FILE%" & echo [错误] Docker Desktop 启动超时 · 90 秒,请检查:
    echo    1. 电脑是否已重启? 首次安装 Docker 需要重启一次 >> "%LOG_FILE%" & echo    1. 电脑是否已重启? 首次安装 Docker 需要重启一次
    echo    2. WSL 2 是否已启用? 控制面板 → 程序 → 启用或关闭 Windows 功能 >> "%LOG_FILE%" & echo    2. WSL 2 是否已启用? 控制面板 → 程序 → 启用或关闭 Windows 功能
    echo    拍照这一屏发微信给发盘人 >> "%LOG_FILE%" & echo    拍照这一屏发微信给发盘人
    echo. >> "%LOG_FILE%"
    pause
    exit /b 1
)
echo    等待 Docker Desktop 就绪... [!wait_count!/18] >> "%LOG_FILE%" & echo    等待 Docker Desktop 就绪... [!wait_count!/18]
timeout /t 5 /nobreak >nul
docker info >nul 2>&1
if errorlevel 1 goto wait_docker

:docker_ready
echo    Docker Desktop 已就绪 >> "%LOG_FILE%" & echo    Docker Desktop 已就绪
echo. >> "%LOG_FILE%"

REM ----- [3/8] WSL 2 / .env / WAL 自检 -----
echo [3/8] 自检... >> "%LOG_FILE%" & echo [3/8] 自检...

REM 3a. WSL 2 检查(只警告不阻断)
wsl --status >nul 2>&1
if errorlevel 1 (
    echo    [警告] WSL 2 未启用,Docker 可能无法启动 >> "%LOG_FILE%" & echo    [警告] WSL 2 未启用,Docker 可能无法启动
    echo       控制面板 → 程序 → 启用或关闭 Windows 功能 >> "%LOG_FILE%" & echo       控制面板 → 程序 → 启用或关闭 Windows 功能
    echo       勾选 "适用于 Linux 的 Windows 子系统" 和 "虚拟机平台" → 重启 >> "%LOG_FILE%" & echo       勾选 "适用于 Linux 的 Windows 子系统" 和 "虚拟机平台" → 重启
)

REM 3b. .env 存在 + 占位符检查(用 /B 行首匹配,避开注释误命中)
if not exist ".env" (
    echo. >> "%LOG_FILE%"
    echo [错误] .env 不存在,请联系客服 >> "%LOG_FILE%" & echo [错误] .env 不存在,请联系客服
    pause
    exit /b 1
)
findstr /B /C:"ALIYUN_BAILIAN_API_KEY=sk-PLEASE-FILL-IN" .env >nul 2>&1
if not errorlevel 1 (
    echo. >> "%LOG_FILE%"
    echo [错误] .env 里的 API Key 还是占位符 sk-PLEASE-FILL-IN-... >> "%LOG_FILE%" & echo [错误] .env 里的 API Key 还是占位符 sk-PLEASE-FILL-IN-...
    echo    请联系客服补填 >> "%LOG_FILE%" & echo    请联系客服补填
    pause
    exit /b 1
)

REM 3c. WAL 自检(上次是否干净退出,不阻断)
if exist "data\db.sqlite-wal" (
    echo    [警告] 检测到 WAL 文件,上次可能未正常退出 >> "%LOG_FILE%" & echo    [警告] 检测到 WAL 文件,上次可能未正常退出
    echo       系统会自动尝试恢复,无需操作 >> "%LOG_FILE%" & echo       系统会自动尝试恢复,无需操作
    timeout /t 3 /nobreak >nul
)
echo    自检通过 >> "%LOG_FILE%" & echo    自检通过
echo. >> "%LOG_FILE%"

REM ----- [4/8] 加载预置 Docker 镜像(避免 5-10 分钟 docker pull) -----
echo [4/8] 加载预置 Docker 镜像... >> "%LOG_FILE%" & echo [4/8] 加载预置 Docker 镜像...

if not exist "tools\kb-ai-images.tar" (
    echo    [警告] 未找到预置镜像 tools\kb-ai-images.tar >> "%LOG_FILE%" & echo    [警告] 未找到预置镜像 tools\kb-ai-images.tar
    echo       将从 Docker Hub 联网下载,首次需 5-10 分钟 >> "%LOG_FILE%" & echo       将从 Docker Hub 联网下载,首次需 5-10 分钟
    goto skip_preload
)

if exist ".docker-images-loaded.flag" (
    echo    镜像已加载过,跳过 >> "%LOG_FILE%" & echo    镜像已加载过,跳过
    goto skip_preload
)

echo    首次启动,正在加载 4 个预置镜像(约 1-2 分钟)... >> "%LOG_FILE%" & echo    首次启动,正在加载 4 个预置镜像(约 1-2 分钟)...
docker load -i "tools\kb-ai-images.tar"
if errorlevel 1 (
    echo. >> "%LOG_FILE%"
    echo [警告] 预置镜像加载失败,将从 Docker Hub 联网下载 >> "%LOG_FILE%" & echo [警告] 预置镜像加载失败,将从 Docker Hub 联网下载
    echo    可能原因:U 盘读写错误 / Docker Desktop 异常 >> "%LOG_FILE%" & echo    可能原因:U 盘读写错误 / Docker Desktop 异常
) else (
    echo. > ".docker-images-loaded.flag"
    echo    镜像加载完成 >> "%LOG_FILE%" & echo    镜像加载完成
)

:skip_preload
echo. >> "%LOG_FILE%"

REM ----- [5/8] 复制预置 HF 模型到用户目录(避免首次检索挂起) -----
echo [5/8] 加载预置 HF 模型... >> "%LOG_FILE%" & echo [5/8] 加载预置 HF 模型...

REM 检查目标位置是否已有 reranker
set "HF_DEST=%USERPROFILE%\.cache\huggingface"
if exist "%HF_DEST%\hub\models--BAAI--bge-reranker-base" goto hf_skip

if not exist "models\huggingface\hub\models--BAAI--bge-reranker-base" (
    echo    [警告] 未找到预置 HF 模型,首次检索可能慢 >> "%LOG_FILE%" & echo    [警告] 未找到预置 HF 模型,首次检索可能慢
    goto skip_hf
)

echo    首次启动,正在复制预置模型到本地缓存(约 30 秒)... >> "%LOG_FILE%" & echo    首次启动,正在复制预置模型到本地缓存(约 30 秒)...
if not exist "%HF_DEST%\hub" mkdir "%HF_DEST%\hub" >nul 2>&1
robocopy "models\huggingface\hub" "%HF_DEST%\hub" /E /NFL /NDL /NJH /NJS /NC /NS >nul
if errorlevel 8 (
    echo    [警告] 模型复制失败 · robocopy 返回 !errorlevel! · 首次检索可能慢 >> "%LOG_FILE%" & echo    [警告] 模型复制失败 · robocopy 返回 !errorlevel! · 首次检索可能慢
) else (
    echo    HF 模型加载完成 >> "%LOG_FILE%" & echo    HF 模型加载完成
)

:hf_skip
:skip_hf
echo. >> "%LOG_FILE%"

REM ----- [6/8] 启动 Docker 容器 + 后端 + MinerU -----
echo [6/8] 启动 Docker 容器(5 个) + KB-AI 后端 + MinerU... >> "%LOG_FILE%" & echo [6/8] 启动 Docker 容器(5 个) + KB-AI 后端 + MinerU...

docker compose up -d
if errorlevel 1 (
    echo. >> "%LOG_FILE%"
    echo [错误] docker compose up 失败 >> "%LOG_FILE%" & echo [错误] docker compose up 失败
    echo    请把这一屏截图发给客服 >> "%LOG_FILE%" & echo    请把这一屏截图发给客服
    pause
    exit /b 1
)

docker compose up -d kb-ai-backend
if errorlevel 1 (
    echo. >> "%LOG_FILE%"
    echo [警告] FastAPI 后端容器启动失败 >> "%LOG_FILE%" & echo [警告] FastAPI 后端容器启动失败
    echo    手动跑:docker compose logs kb-ai-backend >> "%LOG_FILE%" & echo    手动跑:docker compose logs kb-ai-backend
)

REM 启动 MinerU 解析服务(:8001,前端上传 PDF/PPTX 必需)
powershell -NoProfile -Command "try { (Invoke-WebRequest -Uri 'http://127.0.0.1:8001/health' -UseBasicParsing -TimeoutSec 2).StatusCode } catch { 0 }" > "%TEMP%\kb-ai-mineru.txt" 2>nul
set /a mineru_code=0
for /f "delims=" %%i in ('type "%TEMP%\kb-ai-mineru.txt" 2^>nul') do set /a mineru_code=%%i
if !mineru_code! equ 200 (
    echo    MinerU 解析服务已在运行 >> "%LOG_FILE%" & echo    MinerU 解析服务已在运行
) else (
    REM v1.5.1: USB 上的 backend\.venv 引用了发盘机的 Python 路径,客户机器上无法启动
    REM MinerU 暂不打包,改为跳过 + 友好提示;聊天 + 文本资料正常,Word/Excel 部分支持
    echo    [跳过] PDF/PPTX 解析服务 · 本批 USB 未打包 · 聊天不受影响 >> "%LOG_FILE%" & echo    [跳过] PDF/PPTX 解析服务 · 本批 USB 未打包 · 聊天不受影响
    echo             如需 PDF/PPTX 解析能力,请联系发盘人远程协助配置 >> "%LOG_FILE%" & echo             如需 PDF/PPTX 解析能力,请联系发盘人远程协助配置
)
echo    容器已全部启动 >> "%LOG_FILE%" & echo    容器已全部启动
echo. >> "%LOG_FILE%"

REM ----- [7/8] 等待 KB-AI 前端就绪(http://localhost:8000) -----
echo [7/8] 等待 KB-AI 前端就绪(约 30-60 秒)... >> "%LOG_FILE%" & echo [7/8] 等待 KB-AI 前端就绪(约 30-60 秒)...
set /a api_count=0
:wait_api
set /a api_count+=1
if !api_count! gtr 40 (
    echo. >> "%LOG_FILE%"
    echo [警告] KB-AI 前端启动超过 80 秒 >> "%LOG_FILE%" & echo [警告] KB-AI 前端启动超过 80 秒
    echo    可能首次在拉依赖,可手动访问:http://localhost:8000 >> "%LOG_FILE%" & echo    可能首次在拉依赖,可手动访问:http://localhost:8000
    goto open_browser
)
powershell -NoProfile -Command "try { (Invoke-WebRequest -Uri 'http://localhost:8000/api/health' -UseBasicParsing -TimeoutSec 3).StatusCode } catch { 0 }" > "%TEMP%\kb-ai-api.txt" 2>nul
set /a api_code=0
for /f "delims=" %%i in ('type "%TEMP%\kb-ai-api.txt" 2^>nul') do set /a api_code=%%i
if !api_code! equ 200 goto api_ready
timeout /t 2 /nobreak >nul
echo    检查中... [!api_count!/40] >> "%LOG_FILE%" & echo    检查中... [!api_count!/40]
goto wait_api

:api_ready
echo    KB-AI 前端已就绪! >> "%LOG_FILE%" & echo    KB-AI 前端已就绪!
echo. >> "%LOG_FILE%"

REM ----- [8/8] 打开浏览器(3 次重试) -----
:open_browser
echo [8/8] 打开浏览器... >> "%LOG_FILE%" & echo [8/8] 打开浏览器...
start "" "http://localhost:8000"

echo. >> "%LOG_FILE%"
echo ============================================================ >> "%LOG_FILE%" & echo ============================================================
echo    启动完成! >> "%LOG_FILE%" & echo    启动完成!
echo. >> "%LOG_FILE%"
echo    KB-AI 前端:     http://localhost:8000 >> "%LOG_FILE%" & echo    KB-AI 前端:     http://localhost:8000
echo    FastAPI 文档:   http://localhost:8000/docs >> "%LOG_FILE%" & echo    FastAPI 文档:   http://localhost:8000/docs
echo    Dify Web (兼容): http://localhost:8080 >> "%LOG_FILE%" & echo    Dify Web (兼容): http://localhost:8080
echo. >> "%LOG_FILE%"
echo    关闭服务: 双击 stop.bat >> "%LOG_FILE%" & echo    关闭服务: 双击 stop.bat
echo    安全弹出 U 盘: 先停服务,然后右下角弹出 USB >> "%LOG_FILE%" & echo    安全弹出 U 盘: 先停服务,然后右下角弹出 USB
echo. >> "%LOG_FILE%"
echo    故障排查: 拍照这一屏发微信给发盘人 + 看 E:\logs\start-*.log >> "%LOG_FILE%" & echo    故障排查: 拍照这一屏发微信给发盘人 + 看 E:\logs\start-*.log
echo ============================================================ >> "%LOG_FILE%" & echo ============================================================
echo. >> "%LOG_FILE%"
timeout /t 5 /nobreak >nul

REM ----- v1.5.2:启动日志退出收尾(endlocal 之前,变量还有效) -----
echo === KB-AI start.bat 退出 (errorlevel=%errorlevel%) %date% %time% === >> "%LOG_FILE%" & echo === KB-AI start.bat 退出 (errorlevel=%errorlevel%) %date% %time% === 2>nul

endlocal
exit /b 0
