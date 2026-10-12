"""生成随 release 一起发布的两个 Windows 安装脚本。

**这两个 .bat 必须以系统 ANSI 代码页（中文 Windows 是 GBK）保存。**
cmd.exe 无法解析 UTF-8 的批处理文件：UTF-8 的中文在 GBK 代码页下会被拆成一堆
乱码字节，脚本会以「不是内部或外部命令」的形式崩掉。

批处理里所有语法必须保持 ASCII，中文只出现在 echo/rem 里，这样即使用户的
代码页不是 936，最多是提示文字显示乱码，安装逻辑仍然正常。
"""
import os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'tools'))
from mmcore import ROOT, setup_console

OUT = os.path.join(ROOT, 'installer')
BS = chr(92)          # a literal backslash, kept out of the templates below

INSTALL = r'''@echo off
setlocal enabledelayedexpansion
title Motorsport Manager 简体中文汉化补丁

set "HERE=%~dp0"
if "%HERE:~-1%"=="\b" set "HERE=%HERE:~0,-1%"
set "GAME="

rem ---------- 1) 在补丁文件夹附近找游戏 ----------
if exist "%HERE%\bMM_Data\bresources.assets" set "GAME=%HERE%"
if not defined GAME if exist "%HERE%\bMotorsport Manager\bMM_Data\bresources.assets" set "GAME=%HERE%\bMotorsport Manager"
if not defined GAME if exist "%HERE%\b..\bMM_Data\bresources.assets" set "GAME=%HERE%\b.."
if not defined GAME if exist "%HERE%\b..\bMotorsport Manager\bMM_Data\bresources.assets" set "GAME=%HERE%\b..\bMotorsport Manager"

rem ---------- 2) 从 Steam 注册表找 ----------
if not defined GAME for /f "tokens=2,*" %%a in ('reg query "HKCU\bSoftware\bValve\bSteam" /v SteamPath 2^>nul') do call :try "%%b"
if not defined GAME for /f "tokens=2,*" %%a in ('reg query "HKLM\bSOFTWARE\bWOW6432Node\bValve\bSteam" /v InstallPath 2^>nul') do call :try "%%b"

rem ---------- 3) 默认安装位置 ----------
if not defined GAME if exist "%ProgramFiles(x86)%\bSteam\bsteamapps\bcommon\bMotorsport Manager\bMM_Data\bresources.assets" set "GAME=%ProgramFiles(x86)%\bSteam\bsteamapps\bcommon\bMotorsport Manager"
if not defined GAME if exist "%ProgramFiles%\bSteam\bsteamapps\bcommon\bMotorsport Manager\bMM_Data\bresources.assets" set "GAME=%ProgramFiles%\bSteam\bsteamapps\bcommon\bMotorsport Manager"

if not defined GAME goto ask
goto found

:try
if not defined GAME if exist "%~1\bsteamapps\bcommon\bMotorsport Manager\bMM_Data\bresources.assets" set "GAME=%~1\bsteamapps\bcommon\bMotorsport Manager"
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
if not exist "%GAME%\bMM_Data\bresources.assets" goto fail
echo.
echo   游戏目录: %GAME%

rem ---------- 4) 找补丁本体 ----------
set "SRC="
if exist "%HERE%\bresources.assets" set "SRC=%HERE%\bresources.assets"
if not defined SRC if exist "%HERE%\bpatch\bresources.assets" set "SRC=%HERE%\bpatch\bresources.assets"
if not defined SRC if exist "%HERE%\b..\bresources.assets" set "SRC=%HERE%\b..\bresources.assets"
if not defined SRC goto nosrc

rem ---------- 5) 备份 + 安装 ----------
for %%A in ("%GAME%\bMM_Data\bresources.assets") do set "CURSIZE=%%~zA"
if not defined CURSIZE set "CURSIZE=0"
if %CURSIZE% LSS 300000000 goto sizeok
echo.
echo   [警告] 当前的 resources.assets 已经是汉化过的版本（%CURSIZE% 字节）。
echo          继续会把汉化文件当成原版备份，以后卸载就无法还原英文了。
echo          建议先用 Steam 的「验证游戏文件完整性」还原英文版，再运行本安装。
echo.
pause
:sizeok
set "BAK=%GAME%\bMM_Data\bresources.assets.orig"
if exist "%BAK%" goto nobackup
echo   [1/2] 正在备份原文件为 resources.assets.orig ...
copy /y "%GAME%\bMM_Data\bresources.assets" "%BAK%" >nul
if errorlevel 1 goto copyfail
goto install

:nobackup
echo   [1/2] 已存在备份，跳过备份。

:install
echo   [2/2] 正在安装汉化 ...
copy /y "%SRC%" "%GAME%\bMM_Data\bresources.assets" >nul
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
'''

UNINSTALL = r'''@echo off
setlocal
title Motorsport Manager 汉化卸载

set "HERE=%~dp0"
if "%HERE:~-1%"=="\b" set "HERE=%HERE:~0,-1%"
set "GAME="

if exist "%HERE%\bMM_Data\bresources.assets" set "GAME=%HERE%"
if not defined GAME if exist "%HERE%\bMotorsport Manager\bMM_Data\bresources.assets" set "GAME=%HERE%\bMotorsport Manager"
if not defined GAME if exist "%HERE%\b..\bMM_Data\bresources.assets" set "GAME=%HERE%\b.."
if not defined GAME if exist "%HERE%\b..\bMotorsport Manager\bMM_Data\bresources.assets" set "GAME=%HERE%\b..\bMotorsport Manager"

if not defined GAME for /f "tokens=2,*" %%a in ('reg query "HKCU\bSoftware\bValve\bSteam" /v SteamPath 2^>nul') do call :try "%%b"
if not defined GAME for /f "tokens=2,*" %%a in ('reg query "HKLM\bSOFTWARE\bWOW6432Node\bValve\bSteam" /v InstallPath 2^>nul') do call :try "%%b"
if not defined GAME if exist "%ProgramFiles(x86)%\bSteam\bsteamapps\bcommon\bMotorsport Manager\bMM_Data\bresources.assets.orig" set "GAME=%ProgramFiles(x86)%\bSteam\bsteamapps\bcommon\bMotorsport Manager"
if not defined GAME if exist "%ProgramFiles%\bSteam\bsteamapps\bcommon\bMotorsport Manager\bMM_Data\bresources.assets.orig" set "GAME=%ProgramFiles%\bSteam\bsteamapps\bcommon\bMotorsport Manager"

if not defined GAME goto ask
goto found

:try
if not defined GAME if exist "%~1\bsteamapps\bcommon\bMotorsport Manager\bMM_Data\bresources.assets.orig" set "GAME=%~1\bsteamapps\bcommon\bMotorsport Manager"
exit /b 0

:ask
echo.
set "GAME="
set /p GAME=请输入 Motorsport Manager 文件夹的完整路径: 
for /f "tokens=* delims=" %%i in ("%GAME%") do set "GAME=%%~i"
if "%GAME%"=="" goto fail

:found
set "BAK=%GAME%\bMM_Data\bresources.assets.orig"
if not exist "%BAK%" goto nobak
echo.
echo   游戏目录: %GAME%
echo   正在还原英文原版 ...
copy /y "%BAK%" "%GAME%\bMM_Data\bresources.assets" >nul
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
'''


def main():
    setup_console()
    os.makedirs(OUT, exist_ok=True)
    for name, text in (('安装汉化.bat', INSTALL), ('卸载还原.bat', UNINSTALL)):
        # '\b' is the placeholder for a real backslash
        data = text.replace(BS + 'b', BS)
        data = data.replace('\r\n', '\n').replace('\n', '\r\n').encode('gbk')
        path = os.path.join(OUT, name)
        with open(path, 'wb') as f:
            f.write(data)
        print('%-16s %5d bytes (GBK)' % (name, len(data)))


if __name__ == '__main__':
    main()
