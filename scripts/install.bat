@echo off
REM Install all backend dependencies (including dev)
cd /d "%~dp0..\backend"
uv sync --all-extras
echo Done.
echo.
pause
