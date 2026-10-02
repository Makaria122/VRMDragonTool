@echo off
setlocal
cd /d "%~dp0"
rem Prefer a Python that actually provides Tkinter; py -3 may select an embedded runtime.
python -c "import sys, tkinter; assert sys.version_info >= (3, 10)" >nul 2>&1
if not errorlevel 1 goto use_python
py -3.10 -c "import sys, tkinter; assert sys.version_info >= (3, 10)" >nul 2>&1
if not errorlevel 1 goto use_py310
py -3 -c "import sys, tkinter; assert sys.version_info >= (3, 10)" >nul 2>&1
if not errorlevel 1 goto use_py3
echo Python 3.10+ with Tkinter was not found. Install/enable Tkinter, then retry.
pause
exit /b 1
:use_python
python "%~dp0Tool\launch.py"
goto done
:use_py310
py -3.10 "%~dp0Tool\launch.py"
goto done
:use_py3
py -3 "%~dp0Tool\launch.py"
:done
if errorlevel 1 (
    echo The GUI failed to start. See the error above.
    pause
    exit /b 1
)
exit /b 0
