@echo off
setlocal
cd /d "%~dp0"
python -c "import sys; assert sys.version_info >= (3, 10)" >nul 2>&1
if not errorlevel 1 (
    python demo_launcher.py
    goto finished
)
py -3 -c "import sys; assert sys.version_info >= (3, 10)" >nul 2>&1
if not errorlevel 1 (
    py -3 demo_launcher.py
    goto finished
)
echo Python 3.10 or newer is required. Install Python and enable Add Python to PATH.
echo Then double-click this file again. See README.md for instructions.
:finished
echo.
echo Demo stopped. You can close this window.
pause
