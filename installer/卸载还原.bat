@echo off
setlocal
title Motorsport Manager 汉化卸载

set "HERE=%~dp0"
if "%HERE:~-1%"=="\" set "HERE=%HERE:~0,-1%"
set "GAME="

if exist "%HERE%\MM_Data\resources.assets" set "GAME=%HERE%"
if not defined GAME if exist "%HERE%\Motorsport Manager\MM_Data\resources.assets" set "GAME=%HERE%\Motorsport Manager"
if not defined GAME if exist "%HERE%\..\MM_Data\resources.assets" set "GAME=%HERE%\.."
if not defined GAME if exist "%HERE%\..\Motorsport Manager\MM_Data\resources.assets" set "GAME=%HERE%\..\Motorsport Manager"

if not defined GAME for /f "tokens=2,*" %%a in ('reg query "HKCU\Software\Valve\Steam" /v SteamPath 2^>nul') do call :try "%%b"
if not defined GAME for /f "tokens=2,*" %%a in ('reg query "HKLM\SOFTWARE\WOW6432Node\Valve\Steam" /v InstallPath 2^>nul') do call :try "%%b"
if not defined GAME if exist "%ProgramFiles(x86)%\Steam\steamapps\common\Motorsport Manager\MM_Data\resources.assets.orig" set "GAME=%ProgramFiles(x86)%\Steam\steamapps\common\Motorsport Manager"
if not defined GAME if exist "%ProgramFiles%\Steam\steamapps\common\Motorsport Manager\MM_Data\resources.assets.orig" set "GAME=%ProgramFiles%\Steam\steamapps\common\Motorsport Manager"

if not defined GAME goto ask
goto found

:try
if not defined GAME if exist "%~1\steamapps\common\Motorsport Manager\MM_Data\resources.assets.orig" set "GAME=%~1\steamapps\common\Motorsport Manager"
exit /b 0

:ask
echo.
set "GAME="
set /p GAME=请输入 Motorsport Manager 文件夹的完整路径: 
for /f "tokens=* delims=" %%i in ("%GAME%") do set "GAME=%%~i"
if "%GAME%"=="" goto fail

:found
set "BAK=%GAME%\MM_Data\resources.assets.orig"
if not exist "%BAK%" goto nobak
echo.
echo   游戏目录: %GAME%
echo   正在还原英文原版 ...
copy /y "%BAK%" "%GAME%\MM_Data\resources.assets" >nul
if errorlevel 1 goto copyfail
del /q "%BAK%"
echo.
echo   已还原为英文原版。
pause
exit /b 0

:nobak
echo.
echo   [错误] 找不到备份文件 resources.assets.orig
echo          可以用 Steam 的「验证游戏文件完整性」来还原。
goto fail

:copyfail
echo   [错误] 还原失败，请先关闭游戏和 Steam，或以管理员身份运行。
goto fail

:fail
echo.
pause
exit /b 1
