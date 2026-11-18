"""System-tray app: DriveMind lives next to the clock.

The tray icon is a small ring coloured by C: health (teal good, amber watch, red
critical). The menu has: free space, Open dashboard, Tidy now, Pause guardian, Quit.
It also runs the local server (dashboard + phone sync) and the background guardian.

Needs:  pip install "drivemind[tray]"   (pystray + Pillow)
"""

from __future__ import annotations

import threading
import time
import webbrowser
from typing import Optional

COLORS = {"good": (94, 234, 212), "watch": (251, 191, 36), "critical": (248, 113, 113)}


def ring_icon(status: str = "good", used_fraction: float = 0.5, size: int = 64):
    """Draw the tray icon: a ring filled to how full the drive is."""
    from PIL import Image, ImageDraw
    s = size * 4
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    w = int(s * 0.16)
    box = [w // 2, w // 2, s - w // 2, s - w // 2]
    d.arc(box, 0, 360, fill=(70, 76, 86, 255), width=w)
    sweep = max(8, min(360, int(360 * used_fraction)))
    d.arc(box, -90, -90 + sweep, fill=COLORS.get(status, COLORS["good"]) + (255,), width=w)
    return img.resize((size, size))


class TrayApp:
    def __init__(self, port: int = 7878):
        self.port = port
        self.paused = False
        self.icon = None
        self._stop = threading.Event()

    # ---------------------------------------------------------------- server --
    def start_server(self) -> None:
        import uvicorn
        from . import devices
        from .api import app
        lan = devices.any_paired()
        app.state.lan, app.state.port = lan, self.port
        cfg = uvicorn.Config(app, host="0.0.0.0" if lan else "127.0.0.1", port=self.port, log_level="warning")
        threading.Thread(target=uvicorn.Server(cfg).run, name="drivemind-server", daemon=True).start()

    def start_guardian(self) -> None:
        from .service import Guardian
        self.guardian = Guardian()
        self.guardian.start()

    # ----------------------------------------------------------------- state --
    def status(self) -> Optional[dict]:
        from .config import Settings
        from .disk import drive_status, system_drive
        st = drive_status(system_drive(), Settings.load().low_space_percent)
        return st.to_dict() if st else None

    def refresh(self) -> None:
        from .scanner import human
        st = self.status()
        if not st or not self.icon:
            return
        self.icon.icon = ring_icon(st["status"], 1 - st["free_percent"] / 100)
        self.icon.title = f"DriveMind — {st['drive']} {human(st['free'])} free ({st['status']})"

    def _loop(self) -> None:
        while not self._stop.wait(120):
            try:
                self.refresh()
            except Exception:
                pass

    # --------------------------------------------------------------- actions --
    def open_dashboard(self, *_):
        webbrowser.open(f"http://127.0.0.1:{self.port}")

    def tidy_now(self, *_):
        from .api import tidy_now
        from .scanner import human
        r = tidy_now()
        msg = f"Cleared {r['done']} items, freed {human(r['freed_bytes'])}."
        if r["waiting"]:
            msg += f" {r['waiting']} wait for your review."
        try:
            self.icon.notify(msg, "DriveMind")
        except Exception:
            pass
        self.refresh()

    def toggle_pause(self, *_):
        self.paused = not self.paused
        if self.paused:
            self.guardian.stop()
        else:
            self.start_guardian()

    def quit(self, *_):
        self._stop.set()
        try:
            self.guardian.stop()
        except Exception:
            pass
        self.icon.stop()

    def already_running(self) -> bool:
        import socket
        with socket.socket() as sock:
            sock.settimeout(0.5)
            return sock.connect_ex(("127.0.0.1", self.port)) == 0

    def run(self) -> None:
        if self.already_running():  # second launch: just show the dashboard
            self.open_dashboard()
            return
        import pystray
        from pystray import Menu, MenuItem as Item
        from .scanner import human
        self.start_server()
        self.start_guardian()
        st = self.status() or {"status": "good", "free_percent": 50, "free": 0, "drive": "C:\\"}

        def free_text(_):
            s = self.status()
            return f"{s['drive']} — {human(s['free'])} free" if s else "Drive status unavailable"

        menu = Menu(
            Item(free_text, None, enabled=False),
            Menu.SEPARATOR,
            Item("Open dashboard", self.open_dashboard, default=True),
            Item("Tidy now", self.tidy_now),
            Item(lambda _: "Resume guardian" if self.paused else "Pause guardian", self.toggle_pause),
            Menu.SEPARATOR,
            Item("Quit DriveMind", self.quit),
        )
        self.icon = pystray.Icon("DriveMind", ring_icon(st["status"], 1 - st["free_percent"] / 100),
                                 "DriveMind", menu)
        threading.Thread(target=self._loop, daemon=True).start()
        time.sleep(0.5)
        self.refresh()
        self.icon.run()
