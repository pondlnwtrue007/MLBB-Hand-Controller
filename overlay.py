"""
วาดหน้าต่าง preview + overlay ให้ดู debug ง่ายและตัดคลิปสวย

โชว์:
  - โครงมือทั้งสองข้าง (21 จุด/ข้าง)
  - มือซ้าย: วง joystick (จุดกลาง + deadzone) + เส้นชี้ทิศ + ทิศที่ active
  - มือขวา: วงปุ่มทุกวง (ไฮไลต์เมื่อ cursor เข้า / แฟลชเมื่อยิง) + cursor + meter กำหมัด
  - HUD ปุ่ม W/A/S/D ที่ไฟติดตามทิศเดิน + ปุ่มสกิลล่าสุดที่ยิง
  - FPS / focus / test-mode / gesture + เลขนับถอยหลังตอน calibrate

ทุกองค์ประกอบ scale ตามความกว้างจอ (s = width/640). cv2.putText รองรับแค่ ASCII จึงใช้อังกฤษ
"""
from __future__ import annotations

import math

import cv2

# สี (BGR)
GREEN = (80, 220, 80)
RED = (60, 60, 235)
YELLOW = (40, 210, 240)
WHITE = (245, 245, 245)
BLACK = (20, 20, 20)
CYAN = (230, 210, 60)
ORANGE = (40, 150, 250)
LIT = (60, 200, 255)      # สีตอน active
DIM = (70, 70, 70)
GRAY = (140, 140, 140)

FONT = cv2.FONT_HERSHEY_SIMPLEX

# เส้นเชื่อม landmark มือ (MediaPipe Hands)
HAND_CONNECTIONS = [
    (0, 1), (1, 2), (2, 3), (3, 4),            # นิ้วโป้ง
    (0, 5), (5, 6), (6, 7), (7, 8),            # นิ้วชี้
    (9, 10), (10, 11), (11, 12),               # นิ้วกลาง
    (13, 14), (14, 15), (15, 16),              # นิ้วนาง
    (0, 17), (17, 18), (18, 19), (19, 20),     # นิ้วก้อย
    (5, 9), (9, 13), (13, 17),                 # ฝ่ามือ
]


def _text(img, s, org, scale, color, thick=2):
    off = max(1, int(round(scale * 2)))
    cv2.putText(img, s, (org[0] + off, org[1] + off), FONT, scale, BLACK, thick + 2, cv2.LINE_AA)
    cv2.putText(img, s, org, FONT, scale, color, thick, cv2.LINE_AA)


def _text_w(s, scale, thick):
    (w, _), _ = cv2.getTextSize(s, FONT, scale, thick)
    return w


class OverlayRenderer:
    def __init__(self, flash_seconds: float = 0.25):
        self.flash_seconds = flash_seconds
        self.flash_until = {}   # key(ปุ่ม) -> เวลาที่เลิกแฟลช

    def note_taps(self, taps, now):
        for t in taps:
            self.flash_until[t] = now + self.flash_seconds

    # -- โครงมือ ------------------------------------------------------------
    def _draw_hand(self, frame, hand, s, color):
        if hand is None:
            return
        h, w = frame.shape[:2]
        lm = hand.landmarks
        lw = max(2, int(round(2 * s)))
        r = max(2, int(round(3 * s)))

        def px(i):
            return int(lm[i].x * w), int(lm[i].y * h)

        for a, b in HAND_CONNECTIONS:
            cv2.line(frame, px(a), px(b), color, lw, cv2.LINE_AA)
        for i in range(len(lm)):
            cv2.circle(frame, px(i), r, WHITE, -1, cv2.LINE_AA)

    # -- มือซ้าย: joystick --------------------------------------------------
    def _draw_joystick(self, frame, state, s):
        h, w = frame.shape[:2]
        ox, oy = int(state.origin[0] * w), int(state.origin[1] * h)
        dz = int(state.deadzone * w)
        lw = max(2, int(round(2 * s)))

        active = bool(state.held_keys)
        ring_col = LIT if active else GRAY
        # วง deadzone + จุดกลาง
        cv2.circle(frame, (ox, oy), dz, ring_col, lw, cv2.LINE_AA)
        cv2.circle(frame, (ox, oy), max(3, int(4 * s)), ring_col, -1, cv2.LINE_AA)

        # เส้นชี้จากจุดกลางไปตำแหน่งมือ + หัวมือ
        if state.move_palm is not None:
            hx, hy = int(state.move_palm[0] * w), int(state.move_palm[1] * h)
            col = GREEN if active else GRAY
            cv2.line(frame, (ox, oy), (hx, hy), col, lw, cv2.LINE_AA)
            cv2.circle(frame, (hx, hy), max(5, int(8 * s)), col, -1, cv2.LINE_AA)

        # ป้ายทิศ
        label = "+".join(d.upper()[0] for d in state.move_dirs) if state.move_dirs else "IDLE"
        _text(frame, f"MOVE: {label}", (ox - int(40 * s), oy - dz - int(10 * s)),
              0.6 * s, ring_col, max(1, int(1.6 * s)))

    # -- มือขวา: วงปุ่ม + cursor -------------------------------------------
    def _draw_zones(self, frame, state, now, s):
        h, w = frame.shape[:2]
        lw = max(2, int(round(2 * s)))
        for z in state.zones:
            cx, cy = int(z.cx * w), int(z.cy * h)
            r = int(z.r * w)
            flash = now < self.flash_until.get(z.key, 0.0)
            if flash:
                col, fill = GREEN, True
            elif z.hovered:
                col, fill = LIT, False
            else:
                col, fill = DIM, False
            if fill:
                overlay = frame.copy()
                cv2.circle(overlay, (cx, cy), r, col, -1, cv2.LINE_AA)
                cv2.addWeighted(overlay, 0.45, frame, 0.55, 0, frame)
            thick = lw + 1 if z.hovered else lw
            cv2.circle(frame, (cx, cy), r, col, thick, cv2.LINE_AA)
            lbl = z.key.upper()
            (tw, tht), _ = cv2.getTextSize(lbl, FONT, 0.8 * s, thick)
            _text(frame, lbl, (cx - tw // 2, cy + tht // 2), 0.8 * s, WHITE, max(1, int(1.6 * s)))
            _text(frame, z.name, (cx - int(r * 0.9), cy + r + int(14 * s)),
                  0.42 * s, col, max(1, int(s)))

        # cursor มือขวา
        if state.skill_palm is not None:
            hx, hy = int(state.skill_palm[0] * w), int(state.skill_palm[1] * h)
            col = RED if state.is_fist else CYAN
            cv2.circle(frame, (hx, hy), max(6, int(9 * s)), col, -1, cv2.LINE_AA)
            cv2.circle(frame, (hx, hy), max(6, int(9 * s)), WHITE, max(1, int(1.5 * s)), cv2.LINE_AA)

    # -- meter กำหมัด (โชว์ค่า curl เทียบ threshold) -----------------------
    def _draw_curl_meter(self, frame, state, s):
        if not state.skill_present:
            return
        h, w = frame.shape[:2]
        bw, bh = int(180 * s), int(16 * s)
        x = w - bw - int(14 * s)
        y = h - int(60 * s)
        cv2.rectangle(frame, (x, y), (x + bw, y + bh), (55, 55, 55), -1)
        fill = int(_clamp(state.curl_score, 0, 1) * bw)
        col = RED if state.is_fist else CYAN
        cv2.rectangle(frame, (x, y), (x + fill, y + bh), col, -1)
        _text(frame, f"{state.fire_gesture.upper()}: {state.gesture_label}", (x, y - int(6 * s)),
              0.5 * s, col, max(1, int(s)))

    # -- HUD ปุ่ม W/A/S/D + ปุ่มสกิลล่าสุด ---------------------------------
    def _key_box(self, img, x, y, b, label, active, s):
        color = LIT if active else DIM
        cv2.rectangle(img, (x, y), (x + b, y + b), color, -1, cv2.LINE_AA)
        cv2.rectangle(img, (x, y), (x + b, y + b), WHITE, max(2, int(2 * s)), cv2.LINE_AA)
        fs = 0.7 * s
        th = max(2, int(round(2 * s)))
        (tw, tht), _ = cv2.getTextSize(label, FONT, fs, th)
        cv2.putText(img, label, (x + (b - tw) // 2, y + (b + tht) // 2), FONT, fs,
                    BLACK if active else WHITE, th, cv2.LINE_AA)

    def _draw_key_hud(self, frame, state, s):
        h, w = frame.shape[:2]
        b = int(40 * s)
        gap = int(6 * s)
        cx = int(70 * s)
        bottom = h - int(70 * s)
        held = {k.lower() for k in state.held_keys}
        # กากบาท WASD
        top = bottom - (b * 2 + gap)
        self._key_box(frame, cx - b // 2, top, b, "W", "w" in held, s)
        row2 = top + b + gap
        self._key_box(frame, cx - b - gap - b // 2, row2, b, "A", "a" in held, s)
        self._key_box(frame, cx - b // 2, row2, b, "S", "s" in held, s)
        self._key_box(frame, cx + gap + b // 2, row2, b, "D", "d" in held, s)

    # -- แถบสถานะ -----------------------------------------------------------
    def _draw_status(self, frame, state, fps, test_mode, focused, s):
        h, w = frame.shape[:2]
        m = int(14 * s)
        fs = 0.6 * s
        th = max(1, int(round(1.6 * s)))
        line_h = int(28 * s)

        y1 = int(28 * s)
        _text(frame, f"FPS {fps:4.1f}", (m, y1), fs, WHITE, th)
        if test_mode:
            tag, col = "TEST MODE (not sending)", YELLOW
        elif focused:
            tag, col = "MuMu FOCUSED", GREEN
        else:
            tag, col = "NOT FOCUSED", RED
        _text(frame, tag, (w - _text_w(tag, fs, th) - m, y1), fs, col, th)

        y2 = y1 + line_h
        hands_tag = []
        hands_tag.append("L:move" if state.move_present else "L:-")
        hands_tag.append("R:skill" if state.skill_present else "R:-")
        _text(frame, "  ".join(hands_tag), (m, y2), 0.5 * s, WHITE, max(1, int(s)))

        _text(frame, "C set-center  E edit-buttons  P on-top  T test  R reload  Q quit",
              (m, h - int(12 * s)), 0.5 * s, WHITE, max(1, int(s)))

    # -- นับถอยหลังกลางจอ ---------------------------------------------------
    def _draw_countdown(self, frame, remaining, title, sub, s):
        h, w = frame.shape[:2]
        n = int(math.ceil(remaining))
        overlay = frame.copy()
        cv2.rectangle(overlay, (0, 0), (w, h), BLACK, -1)
        cv2.addWeighted(overlay, 0.35, frame, 0.65, 0, frame)

        fs_top = 0.9 * s
        th_top = max(2, int(round(2 * s)))
        _text(frame, title, ((w - _text_w(title, fs_top, th_top)) // 2, int(h * 0.30)),
              fs_top, YELLOW, th_top)
        num = str(n)
        fs_num = 7.0 * s
        th_num = max(6, int(round(8 * s)))
        (nw, nh), _ = cv2.getTextSize(num, FONT, fs_num, th_num)
        _text(frame, num, ((w - nw) // 2, (h + nh) // 2), fs_num, CYAN, th_num)
        fs_sub = 0.8 * s
        th_sub = max(2, int(round(2 * s)))
        _text(frame, sub, ((w - _text_w(sub, fs_sub, th_sub)) // 2, int(h * 0.72)),
              fs_sub, WHITE, th_sub)

    # -- โหมดแก้ไข: ไฮไลต์วงที่เลือก + คำแนะนำ ------------------------------
    def _draw_editor(self, frame, editor, s):
        h, w = frame.shape[:2]
        # แถบบนสุดบอกว่าอยู่ในโหมดแก้ไข
        cv2.rectangle(frame, (0, 0), (w, int(34 * s)), (30, 30, 30), -1)
        _text(frame, "EDIT MODE  |  drag = move   wheel or [ ] = resize   S = save   E = exit",
              (int(10 * s), int(24 * s)), 0.55 * s, YELLOW, max(1, int(1.6 * s)))
        # ไฮไลต์วงที่เลือก
        if 0 <= editor.sel < len(editor.cfg.zones):
            z = editor.cfg.zones[editor.sel]
            cx, cy, r = int(z.cx * w), int(z.cy * h), int(z.r * w)
            cv2.circle(frame, (cx, cy), r, YELLOW, max(2, int(3 * s)), cv2.LINE_AA)
            cv2.line(frame, (cx - r, cy), (cx + r, cy), YELLOW, 1, cv2.LINE_AA)
            cv2.line(frame, (cx, cy - r), (cx, cy + r), YELLOW, 1, cv2.LINE_AA)
            _text(frame, f"{z.name} [{z.key.upper()}]  r={z.r:.3f}",
                  (cx - r, cy - r - int(8 * s)), 0.5 * s, YELLOW, max(1, int(s)))
        if editor.last_saved:
            _text(frame, "SAVED", (w - int(90 * s), int(24 * s)), 0.6 * s, GREEN, max(1, int(2 * s)))

    # -- render หลัก --------------------------------------------------------
    def render(self, frame, state, taps, now, fps,
               test_mode, focused, countdown=None, editor=None):
        s = frame.shape[1] / 640.0
        self.note_taps(taps, now)

        self._draw_zones(frame, state, now, s)          # วงก่อน (เป็นพื้นหลัง)
        self._draw_joystick(frame, state, s)
        # โครงมือ: มือเดิน=เขียว, มือสกิล=ส้ม
        self._draw_hand(frame, state.mover_hand, s, GREEN)
        self._draw_hand(frame, state.skiller_hand, s, ORANGE)
        self._draw_curl_meter(frame, state, s)
        self._draw_key_hud(frame, state, s)
        self._draw_status(frame, state, fps, test_mode, focused, s)
        if editor is not None and editor.active:
            self._draw_editor(frame, editor, s)
        if countdown is not None:
            self._draw_countdown(frame, countdown[0], countdown[1], countdown[2], s)
        return frame


def _clamp(v, lo, hi):
    return max(lo, min(hi, v))
