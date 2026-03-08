@echo off
REM TasteBud Pipeline - list, check auth, and run all enabled pipelines
cd /d "%~dp0..\backend"
uv run tastebud-pipeline %*
echo.
pause
