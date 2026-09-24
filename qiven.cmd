@echo off
rem Thin UX launcher (WG-5): transfers control to the workspace bootstrap.
rem No Devkit discovery, no pins, no fallbacks live here.
setlocal
python "%~dp0bootstrap\qiven-bootstrap.py" %*
exit /b %errorlevel%
