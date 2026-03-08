@echo off
REM Run ruff lint + format check + mypy type check
cd /d "%~dp0..\backend"

echo === ruff check ===
uv run ruff check .
if %ERRORLEVEL% NEQ 0 goto :fail

echo === ruff format check ===
uv run ruff format --check .
if %ERRORLEVEL% NEQ 0 goto :fail

echo === mypy ===
uv run mypy src/
if %ERRORLEVEL% NEQ 0 goto :fail

echo.
echo All checks passed.
goto :eof

echo.
pause
goto :eof

:fail
echo.
echo Checks failed.
pause
exit /b 1
