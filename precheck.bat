@echo off
REM ====================================================================
REM KB-AI · 客户机预检 (v1.5.2.1)
REM 用途: 5 秒判断客户电脑是否能跑 KB-AI(5 个 Docker 容器)
REM 输出: 屏幕直接显示(不像 v1.5.2 start.bat 全写日志)
REM 配合 start.bat 使用:[1/8] 之前调本脚本;不通过 exit /b 1
REM 重要: 用 goto 结构避免 if/else 块内延迟变量扩展的兼容性问题
REM ====================================================================

chcp 65001 >nul
setlocal EnableExtensions

echo.
echo ============================================================
echo    KB-AI  客户机预检  v1.5.2.1
echo ============================================================
echo.
echo    正在检查您的电脑是否能跑 KB-AI(5 个 Docker 容器)...
echo    大约 5 秒,请稍候。
echo.

set "CHECK_OK=0"
set "CHECK_FAIL=0"
set "FAIL_REASONS="

REM ----- [1/5] CPU 虚拟化 (VT-x / AMD-SVM) -----
echo [1/5] CPU 虚拟化 ...
REM v1.5.2.1.3 严格化(2026-07-23 终端用户反馈):firmware 必须 True 才是真实虚拟化
REM 之前 HypervisorPresent 兜底会把 WSL2-only 客户(WSL 装了 docker-desktop 但
REM BIOS 虚拟化关)误判 Yes,导致 precheck 5/5 通过但 Docker 跑不起来。
REM 新逻辑:firmware=True -> Yes;否则只在 HypervisorPresent=True 且 systeminfo
REM 有 'hypervisor has been detected'(VM 内的强信号)才报 Yes(VM-Yes)
powershell -NoProfile -Command "$v='No'; if ((Get-CimInstance Win32_Processor).VirtualizationFirmwareEnabled) { $v='Yes' } elseif ((Get-CimInstance Win32_ComputerSystem).HypervisorPresent) { $l=systeminfo | Select-String -Pattern 'hypervisor has been detected'; if ($l) { $v='VM-Yes' } }; $v" > "%TEMP%\kb-ai-vt.txt" 2>nul
set "VT_RESULT="
for /f "delims=" %%i in ('type "%TEMP%\kb-ai-vt.txt" 2^>nul') do set "VT_RESULT=%%i"
del "%TEMP%\kb-ai-vt.txt" 2>nul
if /i "%VT_RESULT%"=="Yes" goto ok_1
if /i "%VT_RESULT%"=="VM-Yes" goto ok_1
echo    [FAIL] CPU 虚拟化未启用(需要在 BIOS 里开 VT-x 或 AMD-SVM)
echo           这是 Docker Desktop 跑不起来的最大原因,占了 60%% 的失败案例
echo           如果您电脑是 VM 或已开 hypervisor 仍 FAIL,请联系发盘人
echo           检测结果: %VT_RESULT% (Yes=BIOS 已开, VM-Yes=VM 内 OK, No=BIOS 未开)
set /a CHECK_FAIL=CHECK_FAIL+1
set "FAIL_REASONS=%FAIL_REASONS% 1.CPU 虚拟化未开;"
goto next_1
:ok_1
echo    [OK] 虚拟化已启用
set /a CHECK_OK=CHECK_OK+1
:next_1
echo.

REM ----- [2/5] Windows 版本 -----
echo [2/5] Windows 版本 ...
for /f "tokens=2 delims==" %%i in ('wmic os get BuildNumber /value 2^>nul') do set "OS_BUILD=%%i"
if not defined OS_BUILD goto warn_2
if %OS_BUILD% geq 22000 goto win11_2
if %OS_BUILD% geq 17763 goto win10_2
goto fail_2
:win11_2
echo    [OK] Windows 11 ^(Build %OS_BUILD%^)
set /a CHECK_OK=CHECK_OK+1
goto next_2
:win10_2
echo    [OK] Windows 10 1809+ ^(Build %OS_BUILD%^)
set /a CHECK_OK=CHECK_OK+1
goto next_2
:warn_2
echo    [WARN] 无法检测 Windows 版本(继续)
goto next_2
:fail_2
echo    [FAIL] Windows 版本太老 ^(Build %OS_BUILD%^),需要 Win10 1809+ ^(Build 17763+^)
set /a CHECK_FAIL=CHECK_FAIL+1
set "FAIL_REASONS=%FAIL_REASONS% 2.Windows 版本太旧;"
:next_2
echo.

REM ----- [3/5] U 盘剩余空间 -----
echo [3/5] U 盘剩余空间 ...
REM 用 PowerShell 当前 session 的当前目录盘符,避免 cmd /c 调用下 %~d0 为空
set "FREE_GB="
for /f "delims=" %%i in ('powershell -NoProfile -Command "$d=(Get-Location).Drive.Name; [int]((Get-PSDrive $d).Free/1GB)" 2^>nul') do set "FREE_GB=%%i"
if not defined FREE_GB goto warn_3
if %FREE_GB% geq 10 goto ok_3
goto fail_3
:warn_3
echo    [WARN] 无法检测磁盘空间(继续)
goto next_3
:ok_3
echo    [OK] 剩余 %FREE_GB% GB ^(需要 ^>= 10 GB^)
set /a CHECK_OK=CHECK_OK+1
goto next_3
:fail_3
echo    [FAIL] 剩余 %FREE_GB% GB,KB-AI 需要 ^>= 10 GB ^(Docker 镜像 + 模型 + 5 容器运行时^)
set /a CHECK_FAIL=CHECK_FAIL+1
set "FAIL_REASONS=%FAIL_REASONS% 3.磁盘空间不足;"
:next_3
echo.

REM ----- [4/5] 内存 -----
echo [4/5] 内存 ...
REM 用 PowerShell 直接算 GB,避免 set /a 32-bit 溢出(16GB+ 会出 "Invalid number")
set "TOTAL_MEM_GB="
for /f "delims=" %%i in ('powershell -NoProfile -Command "[int]((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory/1GB)" 2^>nul') do set "TOTAL_MEM_GB=%%i"
if not defined TOTAL_MEM_GB goto warn_4
if %TOTAL_MEM_GB% geq 4 goto ok_4
goto fail_4
:warn_4
echo    [WARN] 无法检测内存(继续)
goto next_4
:ok_4
echo    [OK] %TOTAL_MEM_GB% GB ^(需要 ^>= 4 GB^)
set /a CHECK_OK=CHECK_OK+1
goto next_4
:fail_4
echo    [FAIL] %TOTAL_MEM_GB% GB,KB-AI 5 容器需要 ^>= 4 GB
set /a CHECK_FAIL=CHECK_FAIL+1
set "FAIL_REASONS=%FAIL_REASONS% 4.内存不足;"
:next_4
echo.

REM ----- [5/5] S Mode 检测 -----
echo [5/5] S Mode 检测 ...
REM 用 EditionID + Client SKU 联合检测;Server SKU 直接 OK
powershell -NoProfile -Command "$sku=(Get-CimInstance Win32_OperatingSystem).OperatingSystemSKU; $edition=(Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion').EditionID; if ($sku -in 1,2,3,4,27,28,100,101 -and ($edition -match '^Core$|^Cloud$| S$')) { 'SMode' } else { 'Normal' }" > "%TEMP%\kb-ai-smode.txt" 2>nul
set "SMODE="
for /f "delims=" %%i in ('type "%TEMP%\kb-ai-smode.txt" 2^>nul') do set "SMODE=%%i"
del "%TEMP%\kb-ai-smode.txt" 2>nul
if /i "%SMODE%"=="Normal" goto ok_5
if /i "%SMODE%"=="SMode" goto fail_5
echo    [WARN] 无法检测 S Mode(继续)
goto next_5
:ok_5
echo    [OK] 不是 S Mode
set /a CHECK_OK=CHECK_OK+1
goto next_5
:fail_5
echo    [FAIL] 检测到 S Mode,Docker Desktop 不支持 S Mode
set /a CHECK_FAIL=CHECK_FAIL+1
set "FAIL_REASONS=%FAIL_REASONS% 5.S Mode 不支持;"
:next_5
echo.

REM ----- 总结 -----
echo ============================================================
echo    预检结果:  %CHECK_OK% 通过 / %CHECK_FAIL% 失败
echo ============================================================
if %CHECK_FAIL% gtr 0 goto summary_fail
echo.

    echo    [通过] 您的电脑可以跑 KB-AI。
echo.
echo    [下一步] 双击 start.bat 启动 KB-AI(本窗口可以关掉)。
echo.
pause
endlocal
exit /b 0

:summary_fail
echo.
echo    [不通过] 您的电脑目前跑不了 KB-AI:
echo    %FAIL_REASONS%
echo.
echo    建议:
echo    1. 截屏记录后查看 logs/ 启动日志
echo    2. 让发盘人远程协助(ToDesk)或在 BIOS / 系统设置里修复
echo    3. 如果是 CPU 虚拟化或 S Mode,可能需要懂电脑的人到现场修
echo.
endlocal
echo    [下一步] 拍完照后,按任意键关闭此窗口。
echo.
pause
exit /b 1
