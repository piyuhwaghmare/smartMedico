@echo off
echo ====================================
echo Medical Agent - Restart Server
echo ====================================
echo.

echo [1/3] Stopping any running servers...
taskkill /F /IM python.exe /FI "WINDOWTITLE eq *uvicorn*" 2>nul
timeout /t 2 /nobreak >nul
echo     Done.
echo.

echo [2/3] Activating virtual environment...
call venv\Scripts\activate.bat
echo.

echo [3/3] Starting server with fixes...
echo.
echo ====================================
echo Server starting on http://localhost:8000
echo.
echo Open these URLs:
echo   Patient: http://localhost:8000/medical.html
echo   Doctor:  http://localhost:8000/doctor
echo.
echo Watch for these messages:
echo   [LLM] Attempting to use Groq
echo   [LLM] ✅ Groq initialized successfully
echo.
echo Press Ctrl+C to stop
echo ====================================
echo.

python -m uvicorn servers.fastapi_server:app --host 0.0.0.0 --port 8000 --reload
