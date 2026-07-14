@echo off
chcp 65001 >nul
cd /d "%~dp0"

REM --- ขอสิทธิ์ Administrator ให้เท่ากับ MuMu (ไม่งั้น Windows บล็อก input เงียบ ๆ) ---
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo กำลังขอสิทธิ์ Administrator...
    powershell -Command "Start-Process -Verb RunAs -FilePath '%~f0'"
    exit /b
)

echo ============================================================
echo   Mobile Legends - Hand Controller
echo   เปิด MuMu + เข้าแมตช์ไว้ก่อน แล้วสลับมาหน้าต่าง preview
echo ============================================================

REM --- รันด้วย py launcher ถ้าไม่มีลอง python ---
where py >nul 2>&1
if %errorlevel%==0 (
    py main.py %*
) else (
    python main.py %*
)

pause
