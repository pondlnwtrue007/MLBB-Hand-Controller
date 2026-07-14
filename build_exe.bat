@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================================
echo   Building ML Hand Controller .exe (PyInstaller)
echo   ใช้เวลาสักครู่ (bundle mediapipe + opencv)...
echo ============================================================

py -m PyInstaller main.py ^
  --name "ML Hand Controller" ^
  --icon icon.ico ^
  --noconfirm ^
  --console ^
  --collect-all mediapipe ^
  --collect-data cv2 ^
  --hidden-import win32gui ^
  --hidden-import win32con ^
  --add-data "config.json;." ^
  --add-data "hand_landmarker.task;." ^
  --add-data "icon.ico;."

echo.
echo เสร็จแล้ว! ไฟล์อยู่ที่  dist\ML Hand Controller\ML Hand Controller.exe
echo (แจกทั้งโฟลเดอร์ dist\ML Hand Controller — zip แล้วส่งได้เลย)
pause
