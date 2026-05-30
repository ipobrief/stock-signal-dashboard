@echo off
cd /d "%~dp0"
chcp 65001 >nul
echo.
echo   ============================================
echo     데이터 갱신을 시작합니다
echo     (크롤링 + GitHub 푸시 자동 진행)
echo   ============================================
echo.
python update_data.py
echo.
echo   이 창은 닫으셔도 됩니다.
pause
