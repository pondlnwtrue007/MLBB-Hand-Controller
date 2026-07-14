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
  --windowed ^
  --onefile ^
  --collect-all mediapipe ^
  --collect-data cv2 ^
  --hidden-import win32gui ^
  --hidden-import win32con ^
  --add-data "config.json;." ^
  --add-data "hand_landmarker.task;." ^
  --add-data "icon.ico;."

echo.
echo เสร็จแล้ว! ไฟล์เดียวจบที่  dist\ML Hand Controller.exe
echo (แจกไฟล์ .exe ไฟล์เดียวได้เลย — config.json จะสร้างใน appdata ตอนรันครั้งแรก)
pause
