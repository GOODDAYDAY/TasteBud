@echo off
REM Start the TasteBud backend server
cd /d "%~dp0..\backend"
uv run python -m tastebud %*
