"""
กล้องแบบแยก thread อ่านภาพ (ลด latency + เพิ่ม FPS)

thread หนึ่งวิ่งอ่านเฟรมล่าสุดตลอด, main loop หยิบเฟรมล่าสุดไปใช้ทันที
ไม่ต้องรอกล้อง -> ลื่นขึ้นมากและ latency ต่ำ (สำคัญมากกับ MOBA ที่ต้องเดิน+กดสกิลพร้อมกัน)

กล้อง Logitech C922 ทำ 30fps ได้ดีที่ DSHOW+MJPG (ค่า default DSHOW+YUY2 จะได้แค่ ~10-15 fps)
เลี่ยงคู่ MSMF+MJPG เพราะบางเครื่องอาจค้าง
"""
from __future__ import annotations

import threading

import cv2


def list_cameras(max_probe: int = 6):
    """คืนรายชื่อกล้องที่ต่ออยู่ [(index, ชื่อ)] — ใช้ pygrabber ก่อน ถ้าไม่มีค่อย probe"""
    try:
        from pygrabber.dshow_graph import FilterGraph
        names = FilterGraph().get_input_devices()
        if names:
            return [(i, name) for i, name in enumerate(names)]
    except Exception:
        pass

    found = []
    for i in range(max_probe):
        cap = cv2.VideoCapture(i, cv2.CAP_DSHOW)
        if cap.isOpened():
            ok, _ = cap.read()
            if ok:
                found.append((i, f"กล้อง {i}"))
        cap.release()
    return found


def _make_capture(index, width, height, backend, use_mjpg, fps):
    cap = cv2.VideoCapture(index, backend)
    if not cap.isOpened():
        return None
    if use_mjpg:
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    cap.set(cv2.CAP_PROP_FPS, fps)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)   # buffer น้อยสุด = เฟรมสดใหม่เสมอ (latency ต่ำ)
    return cap


def open_capture(index, width, height, prefer_backend, use_mjpg=True, fps=30):
    """
    ลองเปิดกล้องตามลำดับ (backend, mjpg) ที่ปลอดภัย ถ้าไม่ได้ค่อยลองตัวถัดไป
    คืน (cap, ชื่อ backend) หรือ (None, None) ถ้าเปิดไม่ได้เลย

    เลี่ยงคู่ MSMF + MJPG เพราะบางเครื่อง cap.set()/read() ค้างถาวร (หน้าต่างไม่ขึ้น)
    """
    D, M = cv2.CAP_DSHOW, cv2.CAP_MSMF
    if str(prefer_backend).upper() == "MSMF":
        attempts = [(M, "MSMF", False), (D, "DSHOW", use_mjpg), (D, "DSHOW", False)]
    else:
        attempts = [(D, "DSHOW", use_mjpg), (D, "DSHOW", False), (M, "MSMF", False)]

    for backend, name, mjpg in attempts:
        cap = _make_capture(index, width, height, backend, mjpg, fps)
        if cap is None:
            continue
        ok, _ = cap.read()   # ยืนยันว่าอ่านได้จริง 1 เฟรม
        if ok:
            return cap, name + ("+MJPG" if mjpg else "")
        cap.release()
    return None, None


class CameraStream:
    """กล้อง threaded: thread เบื้องหลังอ่านเฟรมล่าสุดตลอด, read() คืนเฟรมล่าสุดทันที"""

    def __init__(self, index, width, height, prefer_backend="DSHOW", use_mjpg=True, fps=30):
        self.cap, self.backend_name = open_capture(
            index, width, height, prefer_backend, use_mjpg, fps
        )
        self._frame = None
        self._lock = threading.Lock()
        self._running = False
        self._thread = None

    def is_opened(self):
        return self.cap is not None

    @property
    def size(self):
        if self.cap is None:
            return (0, 0)
        return (int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
                int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT)))

    @property
    def actual_fps(self):
        return 0.0 if self.cap is None else float(self.cap.get(cv2.CAP_PROP_FPS))

    def start(self):
        if self.cap is None:
            return self
        self._running = True
        self._thread = threading.Thread(target=self._update, daemon=True)
        self._thread.start()
        return self

    def _update(self):
        while self._running:
            ok, frame = self.cap.read()
            if ok:
                with self._lock:
                    self._frame = frame

    def read(self):
        """คืน (ok, frame) — เฟรมล่าสุดที่ thread อ่านมา (copy กันโดนเขียนทับระหว่างใช้)"""
        with self._lock:
            if self._frame is None:
                return False, None
            return True, self._frame.copy()

    def release(self):
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=1.0)
        if self.cap is not None:
            self.cap.release()
