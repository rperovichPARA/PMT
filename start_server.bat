@echo off
echo ============================================
echo  Paradaim Portfolio.Tool Trading V2
echo ============================================
echo.

REM Pull latest changes from git
echo Pulling latest changes...
git pull origin master
if %ERRORLEVEL% NEQ 0 (
    echo WARNING: git pull failed. Continuing with current version...
    echo.
)

REM Install/update dependencies
echo Checking dependencies...
python -m pip install -q -r requirements.txt 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo Installing individual packages...
    python -m pip install -q fastapi uvicorn requests numpy pandas
)

echo.
echo Starting API server on http://localhost:8000 ...
echo Press Ctrl+C to stop the server.
echo.
python -m uvicorn api_server:app --host 0.0.0.0 --port 8000 --reload
pause
