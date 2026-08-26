@echo off
REM ====================================================================
REM KB-AI · Windows 停止脚本 (v1.5.0)
REM 用途: 停止 FastAPI 后端容器 + 优雅停止所有容器 + 自动备份到电脑硬盘,然后安全弹出 U 盘
REM 关键: 必须先停后端和容器再拔 U 盘,直接拔会损坏 SQLite 数据库
REM ====================================================================

chcp 65001 >nul
setlocal EnableExtensions

cd /d "%~dp0"

cls
echo.
echo ============================================================
echo    KB-AI  正在停止服务...
echo ============================================================
echo.

REM ----- [1/4] 停止 FastAPI 后端容器(v1.5.0 容器化) -----
REM v1.5.0:不再调 scripts\stop-backend.ps1,改由 docker compose stop kb-ai-backend
REM 关键:kb-ai-backend 容器持有 data\db.sqlite 句柄;
REM 不停它直接弹盘会被 Windows 拒绝,且提示"可以拔出"后后端仍在写库。
echo [1/4] 停止 FastAPI 后端容器(kb-ai-backend)...
docker compose stop kb-ai-backend
if errorlevel 1 (
    echo [警告] docker compose stop kb-ai-backend 失败,尝试强制停止...
    docker compose kill kb-ai-backend
)
echo    KB-AI 后端容器已停止
echo.

REM v0.8.9(用户授权):停止 MinerU 解析服务(start.bat 会拉起它;
REM 不停会残留 U 盘路径的 python.exe,阻碍安全弹出)
echo    停止 MinerU 解析服务(:8001)...
powershell -NoProfile -Command "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | Where-Object { $_.CommandLine -like '*mineru_server.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }"
echo.

REM ----- 检查 Docker 是否在运行 -----
docker info >nul 2>&1
if errorlevel 1 (
    echo Docker Desktop 未运行,跳过容器停止.
    echo.
    goto backup_step
)

REM ----- [2/4] 优雅停止所有容器(stop 仅暂停,容器实例保留,数据保留在数据卷) -----
echo [2/4] 停止 Docker 容器(给 10 秒优雅退出)...
docker compose stop
if errorlevel 1 (
    echo [警告] docker compose stop 失败,尝试强制停止...
    docker compose kill
)

echo    容器已停止
echo.

REM ----- 5 秒倒计时,确保 SQLite 完成 fsync -----
echo [3/4] 等待 SQLite 完成数据落盘...
for /L %%i in (5,-1,1) do (
    echo    %%i 秒后可以安全弹出 U 盘...
    timeout /t 1 /nobreak >nul
)
echo    数据已落盘
echo.

REM ----- [4/4] 自动备份到电脑硬盘(v0.8.6 新增,FMEA F03) -----
:backup_step
echo [4/4] 备份数据到电脑硬盘(scripts\backup.ps1)...
powershell -NoProfile -ExecutionPolicy Bypass -File "scripts\backup.ps1"
if errorlevel 1 (
    echo [警告] 自动备份失败,不影响安全弹出;可稍后手动跑 scripts\backup.ps1 排查。
)
echo.

REM ----- 提示安全弹出 -----
:safe_eject
echo 安全弹出 U 盘
echo.
echo ============================================================
echo    现在您可以安全弹出 U 盘了!
echo.
echo    操作步骤:
echo    1. 在 Windows 系统托盘找到 "安全删除硬件" 图标
echo    2. 点击 → 选择您的 USB SSD
echo    3. 等待提示 "安全地移除设备"
echo    4. 物理拔出 U 盘
echo.
echo    为什么不直接拔? 请阅读 docs\safe-eject.md
echo    关键原因: SQLite 数据库需要 fsync 才能保证一致.
echo ============================================================
echo.

timeout /t 5 /nobreak >nul
endlocal
exit /b 0