@echo off
chcp 65001 >nul
title Opportunity Hub 서버
cd /d "%~dp0"
echo ========================================
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /c:"IPv4"') do (
    set ip=%%a
    goto :found
)
:found
set ip=%ip: =%
echo  접속 주소: http://%ip%:8888
echo  이 창을 닫으면 서버가 꺼집니다.
echo ========================================
python -m http.server 8888
