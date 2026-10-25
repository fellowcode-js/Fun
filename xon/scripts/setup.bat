@echo off
rem Double-click friendly wrapper for scripts\setup.ps1 (Windows). Untested on real Windows.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup.ps1"
pause
