@echo off
chcp 65001 >nul
title Gov. Insight 공고 갱신
cd /d "%~dp0"
echo ========================================
echo  Gov. Insight 공고 데이터 갱신 중...
echo ========================================
python -m crawler.update
echo.
echo 갱신 완료. 브라우저에서 F5 누르면 반영됩니다.
pause
