"""
ทดสอบว่า scancode เข้าเกม MuMu จริงไหม (แยกจากระบบกล้อง เพื่อไล่ปัญหาให้ตรงจุด)

วิธีใช้:
    python test_key.py
แล้วรีบคลิกหน้าต่าง MuMu ให้ focus ภายในเวลานับถอยหลัง
โปรแกรมจะ: กด W ค้าง 1 วิ (ฮีโร่ควรเดินขึ้น) -> แตะ H, Q, E, R ทีละปุ่ม (ควรมี action ในเกม)

ถ้าฮีโร่ "ไม่ขยับ/สกิลไม่ลั่น":
  1) ยังไม่ได้รันเป็น Administrator  -> ปิดแล้วรันผ่าน "เล่น Mobile Legends.bat" หรือคลิกขวา Run as admin
  2) MuMu ยังไม่ได้แมปปุ่ม           -> ตั้ง keymapping ใน MuMu (ดู README): joystick=WASD, สกิล=H/Q/E/R
  3) หน้าต่าง MuMu ไม่ได้ focus       -> ต้องคลิกที่หน้าต่างเกมก่อนถึงเวลายิง
"""
from __future__ import annotations

import sys
import time

# บังคับ console เป็น UTF-8 กัน UnicodeEncodeError ตอน print ภาษาไทย
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from input_sender import _send_scancode, SCANCODES, EXTENDED_KEYS

COUNTDOWN = 6.0
HOLD_W_SEC = 1.0
TAP_MS = 60
TAP_KEYS = ["h", "q", "e", "r"]


def _tap(key, hold_ms=TAP_MS):
    sc = SCANCODES[key]
    ext = key in EXTENDED_KEYS
    _send_scancode(sc, key_up=False, extended=ext)
    time.sleep(hold_ms / 1000.0)
    _send_scancode(sc, key_up=True, extended=ext)


def main():
    print("=" * 60)
    print(" ทดสอบยิง scancode เข้า MuMu")
    print(f" รีบคลิกหน้าต่าง MuMu ให้ focus ภายใน {COUNTDOWN:.0f} วินาที!")
    print("=" * 60)
    for i in range(int(COUNTDOWN), 0, -1):
        print(f"  ... {i}")
        time.sleep(1.0)

    print("[test] กด W ค้าง 1 วิ (ฮีโร่ควรเดินขึ้น)")
    scw = SCANCODES["w"]
    _send_scancode(scw, key_up=False, extended=False)
    time.sleep(HOLD_W_SEC)
    _send_scancode(scw, key_up=True, extended=False)

    for k in TAP_KEYS:
        print(f"[test] แตะ '{k}'")
        _tap(k)
        time.sleep(0.6)

    print("[test] จบการทดสอบ — ถ้าฮีโร่ขยับ/สกิลลั่น = scancode เข้าเกมแล้ว")


if __name__ == "__main__":
    main()
