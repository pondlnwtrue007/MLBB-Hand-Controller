"""
ยิงปุ่มเข้าเกมด้วย hardware scancode ผ่าน SendInput (ctypes)

ทำไมต้อง scancode: MuMu Player และเกมที่อ่าน DirectInput/Raw Input มักไม่รับ virtual-key
ธรรมดา (เช่น keybd_event ด้วย VK code) — ต้องยิงเป็น hardware scancode ที่เกมเห็นเหมือนกด
คีย์บอร์ดจริง. วิธีนี้พิสูจน์แล้วว่า MuMu รับได้ (โปรเจกต์ Cookie Run ยิงเข้า MuMu สำเร็จ)

สำคัญ: ต้องรันโปรแกรมนี้ "as Administrator" ให้ระดับสิทธิ์เท่ากับ MuMu ไม่งั้น Windows (UIPI)
จะบล็อก input เงียบ ๆ (โปรแกรมทำงานแต่ปุ่มไม่เข้าเกม). ตัว .bat ที่ให้มา auto-elevate ให้แล้ว

- apply(held_keys) : กด/ปล่อยปุ่มเดิน (W/A/S/D) ให้ตรงกับชุดที่ต้องกดค้างตอนนี้ (diff)
- tap(key)         : แตะปุ่ม 1 ที (สกิล H/Q/E/R/F/B/G/1/2/3)
คลาสจำเองว่าปุ่มไหนกดค้างอยู่ (self._down) และปล่อยให้อัตโนมัติเมื่อไม่ focus / test / ปิดโปรแกรม
"""
from __future__ import annotations

import ctypes
import time
from ctypes import wintypes

# ---------------------------------------------------------------------------
# ค่าคงที่ของ SendInput
# ---------------------------------------------------------------------------
INPUT_KEYBOARD = 1
KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_SCANCODE = 0x0008

ULONG_PTR = ctypes.c_size_t  # pointer-sized (ถูกต้องทั้ง 32/64-bit)


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("type", wintypes.DWORD), ("u", _INPUTUNION)]


_SendInput = ctypes.windll.user32.SendInput
_SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
_SendInput.restype = wintypes.UINT


# ---------------------------------------------------------------------------
# ตาราง scancode (Scan Code Set 1 / make codes) — ชื่อปุ่ม -> scancode
#   ครบทุกปุ่มที่เกมใช้: เดิน w/a/s/d + สกิล h/q/e/r/f/b/g + อัพสกิล 1/2/3
# ---------------------------------------------------------------------------
SCANCODES = {
    "a": 0x1E, "b": 0x30, "c": 0x2E, "d": 0x20, "e": 0x12, "f": 0x21,
    "g": 0x22, "h": 0x23, "i": 0x17, "j": 0x24, "k": 0x25, "l": 0x26,
    "m": 0x32, "n": 0x31, "o": 0x18, "p": 0x19, "q": 0x10, "r": 0x13,
    "s": 0x1F, "t": 0x14, "u": 0x16, "v": 0x2F, "w": 0x11, "x": 0x2D,
    "y": 0x15, "z": 0x2C,
    "1": 0x02, "2": 0x03, "3": 0x04, "4": 0x05, "5": 0x06,
    "6": 0x07, "7": 0x08, "8": 0x09, "9": 0x0A, "0": 0x0B,
    "space": 0x39, "enter": 0x1C, "esc": 0x01, "tab": 0x0F,
    "lshift": 0x2A, "shift": 0x2A, "lctrl": 0x1D, "ctrl": 0x1D,
    # ลูกศร (extended keys — จะแนบ KEYEVENTF_EXTENDEDKEY ให้)
    "up": 0x48, "down": 0x50, "left": 0x4B, "right": 0x4D,
}

EXTENDED_KEYS = {"up", "down", "left", "right"}


# ผลลัพธ์ของการยิงปุ่ม (ไว้โชว์บน overlay / log)
FIRED = "FIRED"
BLOCKED = "BLOCKED"      # ไม่ได้ยิงเพราะ MuMu ไม่ได้ focus
TEST = "TEST"            # test mode — โชว์อย่างเดียว ไม่ยิงจริง
NO_KEY = "NO_KEY"        # ชื่อปุ่มไม่มีในตาราง scancode


def _send_scancode(scancode: int, key_up: bool, extended: bool) -> None:
    flags = KEYEVENTF_SCANCODE
    if extended:
        flags |= KEYEVENTF_EXTENDEDKEY
    if key_up:
        flags |= KEYEVENTF_KEYUP
    inp = INPUT(type=INPUT_KEYBOARD)
    inp.ki = KEYBDINPUT(wVk=0, wScan=scancode, dwFlags=flags, time=0, dwExtraInfo=0)
    _SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))


class InputSender:
    """
    ยิงปุ่มเข้าเกม (กดค้าง + แตะ) + ตรวจ focus + รองรับ test mode
    ทำงานกับ "ชื่อปุ่มจริง" ตรง ๆ (เช่น 'w', 'q') ไม่ต้อง map action
    """

    def __init__(self, cfg, test_mode: bool = False):
        self.cfg = cfg
        self.test_mode = test_mode
        self._down: set[str] = set()   # ปุ่มที่กดค้างอยู่จริง ณ ตอนนี้
        # lazy import: ให้โปรแกรมยังเปิด preview ได้แม้ยังไม่ได้ลง pywin32
        try:
            import win32gui  # type: ignore
            self._win32gui = win32gui
        except ImportError:
            self._win32gui = None
            print("[input] เตือน: ไม่พบ pywin32 — จะตรวจ focus ไม่ได้ "
                  "(ยิงปุ่มได้เฉพาะใน test mode). ติดตั้งด้วย: pip install pywin32")

    # -- focus guard --------------------------------------------------------
    def foreground_title(self) -> str:
        if self._win32gui is None:
            return ""
        try:
            hwnd = self._win32gui.GetForegroundWindow()
            return self._win32gui.GetWindowText(hwnd) or ""
        except Exception:
            return ""

    def is_target_focused(self) -> bool:
        keyword = (self.cfg.target_window or "").lower()
        if not keyword:
            return True
        return keyword in self.foreground_title().lower()

    # -- primitive กด/ปล่อยปุ่มเดี่ยว --------------------------------------
    def _key_down(self, key_name: str) -> None:
        sc = SCANCODES.get(key_name.lower())
        if sc is None:
            print(f"[input] ไม่รู้จักปุ่ม '{key_name}' — เพิ่มใน SCANCODES ใน input_sender.py")
            return
        _send_scancode(sc, key_up=False, extended=key_name.lower() in EXTENDED_KEYS)
        self._down.add(key_name.lower())

    def _key_up(self, key_name: str) -> None:
        sc = SCANCODES.get(key_name.lower())
        if sc is not None:
            _send_scancode(sc, key_up=True, extended=key_name.lower() in EXTENDED_KEYS)
        self._down.discard(key_name.lower())

    def release_all(self) -> None:
        for k in list(self._down):
            self._key_up(k)

    # -- กดค้างตามทิศเดิน (W/A/S/D) ---------------------------------------
    def apply(self, held_keys) -> str:
        """
        กด/ปล่อยปุ่มให้ตรงกับชุดปุ่มที่ต้องกดค้างตอนนี้ (diff กับที่ค้างอยู่)
        คืนสถานะ OK / TEST / BLOCKED
        """
        desired = {str(k).lower() for k in held_keys}

        if self.test_mode:
            self.release_all()
            return TEST
        if not self.is_target_focused():
            self.release_all()
            return BLOCKED

        for k in self._down - desired:
            self._key_up(k)
        for k in desired - self._down:
            self._key_down(k)
        return "OK"

    # -- แตะปุ่ม 1 ที (สกิล) ------------------------------------------------
    def tap(self, key_name: str) -> str:
        """แตะปุ่มสกิล 1 ที คืนสถานะ FIRED / BLOCKED / TEST / NO_KEY"""
        if not key_name:
            return NO_KEY
        if self.test_mode:
            return TEST
        if not self.is_target_focused():
            return BLOCKED
        sc = SCANCODES.get(key_name.lower())
        if sc is None:
            print(f"[input] ไม่รู้จักปุ่ม '{key_name}' — เพิ่มใน SCANCODES ใน input_sender.py")
            return NO_KEY
        extended = key_name.lower() in EXTENDED_KEYS
        _send_scancode(sc, key_up=False, extended=extended)
        time.sleep(max(0, self.cfg.output.tap_ms) / 1000.0)
        _send_scancode(sc, key_up=True, extended=extended)
        return FIRED
