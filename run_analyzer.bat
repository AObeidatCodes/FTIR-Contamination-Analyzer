@echo off
REM ==========================================================================
REM  FTIR Contamination Analyzer - Windows launcher. Double-click to start.
REM  The first time, it installs the packages the app needs (a few minutes).
REM  Author: Ali Obeidat
REM ==========================================================================
setlocal
cd /d "%~dp0"
title FTIR Contamination Analyzer

REM 1. Find Python: the "py" launcher from python.org first, then "python"
set "PY="
set "PYW="
py -3 --version >nul 2>nul && (set "PY=py -3" & set "PYW=pyw -3")
if not defined PY python --version >nul 2>nul && (set "PY=python" & set "PYW=pythonw")
if not defined PY goto nopython

REM 2. Python 3.10 or newer is needed
%PY% -c "import sys; sys.exit(sys.version_info < (3, 10))" || goto oldpython

REM 3. First start only: install the packages listed in requirements.txt
set CHECK=import numpy, pandas, scipy, matplotlib, plotly, openpyxl; from PySide6 import QtWidgets
%PY% -c "%CHECK%" >nul 2>nul
if errorlevel 1 (
    echo.
    echo  First start: installing the packages the analyzer needs.
    echo  This takes a few minutes and happens only once.
    echo.
    %PY% -m pip install --upgrade pip
    %PY% -m pip install -r requirements.txt || goto installfailed
)

REM 4. Make sure everything loads (shows the error here if not), then start without a console window
%PY% -c "%CHECK%" || goto brokeninstall
start "" %PYW% run_analyzer.py %*
exit /b 0

:brokeninstall
echo.
echo  The packages are installed but could not be loaded: see the message above.
echo  Installing Python 3.13 from python.org usually fixes this.
echo.
pause
exit /b 1

:nopython
echo.
echo  Python was not found on this computer.
echo  1. Install Python 3.13 from https://www.python.org/downloads/
echo     (tick "Add python.exe to PATH" in the installer)
echo  2. Double-click run_analyzer.bat again.
echo.
pause
exit /b 1

:oldpython
echo.
echo  This Python is too old. Install Python 3.13 from https://www.python.org/downloads/
echo.
pause
exit /b 1

:installfailed
echo.
echo  The packages could not be installed. Check the internet connection and try again.
echo  (On a company laptop, installing packages may be blocked by IT.)
echo.
pause
exit /b 1
