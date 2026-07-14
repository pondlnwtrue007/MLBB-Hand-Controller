"""
ตรวจจับ 2 มือพร้อมกันด้วย MediaPipe HandLandmarker (Tasks API, โหมด VIDEO)
แล้วสกัดฟีเจอร์ต่อมือที่ controller เอาไปใช้:
  - palm : จุดกลางฝ่ามือ (centroid ของ wrist + โคนนิ้ว 4 นิ้ว) — เสถียรกว่าปลายนิ้ว
           ใช้ทั้งเป็น "หัว joystick" (มือซ้าย) และ "cursor เลือกวง" (มือขวา)
  - size : ขนาดมือ (wrist -> โคนนิ้วกลาง) ใช้ normalize ให้ไม่ขึ้นกับระยะห่างกล้อง
  - n_ext / extended : จำนวนนิ้ว(จาก 4: ชี้/กลาง/นาง/ก้อย)ที่ "เหยียด" — ใช้แยกกำหมัด vs แบ/ชี้
  - handedness : "Left"/"Right" จาก MediaPipe (อาจสลับเมื่อ mirror — controller มี option เลือก)

หมายเหตุประสิทธิภาพ: โหมด VIDEO มี inter-frame tracking เร็วกว่า IMAGE, ย่อภาพก่อน detect
(ทำใน main.py) และ num_hands=2 จับสองมือในโมเดลเดียว
"""
from __future__ import annotations

import math
import os
import urllib.request
from dataclasses import dataclass, field

import mediapipe as mp
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision as mp_vision

from paths import resource_path, appdata_dir

MODEL_FILENAME = "hand_landmarker.task"
MODEL_URL = ("https://storage.googleapis.com/mediapipe-models/hand_landmarker/"
             "hand_landmarker/float16/latest/hand_landmarker.task")

# ดัชนี landmark ของ MediaPipe Hands (21 จุด)
WRIST = 0
THUMB_CMC, THUMB_MCP, THUMB_IP, THUMB_TIP = 1, 2, 3, 4
INDEX_MCP, INDEX_PIP, INDEX_DIP, INDEX_TIP = 5, 6, 7, 8
MIDDLE_MCP, MIDDLE_PIP, MIDDLE_DIP, MIDDLE_TIP = 9, 10, 11, 12
RING_MCP, RING_PIP, RING_DIP, RING_TIP = 13, 14, 15, 16
PINKY_MCP, PINKY_PIP, PINKY_DIP, PINKY_TIP = 17, 18, 19, 20

PALM_POINTS = (WRIST, INDEX_MCP, MIDDLE_MCP, RING_MCP, PINKY_MCP)
# 4 นิ้วที่ใช้ตัดสินกำหมัด (ไม่รวมนิ้วโป้งเพราะเหยียด/งอต่างระนาบ) : (tip, pip)
FINGERS_4 = (
    (INDEX_TIP, INDEX_PIP),
    (MIDDLE_TIP, MIDDLE_PIP),
    (RING_TIP, RING_PIP),
    (PINKY_TIP, PINKY_PIP),
)


def _ensure_model(path: str = MODEL_FILENAME) -> str:
    """คืน path โมเดล: ไฟล์ที่ส่งมา -> ที่แนบมากับโปรแกรม -> ใน appdata -> โหลดใหม่ลง appdata"""
    if path and os.path.exists(path):
        return path
    bundled = resource_path(MODEL_FILENAME)
    if os.path.exists(bundled):
        return bundled
    cached = os.path.join(appdata_dir(), MODEL_FILENAME)
    if os.path.exists(cached):
        return cached
    print("[hands] ไม่พบโมเดล — กำลังดาวน์โหลด (~7.5MB)...")
    try:
        urllib.request.urlretrieve(MODEL_URL, cached)
        print("[hands] ดาวน์โหลดโมเดลเสร็จ")
    except Exception as e:
        raise RuntimeError(
            f"ดาวน์โหลดโมเดลไม่ได้ ({e}). โหลดเองจาก\n  {MODEL_URL}\n"
            f"แล้ววางไว้ที่ {cached}"
        )
    return cached


def _dist(a, b) -> float:
    return math.hypot(a.x - b.x, a.y - b.y)


@dataclass
class HandFeatures:
    """ฟีเจอร์ของมือ 1 ข้าง (พิกัด normalized 0..1)"""
    landmarks: list                    # 21 จุด (มี .x .y .z) — overlay เอาไปวาด
    palm: tuple                        # (x, y) จุดกลางฝ่ามือ
    size: float                        # ระยะ wrist -> โคนนิ้วกลาง (สเกลอ้างอิง)
    extended: tuple                    # (index, middle, ring, pinky) เหยียดไหม (bool)
    n_ext: int                         # จำนวนนิ้วที่เหยียด (0..4)
    pinch_dist: float                  # ระยะปลายนิ้วโป้ง-ชี้ / ขนาดมือ (จีบ = ค่าน้อย)
    handedness: str                    # "Left" / "Right"
    handedness_score: float = 0.0

    @property
    def curl_score(self) -> float:
        """0 = แบมือสุด, 1 = กำหมัดสุด (ไว้โชว์เป็น meter)"""
        return 1.0 - self.n_ext / 4.0

    @property
    def is_point(self) -> bool:
        """ชี้นิ้ว = นิ้วชี้เหยียด นิ้วที่เหลืองอ"""
        idx, mid, ring, pky = self.extended
        return idx and not mid and not ring and not pky


def _extract(landmarks, handedness_name, handedness_score) -> HandFeatures:
    lm = landmarks
    # จุดกลางฝ่ามือ = เฉลี่ยตำแหน่ง wrist + โคนนิ้ว
    px = sum(lm[i].x for i in PALM_POINTS) / len(PALM_POINTS)
    py = sum(lm[i].y for i in PALM_POINTS) / len(PALM_POINTS)
    size = max(_dist(lm[WRIST], lm[MIDDLE_MCP]), 1e-4)

    # นิ้วเหยียด: ปลายนิ้วไกลจากข้อมือมากกว่าข้อ PIP (ทำงานทุกมุมมือ ไม่ต้องอิงแกน y)
    ext = []
    for tip, pip in FINGERS_4:
        ext.append(_dist(lm[tip], lm[WRIST]) > _dist(lm[pip], lm[WRIST]))
    ext = tuple(ext)

    # จีบนิ้ว: ระยะปลายนิ้วโป้ง-ปลายนิ้วชี้ หารด้วยขนาดมือ (จีบ -> ค่าน้อย)
    pinch_dist = _dist(lm[THUMB_TIP], lm[INDEX_TIP]) / size

    return HandFeatures(
        landmarks=lm,
        palm=(px, py),
        size=size,
        extended=ext,
        n_ext=sum(ext),
        pinch_dist=pinch_dist,
        handedness=handedness_name,
        handedness_score=handedness_score,
    )


class HandDetector:
    """ห่อ MediaPipe HandLandmarker (โหมด VIDEO, 2 มือ) — คืน list[HandFeatures] (0..2 ข้าง)"""

    def __init__(self, model_path: str = MODEL_FILENAME):
        model_path = _ensure_model(model_path)
        # อ่านโมเดลเป็น bytes ใน Python แล้วส่งเป็น buffer (ไม่ส่ง path)
        # เพราะ MediaPipe (C++) เปิดไฟล์ที่ path มีอักขระ Unicode ไม่ได้
        # (เช่นขีด — ในชื่อโฟลเดอร์) แต่ open() ของ Python เปิดได้ปกติ
        with open(model_path, "rb") as f:
            model_buffer = f.read()
        options = mp_vision.HandLandmarkerOptions(
            base_options=mp_python.BaseOptions(model_asset_buffer=model_buffer),
            running_mode=mp_vision.RunningMode.VIDEO,
            num_hands=2,
            min_hand_detection_confidence=0.5,
            min_hand_presence_confidence=0.5,
            min_tracking_confidence=0.5,
        )
        self.landmarker = mp_vision.HandLandmarker.create_from_options(options)
        self._last_ts_ms = 0

    def process(self, rgb_frame, now: float) -> list:
        ts_ms = int(now * 1000)
        if ts_ms <= self._last_ts_ms:
            ts_ms = self._last_ts_ms + 1
        self._last_ts_ms = ts_ms

        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)
        result = self.landmarker.detect_for_video(mp_image, ts_ms)

        hands = []
        if result.hand_landmarks:
            for i, lm in enumerate(result.hand_landmarks):
                name, score = "Unknown", 0.0
                if result.handedness and i < len(result.handedness) and result.handedness[i]:
                    cat = result.handedness[i][0]
                    name, score = cat.category_name, cat.score
                hands.append(_extract(lm, name, score))
        return hands

    def close(self):
        self.landmarker.close()
