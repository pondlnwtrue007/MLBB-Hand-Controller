"""
Mobile Legends — Hand Controller
คุม Mobile Legends (บน MuMu Player) ด้วย 2 มือผ่านเว็บแคม

รัน:
    python main.py            # โหมดเล่นจริง (ยิงปุ่มเข้า MuMu ตอนหน้าต่าง MuMu focus)
    python main.py --test     # โหมดซ้อม: โชว์ทิศ/ปุ่มที่จะกด แต่ไม่ยิงจริง

การคุม:
    มือซ้าย  = เลื่อนมือรอบ "วงกลาง" -> เดิน W/A/S/D (กดค้างตามทิศ)
    มือขวา   = เลื่อนฝ่ามือเข้า "วงปุ่ม" แล้ว "กำหมัด" = ยิงปุ่มนั้น

ปุ่มลัดในหน้าต่าง preview:
    C = ตั้งจุดกลาง joystick (วางมือซ้ายตรงกลางแล้วกด)   T = สลับ test mode
    R = reload config.json    Q / Esc = ออก
"""
from __future__ import annotations

import argparse
import os
import sys
import time

# บังคับ console เป็น UTF-8 กัน UnicodeEncodeError ตอน print ภาษาไทย
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import cv2

from config import Config
from camera import CameraStream
from hands import HandDetector
from controller import Controller
from input_sender import InputSender
from overlay import OverlayRenderer
from editor import ZoneEditor


from paths import resource_path, appdata_dir

ICON_PATH = resource_path("icon.ico")


def set_window_icon(title: str) -> bool:
    """ตั้งไอคอนหน้าต่าง preview (Windows) จาก icon.ico — ล้มเหลวก็ข้ามเงียบ ๆ"""
    try:
        import os
        import win32gui
        import win32con
        if not os.path.exists(ICON_PATH):
            return False
        hwnd = win32gui.FindWindow(None, title)
        if not hwnd:
            return False
        flags = win32con.LR_LOADFROMFILE | win32con.LR_DEFAULTSIZE
        hicon = win32gui.LoadImage(0, ICON_PATH, win32con.IMAGE_ICON, 0, 0, flags)
        win32gui.SendMessage(hwnd, win32con.WM_SETICON, win32con.ICON_SMALL, hicon)
        win32gui.SendMessage(hwnd, win32con.WM_SETICON, win32con.ICON_BIG, hicon)
        return True
    except Exception:
        return False


def set_topmost(title: str, on: bool = True) -> bool:
    """ทำให้หน้าต่าง preview ลอยหน้าสุด (ไม่แย่ง focus จาก MuMu — สำคัญ ไม่งั้นปุ่มไม่เข้าเกม)"""
    try:
        import win32gui
        import win32con
        hwnd = win32gui.FindWindow(None, title)
        if not hwnd:
            return False
        flag = win32con.HWND_TOPMOST if on else win32con.HWND_NOTOPMOST
        win32gui.SetWindowPos(
            hwnd, flag, 0, 0, 0, 0,
            win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_NOACTIVATE,
        )
        return True
    except Exception:
        # fallback: ใช้ property ของ OpenCV (บางบิลด์รองรับ)
        try:
            cv2.setWindowProperty(title, cv2.WND_PROP_TOPMOST, 1.0 if on else 0.0)
            return True
        except Exception:
            return False


def open_camera(cfg):
    cam = CameraStream(
        cfg.camera.index, cfg.camera.width, cfg.camera.height,
        prefer_backend=cfg.camera.backend, use_mjpg=cfg.camera.mjpg, fps=cfg.camera.fps,
    )
    if not cam.is_opened():
        return None
    cam.start()
    deadline = time.time() + 3.0
    while time.time() < deadline:
        ok, _ = cam.read()
        if ok:
            break
        time.sleep(0.02)
    return cam


def resolve_config_path(path_arg: str) -> str:
    """
    หา config.json ที่ "เขียนได้" — ผู้ใช้แก้ไข/กด S เซฟจาก editor ได้จริง
    - ตอนเป็น .exe (one-file): เก็บใน %LOCALAPPDATA%\\MLHandController
      เพื่อให้โฟลเดอร์โปรแกรมเหลือแค่ไฟล์ .exe เดียว
    - ตอนรันจากซอร์ส: ใช้ config.json ข้าง ๆ สคริปต์
    ถ้ายังไม่มี ก็อปค่า default ที่ฝังมา (resource_path) ออกมาให้ 1 ชุด
    """
    if path_arg != "config.json":
        return path_arg   # ผู้ใช้ระบุ path เอง ใช้ตามนั้น
    if getattr(sys, "frozen", False):
        base = appdata_dir()                            # %LOCALAPPDATA%\MLHandController
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    target = os.path.join(base, "config.json")
    if not os.path.exists(target):
        try:
            import shutil
            shutil.copy(resource_path("config.json"), target)
            print(f"[config] สร้าง config.json ที่ {target}")
        except Exception as e:
            print(f"[config] ก็อป config.json ไม่ได้ ({e}) — ใช้ค่า default")
    if getattr(sys, "frozen", False):
        print(f"[config] แก้ค่าได้ที่: {target}")
    return target


def main():
    ap = argparse.ArgumentParser(description="Mobile Legends hand controller")
    ap.add_argument("--test", action="store_true",
                    help="test mode: โชว์ทิศ/ปุ่มที่จะกด แต่ไม่ยิงจริง")
    ap.add_argument("--config", default="config.json", help="path ของ config")
    ap.add_argument("--camera", type=int, default=None, help="override camera index")
    args = ap.parse_args()

    cfg = Config.load(resolve_config_path(args.config))
    if args.camera is not None:
        cfg.camera.index = args.camera

    cap = open_camera(cfg)
    if cap is None or not cap.is_opened():
        print(f"[main] เปิดกล้อง index {cfg.camera.index} ไม่ได้ — "
              f"ลองเปลี่ยน camera.index ใน config.json หรือใช้ --camera 1\n"
              f"       (ปิดโปรแกรมอื่นที่ใช้กล้องอยู่ เช่น OBS/Zoom/เบราว์เซอร์)")
        return

    aw, ah = cap.size
    print(f"[cam] {aw}x{ah} @ {cap.actual_fps:.0f}fps  backend={cap.backend_name}  "
          f"(detect_width={cfg.detect_width})")

    detector = HandDetector()
    controller = Controller(cfg)
    sender = InputSender(cfg, test_mode=args.test)
    overlay = OverlayRenderer()
    editor = ZoneEditor(cfg)

    win = "Mobile Legends - Hand Controller"
    cv2.namedWindow(win, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(win, cfg.camera.width, cfg.camera.height)
    cv2.setMouseCallback(win, editor.on_mouse)

    print("=" * 64)
    print(" พร้อมแล้ว! ยกมือซ้าย=เดิน  มือขวา=เข้าวง+กำหมัดยิงสกิล")
    print(" ตั้งจุดกลาง joystick: วางมือซ้ายตรงกลางที่ถนัด แล้วกด  C")
    print(" จัดวางปุ่มเอง: กด  E  แล้วลากวงด้วยเมาส์ -> กด S เซฟ")
    print(" TEST MODE:", "ON (ไม่ยิงปุ่มจริง)" if args.test else "OFF (ยิงเข้า MuMu)")
    print(" ปุ่มลัด: C=ตั้งจุดกลาง  E=จัดวางปุ่ม  P=ลอยหน้าสุด  T=test  R=reload  Q/Esc=ออก")
    print("=" * 64)

    prev_held: set = set()
    fps = 0.0
    prev_frame_t = time.time()

    calibrating = False
    calib_deadline = 0.0
    preparing = False
    prep_deadline = 0.0

    topmost = cfg.always_on_top
    topmost_applied = False
    icon_set = False

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                print("[main] อ่านเฟรมจากกล้องไม่ได้")
                break

            if cfg.camera.mirror:
                frame = cv2.flip(frame, 1)   # selfie view (mirror ก่อนตรวจ)

            now = time.time()
            dt = now - prev_frame_t
            prev_frame_t = now
            if dt > 0:
                fps = 0.9 * fps + 0.1 * (1.0 / dt)

            # ตรวจบนภาพย่อ (เร็วขึ้น) — landmark เป็น normalized วาดบนภาพเต็มได้เลย
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            fh, fw = rgb.shape[:2]
            if cfg.detect_width and cfg.detect_width < fw:
                dh = int(fh * cfg.detect_width / fw)
                small = cv2.resize(rgb, (cfg.detect_width, dh))
            else:
                small = rgb
            small.flags.writeable = False
            hands = detector.process(small, now)

            aspect = fh / max(fw, 1)   # ให้ทิศ/วงถูกเชิงเรขาคณิต
            held, taps, state = controller.update(hands, now, aspect)

            # โหมดจัดวางปุ่ม: บอกขนาดเฟรมให้ editor + หยุดยิงปุ่มระหว่างแก้ไข
            editor.set_frame_size(frame.shape[1], frame.shape[0])
            if editor.active:
                held, taps = set(), []

            # นับถอยหลัง (ตั้งจุดกลาง หรือ prep ก่อนยิงจริง) — ระหว่างนับ ไม่ยิงปุ่ม
            countdown = None
            if calibrating:
                r = calib_deadline - now
                if r <= 0:
                    calibrating = False
                    if controller.set_origin_from(hands):
                        print("[main] ตั้งจุดกลาง joystick แล้ว")
                    else:
                        print("[main] ไม่เจอมือซ้าย — ยกมือซ้ายให้เห็นชัดแล้วกด C ใหม่")
                else:
                    countdown = (r, "PUT LEFT HAND AT CENTER",
                                 "hold still, then it becomes the joystick center")
                    held, taps = set(), []
            elif preparing:
                r = prep_deadline - now
                if r <= 0:
                    preparing = False
                    print("[main] เริ่มยิงปุ่มจริงแล้ว!")
                else:
                    countdown = (r, "GET READY - SWITCH TO MuMu",
                                 "click the MuMu window & get in place")
                    held, taps = set(), []

            # กด/ปล่อยปุ่มเดินให้ตรงกับทิศ
            sender.apply(held)
            if held != prev_held:
                mode = "TEST" if args.test else "SEND"
                keys = ",".join(sorted(held)) or "-"
                print(f"[{mode}] hold: {keys}")
                prev_held = set(held)

            # แตะปุ่มสกิล
            for key in taps:
                status = sender.tap(key)
                print(f"[{status}] tap '{key}'")

            focused = (not args.test) and sender.is_target_focused()
            overlay.render(frame, state, taps, now, fps, args.test, focused, countdown, editor)
            cv2.imshow(win, frame)
            # ตั้งลอยหน้าสุด + ไอคอน ครั้งแรกหลังหน้าต่างโผล่ (ทำครั้งเดียว)
            if topmost and not topmost_applied:
                topmost_applied = set_topmost(win, True)
            if not icon_set:
                icon_set = set_window_icon(win)

            key = cv2.waitKey(1) & 0xFF
            if editor.handle_key(key):    # โหมดแก้ไขจัดการปุ่ม [ ] S เอง
                pass
            elif key in (ord("q"), 27):
                break
            elif key == ord("e"):
                editor.active = not editor.active
                if editor.active:
                    sender.release_all()   # กันปุ่มค้างระหว่างจัดวาง
                    print("[editor] เข้าโหมดจัดวางปุ่ม — ลากวงด้วยเมาส์, [ ] ปรับขนาด, S เซฟ, E ออก")
                else:
                    editor.last_saved = ""
                    print("[editor] ออกจากโหมดจัดวางปุ่ม")
            elif key == ord("c"):
                calibrating = True
                preparing = False
                calib_deadline = now + cfg.calibrate_countdown
                print(f"[main] ตั้งจุดกลางใน {cfg.calibrate_countdown:.0f} วิ — วางมือซ้ายตรงกลาง")
            elif key == ord("t"):
                args.test = not args.test
                sender.release_all()
                sender.test_mode = args.test
                prev_held = set()
                if not args.test:
                    preparing = True
                    prep_deadline = now + cfg.prep_countdown
                    print(f"[main] TEST OFF — เตรียมตัว {cfg.prep_countdown:.0f} วิ "
                          f"(ไปหน้าต่าง MuMu) ก่อนเริ่มยิงปุ่ม")
                else:
                    preparing = False
                    print("[main] TEST MODE = ON (ไม่ยิงปุ่มจริง)")
            elif key == ord("p"):
                topmost = not topmost
                set_topmost(win, topmost)
                topmost_applied = True
                print(f"[main] preview ลอยหน้าสุด: {'ON' if topmost else 'OFF'}")
            elif key == ord("r"):
                cfg = cfg.reload()
                sender.cfg = cfg
                controller.cfg = cfg
                editor.cfg = cfg
                print("[main] reload config.json แล้ว")

            if cv2.getWindowProperty(win, cv2.WND_PROP_VISIBLE) < 1:
                break
    finally:
        sender.release_all()
        cap.release()
        detector.close()
        cv2.destroyAllWindows()
        print("[main] ปิดโปรแกรมแล้ว")


if __name__ == "__main__":
    main()
