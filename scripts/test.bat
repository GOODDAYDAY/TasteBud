@echo off
REM Run all backend tests
cd /d "%~dp0..\backend"
uv run pytest -v %*
echo.
pause
