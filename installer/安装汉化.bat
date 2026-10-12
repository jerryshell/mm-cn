@echo off
setlocal enabledelayedexpansion
title Motorsport Manager 简体中文汉化补丁

set "HERE=%~dp0"
if "%HERE:~-1%"=="\" set "HERE=%HERE:~0,-1%"
set "GAME="

rem ---------- 1) 在补丁文件夹附近找游戏 ----------
if exist "%HERE%\MM_Data\resources.assets" set "GAME=%HERE%"
if not defined GAME if exist "%HERE%\Motorsport Manager\MM_Data\resources.assets" set "GAME=%HERE%\Motorsport Manager"
if not defined GAME if exist "%HERE%\..\MM_Data\resources.assets" set "GAME=%HERE%\.."
if not defined GAME if exist "%HERE%\..\Motorsport Manager\MM_Data\resources.assets" set "GAME=%HERE%\..\Motorsport Manager"

rem ---------- 2) 从 Steam 注册表找 ----------
if not defined GAME for /f "tokens=2,*" %%a in ('reg query "HKCU\Software\Valve\Steam" /v SteamPath 2^>nul') do call :try "%%b"
if not defined GAME for /f "tokens=2,*" %%a in ('reg query "HKLM\SOFTWARE\WOW6432Node\Valve\Steam" /v InstallPath 2^>nul') do call :try "%%b"

rem ---------- 3) 默认安装位置 ----------
if not defined GAME if exist "%ProgramFiles(x86)%\Steam\steamapps\common\Motorsport Manager\MM_Data\resources.assets" set "GAME=%ProgramFiles(x86)%\Steam\steamapps\common\Motorsport Manager"
if not defined GAME if exist "%ProgramFiles%\Steam\steamapps\common\Motorsport Manager\MM_Data\resources.assets" set "GAME=%ProgramFiles%\Steam\steamapps\common\Motorsport Manager"

if not defined GAME goto ask
goto found

:try
if not defined GAME if exist "%~1\steamapps\common\Motorsport Manager\MM_Data\resources.assets" set "GAME=%~1\steamapps\common\Motorsport Manager"
exit /b 0

:ask
echo.
echo   没有自动找到游戏目录。
echo   可以把本补丁文件夹放到 "Motorsport Manager" 文件夹里（和 MM.exe 同级）再运行，
echo   也可以直接在下面输入游戏目录。
echo.
set "GAME="
set /p GAME=请输入 Motorsport Manager 文件夹的完整路径: 
for /f "tokens=* delims=" %%i in ("%GAME%") do set "GAME=%%~i"
if "%GAME%"=="" goto fail

:found
if not exist "%GAME%\MM_Data\resources.assets" goto fail
echo.
echo   游戏目录: %GAME%

rem ---------- 4) 找补丁本体 ----------
set "SRC="
if exist "%HERE%\resources.assets" set "SRC=%HERE%\resources.assets"
if not defined SRC if exist "%HERE%\patch\resources.assets" set "SRC=%HERE%\patch\resources.assets"
if not defined SRC if exist "%HERE%\..\resources.assets" set "SRC=%HERE%\..\resources.assets"
if not defined SRC goto nosrc

rem ---------- 5) 备份 + 安装 ----------
for %%A in ("%GAME%\MM_Data\resources.assets") do set "CURSIZE=%%~zA"
if not defined CURSIZE set "CURSIZE=0"
if %CURSIZE% LSS 300000000 goto sizeok
echo.
echo   [警告] 当前的 resources.assets 已经是汉化过的版本（%CURSIZE% 字节）。
echo          继续会把汉化文件当成原版备份，以后卸载就无法还原英文了。
echo          建议先用 Steam 的「验证游戏文件完整性」还原英文版，再运行本安装。
echo.
pause
:sizeok
set "BAK=%GAME%\MM_Data\resources.assets.orig"
if exist "%BAK%" goto nobackup
echo   [1/2] 正在备份原文件为 resources.assets.orig ...
copy /y "%GAME%\MM_Data\resources.assets" "%BAK%" >nul
if errorlevel 1 goto copyfail
goto install

:nobackup
echo   [1/2] 已存在备份，跳过备份。

:install
echo   [2/2] 正在安装汉化 ...
copy /y "%SRC%" "%GAME%\MM_Data\resources.assets" >nul
if errorlevel 1 goto copyfail

echo.
echo   汉化安装完成，直接启动游戏即可（不需要修改任何语言设置）。
echo.
echo   提示：
echo    * 如果 Steam 校验了游戏文件完整性，补丁会被还原，重新运行本文件即可。
echo    * 卸载请运行 卸载还原.bat。
echo.
pause
exit /b 0

:nosrc
echo   [错误] 找不到补丁本体 resources.assets。
echo          请确认它和本文件在同一个文件夹里。
goto fail

:copyfail
echo   [错误] 复制失败，请先关闭游戏和 Steam，或以管理员身份运行。
goto fail

:fail
echo.
pause
exit /b 1
