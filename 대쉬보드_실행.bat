@echo off
cd /d "%~dp0"
echo ============================================
echo   Stock Signal Dashboard starting...
echo   A browser tab will open automatically.
echo   Press Ctrl+C in this window to stop.
echo ============================================
echo.
python -m streamlit run streamlit_app.py
pause
