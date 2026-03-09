@echo off
REM Build backend (type check) and frontend (production build)

echo === Backend: mypy type check ===
cd /d "%~dp0..\backend"
uv run mypy src/
if %ERRORLEVEL% NEQ 0 goto :fail

echo === Frontend: production build ===
cd /d "%~dp0..\frontend"
if exist node_modules (
    npm run build
    if %ERRORLEVEL% NEQ 0 goto :fail
) else (
    echo Skipped: node_modules not found. Run install first.
)

echo.
echo Build passed.
goto :eof

:fail
echo.
echo Build failed.
pause
exit /b 1
