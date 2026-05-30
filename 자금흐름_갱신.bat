@echo off
cd /d "%~dp0"
chcp 65001 >nul
echo.
echo   ============================================
echo     산업 자금흐름(기관 지분) 갱신을 시작합니다
echo     (DART 수집 + GitHub 푸시 자동 진행)
echo   ============================================
echo.
python update_fund.py
echo.
echo   이 창은 닫으셔도 됩니다.
pause
