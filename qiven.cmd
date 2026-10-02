@echo off
rem Thin UX launcher (WG-5): transfers control to the workspace bootstrap.
rem No Devkit discovery, no pins, no fallbacks live here. The ONLY
rem launcher-owned surface is the interpreter availability probe below:
rem a launcher-level failure is a typed four-element carrier (WHAT + WHY
rem + evidence + NEXT: FIX), never a raw cmd error (P0 repair batch B2,
rem register row workspace-launcher-qiven-cmd; the devkit qiven.cmd twin
rem is the pattern).
setlocal EnableExtensions
set "QIVEN_BOOTSTRAP_PY=%~dp0bootstrap\qiven-bootstrap.py"

if defined QIVEN_PYTHON goto validate_configured_python

:try_python
where python >nul 2>nul
if errorlevel 1 goto try_py_launcher
python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 9) else 1)" >nul 2>nul
if errorlevel 1 goto try_py_launcher
goto use_python

:try_py_launcher
where py >nul 2>nul
if errorlevel 1 goto no_supported_python
py -3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 9) else 1)" >nul 2>nul
if errorlevel 1 goto no_supported_python
goto use_py_launcher

:validate_configured_python
"%QIVEN_PYTHON%" -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 9) else 1)" >nul 2>nul
if errorlevel 1 goto configured_python_invalid
goto use_configured_python

:configured_python_invalid
set "QIVEN_PY_PROBE=%TEMP%\qiven-python-probe-%RANDOM%.txt"
set "QIVEN_PY_VERSION=unknown - the interpreter printed no version"
"%QIVEN_PYTHON%" -c "import sys; print('.'.join(map(str, sys.version_info[:3])))" > "%QIVEN_PY_PROBE%" 2>nul
if exist "%QIVEN_PY_PROBE%" set /p QIVEN_PY_VERSION=<"%QIVEN_PY_PROBE%"
if exist "%QIVEN_PY_PROBE%" del "%QIVEN_PY_PROBE%" >nul 2>nul
echo [FAIL] QIVEN_PYTHON must point to Python 3.9 or newer: %QIVEN_PYTHON%
echo   evidence: the configured interpreter reports Python %QIVEN_PY_VERSION%; the probe requires "sys.version_info >= (3, 9)"
echo   NEXT: FIX - point QIVEN_PYTHON at a Python 3.9 or newer executable, then re-run
exit /b 2

:no_supported_python
echo [FAIL] Qiven workspace bootstrap requires Python 3.9 or newer. Set QIVEN_PYTHON or make a supported python available on PATH.
echo   evidence: every candidate failed the 3.9+ probe - where python, python -c "sys.version_info >= (3, 9)", where py, py -3 -c "sys.version_info >= (3, 9)"
echo   NEXT: FIX - set QIVEN_PYTHON to a Python 3.9+ executable path, or install Python 3.9+ so python or py -3 resolves to it, then re-run
exit /b 2

:use_configured_python
"%QIVEN_PYTHON%" "%QIVEN_BOOTSTRAP_PY%" %*
exit /b %errorlevel%

:use_python
python "%QIVEN_BOOTSTRAP_PY%" %*
exit /b %errorlevel%

:use_py_launcher
py -3 "%QIVEN_BOOTSTRAP_PY%" %*
exit /b %errorlevel%
