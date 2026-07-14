"""
แปลงฟีเจอร์ 2 มือ -> ปุ่มที่ต้อง "กดค้าง" (เดิน W/A/S/D) + ปุ่มที่ "แตะ" (สกิล)

มือซ้าย = LeftJoystick : ตำแหน่งฝ่ามือเทียบจุดกลาง (origin) -> ทิศ -> ปุ่ม WASD กดค้าง
  - ระยะจากจุดกลาง < deadzone_out -> หยุด ; เกิน deadzone -> เดิน (hysteresis กันกระพริบ)
  - snap เป็น 4 ทิศ (หรือ 8 ทิศตาม config.move.directions)

มือขวา = RightZones : จุดกลางฝ่ามือเป็น cursor เลือก "วง", กำหมัดยืนยัน -> แตะปุ่มวงนั้น
  - แยก "เลือกปุ่ม (ตำแหน่ง)" ออกจาก "ยิง (กำหมัด)" -> ใส่กี่วงก็ได้ ใช้ท่าเดียว
  - ยิงที่ขอบเปลี่ยน แบ->กำหมัด (1 กำหมัด = 1 ยิง). วง repeat=true (เช่นโจมตี) รัวขณะกำหมัดค้าง

การ assign มือ->บทบาท: default ใช้ "ตำแหน่งในเฟรม" (ฝั่งซ้าย=เดิน, ฝั่งขวา=สกิล) เพราะทนกว่า
handedness ที่ label อาจสลับเมื่อ mirror ; มี swap_hands ไว้กลับข้างถ้าจับผิด
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field


# แม็ปทิศ -> คีย์ย่อ (สร้างจาก config.move.keys ตอนใช้งาน)
# 8 ทิศ index 0..7 เริ่มที่ขวา ทวนเข็ม (คณิตศาสตร์มาตรฐาน): R, UR, U, UL, L, DL, D, DR
_DIR8 = [("right",), ("up", "right"), ("up",), ("up", "left"),
         ("left",), ("down", "left"), ("down",), ("down", "right")]
_DIR4 = [("right",), ("up",), ("left",), ("down",)]


@dataclass
class ZoneState:
    name: str
    key: str
    cx: float
    cy: float
    r: float
    repeat: bool = False
    hovered: bool = False
    fired: bool = False       # เพิ่งยิงเฟรมนี้ (ไว้ flash overlay)


@dataclass
class ControllerState:
    # มือซ้าย (joystick)
    move_present: bool = False
    origin: tuple = (0.25, 0.55)
    deadzone: float = 0.10
    move_palm: tuple | None = None      # ตำแหน่ง cursor มือซ้าย
    move_mag: float = 0.0               # ระยะจากจุดกลาง (สัดส่วนความกว้างจอ)
    move_dirs: tuple = ()               # ทิศที่ active ("up","left",...)
    held_keys: set = field(default_factory=set)

    # มือขวา (zones)
    skill_present: bool = False
    skill_palm: tuple | None = None     # ตำแหน่ง cursor มือขวา
    is_fist: bool = False
    curl_score: float = 0.0
    gesture_label: str = "-"            # READY / FIRE / OPEN
    fire_gesture: str = "pinch"         # ท่ายิงที่ใช้อยู่ (pinch/fist/trigger)
    hovered_zone: str | None = None
    zones: list = field(default_factory=list)  # list[ZoneState]

    # อ้างอิง HandFeatures ดิบ (ไว้ให้ overlay วาดโครงมือ)
    mover_hand: object = None
    skiller_hand: object = None


class Controller:
    def __init__(self, cfg):
        self.cfg = cfg
        self.origin = tuple(cfg.move.origin)   # override ได้ด้วยการ calibrate (กด C)

        # EMA ตำแหน่งฝ่ามือแต่ละมือ (ลด jitter)
        self._move_ema = None
        self._skill_ema = None

        # state machine มือขวา
        self._fisted = False        # ตอนนี้ถือว่ากำหมัดอยู่ไหม (มี hysteresis)
        self._last_repeat = 0.0     # เวลายิงซ้ำล่าสุด (สำหรับวง repeat)
        self._moving = False        # ตอนนี้มือซ้ายพ้น deadzone แล้วไหม (hysteresis)

    # -- calibration --------------------------------------------------------
    def set_origin_from(self, hands) -> bool:
        """ตั้งจุดกลาง joystick = ตำแหน่งมือซ้ายปัจจุบัน. คืน True ถ้าเจอมือซ้าย"""
        mover, _ = self._assign(hands)
        if mover is None:
            return False
        self.origin = mover.palm
        self._move_ema = None
        return True

    # -- helpers ------------------------------------------------------------
    def _ema(self, prev, raw):
        if prev is None:
            return raw
        a = self.cfg.smoothing
        return (a * raw[0] + (1 - a) * prev[0], a * raw[1] + (1 - a) * prev[1])

    def _assign(self, hands):
        """คืน (mover_hand, skiller_hand) — อาจเป็น None ถ้าไม่มี"""
        present = [h for h in hands if h is not None]
        if not present:
            return None, None

        if self.cfg.hand_assignment == "handedness":
            # มือซ้ายของคนเล่น (เดิน) = label "Left", มือขวา (สกิล) = "Right"
            move_label = "Right" if self.cfg.swap_hands else "Left"
            mover = next((h for h in present if h.handedness == move_label), None)
            skiller = next((h for h in present if h.handedness != move_label), None)
            # ถ้า label ซ้ำ/หาไม่เจอ fallback ใช้ตำแหน่ง
            if mover is None and skiller is None:
                pass
            elif mover is skiller:
                skiller = None
            if mover is not None or skiller is not None:
                return mover, skiller

        # ---- position mode (default) : ฝั่งซ้ายของเฟรม = เดิน, ฝั่งขวา = สกิล ----
        s = sorted(present, key=lambda h: h.palm[0])
        if len(s) == 1:
            # มือเดียว: อยู่ฝั่งซ้ายจอ = เดิน, ฝั่งขวา = สกิล
            one = s[0]
            if one.palm[0] < 0.5:
                mover, skiller = one, None
            else:
                mover, skiller = None, one
        else:
            mover, skiller = s[0], s[-1]

        if self.cfg.swap_hands:
            mover, skiller = skiller, mover
        return mover, skiller

    # -- มือซ้าย: ตำแหน่ง -> ทิศ -> ปุ่มกดค้าง ------------------------------
    def _update_move(self, mover, aspect, st: ControllerState) -> set:
        st.origin = self.origin
        st.deadzone = self.cfg.move.deadzone
        if mover is None:
            self._move_ema = None
            self._moving = False
            return set()

        st.move_present = True
        self._move_ema = self._ema(self._move_ema, mover.palm)
        px, py = self._move_ema
        st.move_palm = (px, py)

        # offset เทียบจุดกลาง — คูณ y ด้วย aspect (H/W) ให้ทิศถูกเชิงเรขาคณิต
        dx = px - self.origin[0]
        dy = (py - self.origin[1]) * aspect
        mag = math.hypot(dx, dy)
        st.move_mag = mag

        # hysteresis: เริ่มเดินเมื่อเกิน deadzone, หยุดเมื่อต่ำกว่า deadzone_out
        if self._moving:
            if mag < self.cfg.move.deadzone_out:
                self._moving = False
        else:
            if mag > self.cfg.move.deadzone:
                self._moving = True
        if not self._moving:
            return set()

        # snap ทิศ: มุม 0 = ขวา, ทวนเข็มขึ้นบน (จอ y ชี้ลง จึงกลับเครื่องหมาย dy)
        ang = math.atan2(-dy, dx)
        if self.cfg.move.directions >= 8:
            table = _DIR8
            step = 2 * math.pi / 8
        else:
            table = _DIR4
            step = 2 * math.pi / 4
        sector = int(round(ang / step)) % len(table)
        dirs = table[sector]
        st.move_dirs = dirs

        km = self.cfg.move.keys
        return {km[d] for d in dirs if km.get(d)}

    # -- มือขวา: cursor เลือกวง + กำหมัดยิง --------------------------------
    def _update_skill(self, skiller, aspect, now, st: ControllerState) -> list:
        # เตรียม ZoneState ทุกวงไว้ก่อน (overlay ใช้เสมอ)
        st.zones = [ZoneState(z.name, z.key, z.cx, z.cy, z.r, z.repeat) for z in self.cfg.zones]
        taps: list[str] = []

        if skiller is None:
            self._skill_ema = None
            self._fisted = False
            return taps

        st.skill_present = True
        self._skill_ema = self._ema(self._skill_ema, skiller.palm)
        cx, cy = self._skill_ema
        st.skill_palm = (cx, cy)

        # ---- ตรวจ "ท่ายิง" ตามที่เลือกใน config (มี hysteresis กันสั่น) ----
        # closed_now = ทำท่าอยู่, open_now = คลายท่าแล้ว (ต้องคลายก่อนถึงยิงใหม่ได้)
        g = self.cfg.gesture
        gt = str(getattr(g, "fire_gesture", "fist")).lower()
        st.fire_gesture = gt
        if gt == "pinch":
            closed_now = skiller.pinch_dist < g.pinch_on
            open_now = skiller.pinch_dist > g.pinch_off
            span = max(1e-4, g.pinch_off - g.pinch_on)
            st.curl_score = max(0.0, min(1.0, (g.pinch_off - skiller.pinch_dist) / span))
            idle_label = "READY"
        elif gt == "trigger":
            idx_ext, mid_ext = skiller.extended[0], skiller.extended[1]
            closed_now = (not idx_ext) and mid_ext   # งอเฉพาะนิ้วชี้ (นิ้วกลางยังเหยียด)
            open_now = idx_ext
            st.curl_score = 1.0 if closed_now else 0.0
            idle_label = "READY"
        else:  # fist
            closed_now = skiller.n_ext <= g.fist_max_open
            open_now = skiller.n_ext >= g.open_min
            st.curl_score = skiller.curl_score
            idle_label = "OPEN"

        if self._fisted:
            if open_now:
                self._fisted = False
            fire_edge = False
        else:
            if closed_now:
                self._fisted = True
                fire_edge = True   # ขอบเปลี่ยน คลาย->ทำท่า = ยิง 1 ที
            else:
                fire_edge = False
        st.is_fist = self._fisted
        st.gesture_label = "FIRE" if self._fisted else idle_label

        # หา "วงที่ cursor อยู่ใน" ที่ใกล้ที่สุด (เผื่อวงซ้อน)
        best = None
        best_d = 1e9
        for zs in st.zones:
            ddx = cx - zs.cx
            ddy = (cy - zs.cy) * aspect
            d = math.hypot(ddx, ddy)
            if d < zs.r and d < best_d:
                best, best_d = zs, d
        if best is not None:
            best.hovered = True
            st.hovered_zone = best.name

            if fire_edge:
                taps.append(best.key)
                best.fired = True
                self._last_repeat = now
            elif best.repeat and self._fisted and \
                    (now - self._last_repeat) >= self.cfg.output.repeat_interval:
                taps.append(best.key)
                best.fired = True
                self._last_repeat = now
        return taps

    # -- main update --------------------------------------------------------
    def update(self, hands, now: float, aspect: float):
        """
        hands  : list[HandFeatures] จาก HandDetector
        aspect : frame_height / frame_width (ให้ทิศ/วงถูกเชิงเรขาคณิต)
        คืน (held_keys:set, taps:list, state:ControllerState)
        """
        st = ControllerState()
        mover, skiller = self._assign(hands)
        st.mover_hand = mover
        st.skiller_hand = skiller

        held = self._update_move(mover, aspect, st)
        taps = self._update_skill(skiller, aspect, now, st)
        st.held_keys = set(held)
        return held, taps, st
