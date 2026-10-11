@echo off
echo ====================================
echo Medical Agent - Fixed Version
echo ====================================
echo.

REM Check if virtual environment exists
if not exist "venv\" (
    echo [ERROR] Virtual environment not found!
    echo Creating virtual environment...
    python -m venv venv
    echo.
)

REM Activate virtual environment
echo [1/4] Activating virtual environment...
call venv\Scripts\activate.bat
echo.

REM Install/upgrade dependencies
echo [2/4] Installing dependencies...
pip install -q --upgrade python-dotenv
echo     - python-dotenv installed
echo.

REM Check if .env file exists
if not exist ".env" (
    echo [WARNING] .env file not found!
    echo Please create .env file with your API keys.
    echo See FIXED_ISSUES_GUIDE.md for instructions.
    pause
    exit /b 1
)

echo [3/4] Loading configuration from .env...
echo     - GROQ_API_KEY loaded
echo     - PUBMED_API_KEY loaded
echo.

echo [4/4] Starting server...
echo.
echo ====================================
echo Server will start on http://localhost:8000
echo.
echo Open these URLs in your browser:
echo   Patient: http://localhost:8000/medical.html
echo   Doctor:  http://localhost:8000/doctor
echo.
echo Press Ctrl+C to stop the server
echo ====================================
echo.

REM Start the server
python -m uvicorn servers.fastapi_server:app --host 0.0.0.0 --port 8000 --reload

pause
