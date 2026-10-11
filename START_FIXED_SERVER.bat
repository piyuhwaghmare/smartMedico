@echo off
cls
echo ========================================
echo MEDICAL AGENT - COMPLETE FIX
echo ========================================
echo.
echo Using: Groq (Cloud API - Fast!)
echo Model: llama-3.1-8b-instant
echo.
echo ========================================
echo.

echo [1/4] Activating virtual environment...
call venv\Scripts\activate.bat

echo [2/4] Ensuring Groq package is installed...
pip install -q langchain-groq

echo [3/4] Starting server...
echo.
echo ========================================
echo Server URL: http://localhost:8000
echo.
echo Open these pages:
echo   Patient: http://localhost:8000/medical.html
echo   Doctor:  http://localhost:8000/doctor
echo.
echo Expected flow (15-20 seconds total):
echo   1. Patient submits query
echo   2. Search PubMed (5-10s)
echo   3. Groq synthesis (2-5s) - FAST!
echo   4. Doctor approves
echo   5. Patient receives result
echo.
echo Watch for: [LLM] Using Groq (cloud) - FAST!
echo ========================================
echo.

python -m uvicorn servers.fastapi_server:app --host 0.0.0.0 --port 8000 --reload

pause
