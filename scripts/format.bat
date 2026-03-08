@echo off
REM Auto-format backend code with ruff
cd /d "%~dp0..\backend"
uv run ruff format .
uv run ruff check --fix .
echo Done.
echo.
pause
