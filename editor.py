"""
โหมดจัดวาง "วงปุ่ม" ด้วยเมาส์ในหน้าต่าง preview

เข้าโหมดด้วยปุ่ม E แล้ว:
  - ลากวง (คลิกซ้ายค้าง) = ย้ายตำแหน่ง
  - ล้อเมาส์ หรือปุ่ม [ ] = ย่อ/ขยายวงที่เลือก
  - S = เซฟลง config.json,  E = ออกจากโหมดแก้ไข

แก้ค่า cfg.zones ตรง ๆ (in place) ระหว่างเล่นได้เลย overlay จะอัปเดตตำแหน่งสด
"""
from __future__ import annotations

import json
import math

import cv2


class ZoneEditor:
    def __init__(self, cfg):
        self.cfg = cfg
        self.active = False
        self.sel = -1           # index วงที่เลือกอยู่
        self.dragging = False
        self._off = (0.0, 0.0)  # ระยะจากจุดคลิกถึงจุดกลางวง (พิกเซล)
        self.wh = (1, 1)        # ขนาดเฟรมล่าสุด (w, h)
        self.last_saved = ""    # path ที่เพิ่งเซฟ (ไว้โชว์)

    def set_frame_size(self, w, h):
        self.wh = (max(1, w), max(1, h))

    def _zone_at(self, x, y):
        w, h = self.wh
        best, bd = -1, 1e9
        for i, z in enumerate(self.cfg.zones):
            zx, zy, r = z.cx * w, z.cy * h, z.r * w
            d = math.hypot(x - zx, y - zy)
            if d <= max(r, 12) and d < bd:
                best, bd = i, d
        return best

    def _resize_sel(self, step):
        if 0 <= self.sel < len(self.cfg.zones):
            z = self.cfg.zones[self.sel]
            z.r = min(0.30, max(0.02, z.r + step))

    # -- callback เมาส์ (ผูกกับหน้าต่าง cv2) -------------------------------
    def on_mouse(self, event, x, y, flags, param):
        if not self.active:
            return
        w, h = self.wh
        if event == cv2.EVENT_LBUTTONDOWN:
            i = self._zone_at(x, y)
            if i >= 0:
                self.sel = i
                self.dragging = True
                z = self.cfg.zones[i]
                self._off = (x - z.cx * w, y - z.cy * h)
        elif event == cv2.EVENT_MOUSEMOVE and self.dragging and self.sel >= 0:
            z = self.cfg.zones[self.sel]
            z.cx = min(1.0, max(0.0, (x - self._off[0]) / w))
            z.cy = min(1.0, max(0.0, (y - self._off[1]) / h))
        elif event == cv2.EVENT_LBUTTONUP:
            self.dragging = False
        elif event == cv2.EVENT_MOUSEWHEEL:
            i = self.sel if self.sel >= 0 else self._zone_at(x, y)
            if i >= 0:
                self.sel = i
                try:
                    delta = cv2.getMouseWheelDelta(flags)
                except Exception:
                    delta = flags   # fallback: flags บวก=หมุนขึ้น
                self._resize_sel(0.005 if delta > 0 else -0.005)

    # -- ปุ่มลัดในโหมดแก้ไข -------------------------------------------------
    def handle_key(self, key) -> bool:
        """คืน True ถ้าจัดการปุ่มนี้แล้ว (main จะได้ไม่เอาไปทำอย่างอื่น)"""
        if not self.active:
            return False
        if key == ord("["):
            self._resize_sel(-0.005)
            return True
        if key == ord("]"):
            self._resize_sel(0.005)
            return True
        if key == ord("s"):
            self.last_saved = self.save()
            print(f"[editor] เซฟตำแหน่งวงลง {self.last_saved} แล้ว")
            return True
        return False

    def save(self) -> str:
        path = self.cfg._path or "config.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.cfg.as_dict(), f, ensure_ascii=False, indent=2)
        return path
