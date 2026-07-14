"""
หาว่าหน้าต่าง MuMu ชื่ออะไรจริง ๆ เพื่อตั้งค่า target_window ใน config.json ให้ถูก

วิธีใช้:
    python check_window.py
แล้วรีบคลิกหน้าต่าง MuMu ให้ focus ภายในเวลานับถอยหลัง
โปรแกรมจะโชว์ชื่อหน้าต่างที่ focus อยู่ทุกครึ่งวินาที + list หน้าต่างทั้งหมดที่เปิดอยู่

เอาคำที่อยู่ในชื่อหน้าต่าง MuMu (เช่น 'MuMu' หรือ 'Player') ไปใส่ target_window ใน config.json
(ใส่แค่บางส่วนของชื่อก็ได้ ระบบเช็คแบบ substring ไม่สนตัวพิมพ์เล็ก/ใหญ่)
"""
from __future__ import annotations

import sys
import time

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import ctypes

user32 = ctypes.windll.user32


def foreground_title() -> str:
    hwnd = user32.GetForegroundWindow()
    n = user32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(n + 1)
    user32.GetWindowTextW(hwnd, buf, n + 1)
    return buf.value or "(no title)"


def list_windows():
    titles = []
    EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

    def cb(hwnd, _):
        if not user32.IsWindowVisible(hwnd):
            return True
        n = user32.GetWindowTextLengthW(hwnd)
        if n <= 0:
            return True
        buf = ctypes.create_unicode_buffer(n + 1)
        user32.GetWindowTextW(hwnd, buf, n + 1)
        if buf.value.strip():
            titles.append(buf.value)
        return True

    user32.EnumWindows(EnumWindowsProc(cb), 0)
    return titles


def main():
    print("=" * 64)
    print(" หาชื่อหน้าต่าง MuMu — รีบคลิกหน้าต่าง MuMu ให้ focus ใน 5 วินาที!")
    print("=" * 64)
    for i in range(5, 0, -1):
        print(f"  ... {i}")
        time.sleep(1.0)

    print("\n>>> ชื่อหน้าต่างที่ focus อยู่ (คลิก MuMu ค้างไว้) — จับ 6 วินาที:")
    seen = {}
    for _ in range(12):
        t = foreground_title()
        seen[t] = seen.get(t, 0) + 1
        print(f"    FOCUS = [{t}]")
        time.sleep(0.5)

    print("\n>>> หน้าต่างทั้งหมดที่เปิดอยู่ตอนนี้:")
    for t in list_windows():
        mark = "  <-- น่าจะใช่ MuMu?" if ("mumu" in t.lower() or "player" in t.lower()
                                          or "mobile" in t.lower() or "legend" in t.lower()) else ""
        print(f"    [{t}]{mark}")

    # เดาคำที่ควรใส่ใน target_window
    best = max(seen, key=seen.get) if seen else ""
    print("\n" + "=" * 64)
    print(f" หน้าต่างที่ focus บ่อยสุดตอนคลิก MuMu คือ: [{best}]")
    print(" -> เอา 'คำเด่น' ในชื่อนี้ไปใส่ target_window ใน config.json")
    print("    เช่น ถ้าชื่อคือ 'MuMuPlayer' ก็ใส่  \"target_window\": \"MuMu\"")
    print("    (หรือใส่ \"target_window\": \"\" เพื่อปิดการเช็ค focus = ยิงตลอด)")
    print("=" * 64)


if __name__ == "__main__":
    main()
