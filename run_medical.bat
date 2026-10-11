@echo off
echo ====================================
echo Medical Research Agent - Starting
echo ====================================
echo.

echo Checking Python installation...
python --version
if %errorlevel% neq 0 (
    echo ERROR: Python is not installed or not in PATH
    pause
    exit /b 1
)

echo.
echo Installing dependencies...
pip install -q -r requirements.txt

echo.
echo ====================================
echo Server starting on http://localhost:8000
echo.
echo Open in browser:
echo   Medical UI: http://localhost:8000/medical.html
echo.
echo Press Ctrl+C to stop the server
echo ====================================
echo.

python -m uvicorn servers.fastapi_server:app --host 0.0.0.0 --port 8000 --reload
