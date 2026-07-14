"""
โหลดและ validate config.json เป็น dataclass ที่ใช้งานง่าย พร้อมค่า default ครบ
แก้ค่าใน config.json แล้วกด R ในโปรแกรมเพื่อ reload ทันที (ไม่ต้องปิด) — ปรับจูนหน้ากล้องได้เร็ว

เกม: Mobile Legends (MuMu Player)
  มือซ้าย  = virtual joystick เดิน (W/A/S/D) — กดค้างตามทิศ
  มือขวา   = cursor เลือก "วง" ปุ่ม + กำหมัดยืนยัน = แตะปุ่มนั้น
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, asdict


DEFAULTS = {
    "camera": {"index": 0, "width": 1280, "height": 720, "fps": 30,
               "backend": "DSHOW", "mjpg": True, "mirror": True},
    "detect_width": 480,          # ย่อภาพเหลือกว้างเท่านี้ก่อนส่งเข้า MediaPipe (fps สูงขึ้น)
    "smoothing": 0.5,             # EMA ตำแหน่งมือ (0..1) ยิ่งมากยิ่งไว/สั่นง่าย ยิ่งน้อยยิ่งนิ่ง/หน่วง
    "target_window": "Android Device",  # ยิงปุ่มเฉพาะตอนหน้าต่างที่ชื่อมีคำนี้ focus
                                          # (หน้าต่างเกม MuMu มักชื่อ "Android Device")
    "hand_assignment": "position",  # "position" (ฝั่งซ้ายเฟรม=เดิน) หรือ "handedness"
    "swap_hands": False,          # สลับว่ามือไหนเดิน/มือไหนสกิล ถ้าจับผิดข้าง
    "always_on_top": True,        # หน้าต่าง preview ลอยหน้าสุด (ดูมือระหว่างเล่น) — กด P สลับ
    "calibrate_countdown": 4.0,   # กด C แล้วนับถอยหลังกี่วิ ก่อนตั้งจุดกลาง joystick
    "prep_countdown": 8.0,        # ออกจาก test แล้วให้เวลากี่วิ ก่อนเริ่มยิงปุ่มจริง
    "move": {
        "directions": 4,          # 4 = ตรงเท่านั้น, 8 = มีเฉียง (W+A ฯลฯ)
        "deadzone": 0.10,         # ระยะจากจุดกลาง (สัดส่วนความกว้างจอ) เกินนี้ = เริ่มเดิน
        "deadzone_out": 0.07,     # ต่ำกว่านี้ = หยุด (< deadzone เพื่อกันกระพริบ)
        "origin": [0.25, 0.55],   # จุดกลาง joystick (x,y normalized 0..1) — กด C ตั้งใหม่ได้
        "keys": {"up": "w", "down": "s", "left": "a", "right": "d"},
    },
    "gesture": {
        "fire_gesture": "pinch",  # ท่ายิง: "pinch" (จีบนิ้ว-แนะนำ) / "fist" (กำหมัด) / "trigger" (เหนี่ยวไก)
        "fist_max_open": 1,       # [fist] กำหมัด = นิ้ว(จาก 4)เหยียดได้ไม่เกินกี่นิ้ว
        "open_min": 3,            # [fist] แบมือ (re-arm) = ต้องเหยียด >= กี่นิ้ว ถึงยิงใหม่ได้
        "pinch_on": 0.55,         # [pinch] จีบติดเมื่อระยะโป้ง-ชี้ < ค่านี้ (ใหญ่=จีบหลวมก็ติด)
        "pinch_off": 0.78,        # [pinch] คลายเมื่อ > ค่านี้ (ต้องคลายก่อนจีบยิงใหม่)
    },
    "output": {
        "tap_ms": 55,             # กดปุ่มสกิลค้างกี่ ms (ต่ำกว่า ~16ms เกมไม่เห็น)
        "repeat_interval": 0.15,  # วงที่ repeat=true (เช่นโจมตี) รัวทุกกี่วิ ตอนทำท่าค้าง
    },
    "zones": [
        {"name": "attack", "key": "h", "cx": 0.82, "cy": 0.55, "r": 0.090, "repeat": True},
        {"name": "skill1", "key": "q", "cx": 0.70, "cy": 0.73, "r": 0.075, "repeat": False},
        {"name": "skill2", "key": "e", "cx": 0.83, "cy": 0.81, "r": 0.075, "repeat": False},
        {"name": "skill3", "key": "r", "cx": 0.95, "cy": 0.70, "r": 0.075, "repeat": False},
        {"name": "spell",  "key": "f", "cx": 0.63, "cy": 0.55, "r": 0.065, "repeat": False},
        {"name": "recall", "key": "b", "cx": 0.94, "cy": 0.20, "r": 0.055, "repeat": False},
        {"name": "regen",  "key": "g", "cx": 0.80, "cy": 0.18, "r": 0.055, "repeat": False},
        {"name": "up1",    "key": "1", "cx": 0.58, "cy": 0.13, "r": 0.050, "repeat": False},
        {"name": "up2",    "key": "2", "cx": 0.67, "cy": 0.11, "r": 0.050, "repeat": False},
        {"name": "up3",    "key": "3", "cx": 0.76, "cy": 0.13, "r": 0.050, "repeat": False},
    ],
}


def _deep_merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


@dataclass
class Camera:
    index: int = 0
    width: int = 1280
    height: int = 720
    fps: int = 30
    backend: str = "DSHOW"
    mjpg: bool = True
    mirror: bool = True


@dataclass
class Move:
    directions: int = 4
    deadzone: float = 0.10
    deadzone_out: float = 0.07
    origin: tuple = (0.25, 0.55)
    keys: dict = field(default_factory=lambda: dict(DEFAULTS["move"]["keys"]))


@dataclass
class Gesture:
    fire_gesture: str = "pinch"
    fist_max_open: int = 1
    open_min: int = 3
    pinch_on: float = 0.55
    pinch_off: float = 0.78


@dataclass
class Output:
    tap_ms: int = 55
    repeat_interval: float = 0.18


@dataclass
class Zone:
    name: str
    key: str
    cx: float
    cy: float
    r: float
    repeat: bool = False


@dataclass
class Config:
    camera: Camera = field(default_factory=Camera)
    detect_width: int = 480
    smoothing: float = 0.5
    target_window: str = "Android Device"
    hand_assignment: str = "position"
    swap_hands: bool = False
    always_on_top: bool = True
    calibrate_countdown: float = 4.0
    prep_countdown: float = 8.0
    move: Move = field(default_factory=Move)
    gesture: Gesture = field(default_factory=Gesture)
    output: Output = field(default_factory=Output)
    zones: list = field(default_factory=list)

    _path: str = ""

    @staticmethod
    def load(path: str = "config.json") -> "Config":
        raw = {}
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    raw = json.load(f)
            except (json.JSONDecodeError, OSError) as e:
                print(f"[config] อ่าน {path} ไม่ได้ ({e}) — ใช้ค่า default")
                raw = {}
        else:
            print(f"[config] ไม่พบ {path} — ใช้ค่า default")

        m = _deep_merge(DEFAULTS, raw)
        mv = m["move"]
        cfg = Config(
            camera=Camera(**m["camera"]),
            detect_width=int(m["detect_width"]),
            smoothing=float(m["smoothing"]),
            target_window=str(m["target_window"]),
            hand_assignment=str(m["hand_assignment"]).lower(),
            swap_hands=bool(m["swap_hands"]),
            always_on_top=bool(m["always_on_top"]),
            calibrate_countdown=float(m["calibrate_countdown"]),
            prep_countdown=float(m["prep_countdown"]),
            move=Move(
                directions=int(mv["directions"]),
                deadzone=float(mv["deadzone"]),
                deadzone_out=float(mv["deadzone_out"]),
                origin=tuple(mv["origin"]),
                keys=mv["keys"],
            ),
            gesture=Gesture(**m["gesture"]),
            output=Output(**m["output"]),
            zones=[Zone(**z) for z in m["zones"]],
        )
        cfg._path = path
        return cfg

    def reload(self) -> "Config":
        return Config.load(self._path or "config.json")

    def as_dict(self) -> dict:
        d = asdict(self)
        d.pop("_path", None)
        return d
