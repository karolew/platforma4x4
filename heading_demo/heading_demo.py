"""Live demo: heading/elevation compass + angle gauges, fed from rover/<id>/nav/pose over MQTT.

Standalone extra, NOT part of platforma4x4 - delete this folder after recording the demo.
Requires: paho-mqtt (pip install paho-mqtt). pyyaml optional, only used to read
../rover/config/rover.yaml for connection defaults.

Usage:
    python heading_demo.py [--host HOST] [--port PORT] [--rover-id ROVER_ID]
"""
from __future__ import annotations

import argparse
import json
import math
import threading
import time
import tkinter as tk
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

import paho.mqtt.client as mqtt

BG = "#0f1115"
PANEL_BG = "#1a1d24"
FG = "#e6e6e6"
GRID = "#333944"
MUTED = "#7a8290"
ARROW_HEADING = "#ffffff"
ARROW_ELEV = "#ffffff"
OK_GREEN = "#3ddc84"
WARN_ORANGE = "#ffb020"
BAD_RED = "#ff5c5c"
COLOR_ROVER = "#3ddc84"
COLOR_BASE = "#2ea8e0"

STALE_S = 2.0
GAUGE_SIZE = 380
MAX_LOG_ENTRIES = 200
MAX_TRAIL_POINTS = 100
POS_RINGS = 4
_NICE_STEPS_M = (0.02, 0.05, 0.1, 0.2, 0.5, 1, 2, 5, 10, 20, 50, 100, 200, 500, 1000)
_EARTH_RADIUS_M = 6371000.0


def polar(cx: float, cy: float, r: float, angle_deg: float) -> tuple[float, float]:
    rad = math.radians(angle_deg)
    return cx + r * math.cos(rad), cy - r * math.sin(rad)


def fix_color(fix_type: str) -> str:
    if "RTK Fix" in fix_type:
        return OK_GREEN
    if "RTK Float" in fix_type or "DGPS" in fix_type:
        return WARN_ORANGE
    if fix_type in ("none", "Fix Unavailable", "Unknown"):
        return BAD_RED
    return FG


def latlon_to_enu(lat: float, lon: float, lat0: float, lon0: float) -> tuple[float, float]:
    """Local flat-earth ENU offset (meters) from anchor (lat0, lon0) - fine over demo-scale distances."""
    e = math.radians(lon - lon0) * _EARTH_RADIUS_M * math.cos(math.radians(lat0))
    n = math.radians(lat - lat0) * _EARTH_RADIUS_M
    return e, n


def pick_step(max_r_m: float, rings: int = POS_RINGS) -> float:
    target = max(max_r_m, 0.02) / rings
    for step in _NICE_STEPS_M:
        if step >= target:
            return step
    return _NICE_STEPS_M[-1]


def load_defaults() -> tuple[str, int, str]:
    cfg_path = Path(__file__).resolve().parent.parent / "rover" / "config" / "rover.yaml"
    if cfg_path.exists():
        try:
            import yaml

            root = yaml.safe_load(cfg_path.read_text())
            return root["mqtt"]["host"], int(root["mqtt"]["port"]), root["rover_id"]
        except Exception:
            pass
    return "localhost", 1883, "rover-01"


@dataclass
class PoseSample:
    timestamp: float
    lat: float
    lon: float
    heading_deg: Optional[float]
    elevation_deg: Optional[float]
    speed_kmh: float
    course_deg: Optional[float]
    alt_msl_m: Optional[float]
    baseline_e_m: Optional[float]
    baseline_n_m: Optional[float]
    fix_type: str
    received_at: float


class MqttFeed:
    """Subscribes to rover/<id>/nav/pose in a background thread; .latest() is thread-safe."""

    def __init__(self, host: str, port: int, rover_id: str) -> None:
        self.topic = f"rover/{rover_id}/nav/pose"
        self._lock = threading.Lock()
        self._latest: Optional[PoseSample] = None
        self._connected = False

        try:
            self._client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1, client_id="heading-demo")
        except AttributeError:
            self._client = mqtt.Client(client_id="heading-demo")  # paho-mqtt 1.x

        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._client.on_message = self._on_message
        self._client.connect_async(host, port)
        self._client.loop_start()

    def _on_connect(self, client, userdata, flags, rc) -> None:
        self._connected = rc == 0
        client.subscribe(self.topic, qos=0)

    def _on_disconnect(self, client, userdata, rc) -> None:
        self._connected = False

    def _on_message(self, client, userdata, msg) -> None:
        try:
            data = json.loads(msg.payload)
            sample = PoseSample(
                timestamp=data["timestamp"],
                lat=data["lat"],
                lon=data["lon"],
                heading_deg=data.get("heading_deg"),
                elevation_deg=data.get("elevation_deg"),
                speed_kmh=data["speed_kmh"],
                course_deg=data.get("course_deg"),
                alt_msl_m=data.get("alt_msl_m"),
                baseline_e_m=data.get("baseline_e_m"),
                baseline_n_m=data.get("baseline_n_m"),
                fix_type=data["fix_type"],
                received_at=time.monotonic(),
            )
        except (json.JSONDecodeError, KeyError):
            return
        with self._lock:
            self._latest = sample

    @property
    def connected(self) -> bool:
        return self._connected

    def latest(self) -> Optional[PoseSample]:
        with self._lock:
            return self._latest

    def close(self) -> None:
        self._client.loop_stop()
        self._client.disconnect()


class HeadingDemoApp:
    FIELDS = ("KURS KOMPASOWY", "ELEWACJA", "LAT", "LON", "WYSOKOŚĆ N.P.M.", "FIX", "CZAS", "PRĘDKOŚĆ", "KURS")

    def __init__(self, root: tk.Tk, feed: MqttFeed, rover_id: str) -> None:
        self.root = root
        self.feed = feed
        root.title(f"Demo Konfiguracja Ruchomej Bazy RTK - {rover_id}")
        root.configure(bg=BG)
        root.resizable(False, False)

        self._anchor: Optional[tuple[float, float]] = None
        self._rover_trail: deque[tuple[float, float]] = deque(maxlen=MAX_TRAIL_POINTS)
        self._base_trail: deque[tuple[float, float]] = deque(maxlen=MAX_TRAIL_POINTS)
        self._last_trail_ts: Optional[float] = None

        gauges = tk.Frame(root, bg=BG)
        gauges.pack(padx=16, pady=(16, 8))
        for col in (0, 1):
            tk.Label(gauges, text="", bg=BG).grid(row=0, column=col)
        tk.Label(
            gauges, text="", bg=BG, fg=MUTED, font=("Consolas", 11, "bold")
        ).grid(row=0, column=2, pady=(0, 4))
        self.compass = tk.Canvas(gauges, width=GAUGE_SIZE, height=GAUGE_SIZE, bg=PANEL_BG, highlightthickness=0)
        self.compass.grid(row=1, column=0, padx=8)
        self.elev = tk.Canvas(gauges, width=GAUGE_SIZE, height=GAUGE_SIZE, bg=PANEL_BG, highlightthickness=0)
        self.elev.grid(row=1, column=1, padx=8)
        self.pos_canvas = tk.Canvas(gauges, width=GAUGE_SIZE, height=GAUGE_SIZE, bg=PANEL_BG, highlightthickness=0)
        self.pos_canvas.grid(row=1, column=2, padx=8)

        self.status_var = tk.StringVar(value="Łączenie...")
        tk.Label(
            root, textvariable=self.status_var, bg=BG, fg=MUTED, font=("Consolas", 10), anchor="w"
        ).pack(fill="x", padx=20)

        table = tk.Frame(root, bg=PANEL_BG)
        table.pack(fill="both", expand=True, padx=16, pady=16)
        table.columnconfigure(1, weight=1)

        self.values: dict[str, tk.StringVar] = {}
        self.value_labels: dict[str, tk.Label] = {}
        for i, name in enumerate(self.FIELDS):
            tk.Label(
                table, text=name, bg=PANEL_BG, fg=MUTED, font=("Consolas", 15, "bold"), anchor="w"
            ).grid(row=i, column=0, sticky="w", padx=(18, 30), pady=6)
            var = tk.StringVar(value="--")
            self.values[name] = var
            lbl = tk.Label(table, textvariable=var, bg=PANEL_BG, fg=FG, font=("Consolas", 15), anchor="w")
            lbl.grid(row=i, column=1, sticky="w", pady=6)
            self.value_labels[name] = lbl

        log_frame = tk.Frame(root, bg=PANEL_BG)
        log_frame.pack(fill="both", expand=False, padx=16, pady=(0, 16))
        tk.Label(
            log_frame, text="LOG ZMIAN HEADING", bg=PANEL_BG, fg=MUTED, font=("Consolas", 11, "bold"), anchor="w"
        ).pack(fill="x", padx=12, pady=(8, 4))
        log_inner = tk.Frame(log_frame, bg=PANEL_BG)
        log_inner.pack(fill="both", expand=True, padx=12, pady=(0, 10))
        scrollbar = tk.Scrollbar(log_inner)
        scrollbar.pack(side="right", fill="y")
        self.log_box = tk.Listbox(
            log_inner,
            bg="#11141a",
            fg=FG,
            font=("Consolas", 11),
            height=7,
            bd=0,
            highlightthickness=0,
            activestyle="none",
            selectbackground="#11141a",
            selectforeground=FG,
            yscrollcommand=scrollbar.set,
        )
        self.log_box.pack(side="left", fill="both", expand=True)
        scrollbar.config(command=self.log_box.yview)

        self._last_fix: Optional[str] = None
        self._heading_present: Optional[bool] = None

        self._tick()

    def _log(self, text: str) -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_box.insert("end", f"[{ts}] {text}")
        if self.log_box.size() > MAX_LOG_ENTRIES:
            self.log_box.delete(0)
        self.log_box.see("end")

    def _check_events(self, sample: PoseSample) -> None:
        if sample.fix_type != self._last_fix:
            if self._last_fix is not None:
                self._log(f"FIX: {self._last_fix} -> {sample.fix_type}")
            self._last_fix = sample.fix_type

        heading_present = sample.heading_deg is not None
        if self._heading_present is not None and heading_present != self._heading_present:
            if heading_present:
                self._log(f"HEADING: brak -> {sample.heading_deg:.1f} deg")
            else:
                self._log("HEADING: utracono (wartosc -> brak)")
        self._heading_present = heading_present

    def _tick(self) -> None:
        sample = self.feed.latest()
        if sample is not None:
            self._check_events(sample)
            self._update_position_trails(sample)
        stale = sample is None or (time.monotonic() - sample.received_at) > STALE_S
        self._draw_compass(sample.heading_deg if sample else None, stale)
        self._draw_elevation(sample.elevation_deg if sample else None, stale)
        self._draw_position()
        self._update_table(sample, stale)
        self.root.after(100, self._tick)

    def _update_position_trails(self, sample: PoseSample) -> None:
        if sample.timestamp == self._last_trail_ts:
            return
        self._last_trail_ts = sample.timestamp

        if self._anchor is None:
            self._anchor = (sample.lat, sample.lon)
        lat0, lon0 = self._anchor

        base_e, base_n = latlon_to_enu(sample.lat, sample.lon, lat0, lon0)
        self._base_trail.append((base_e, base_n))

        if sample.baseline_e_m is not None and sample.baseline_n_m is not None:
            self._rover_trail.append((base_e + sample.baseline_e_m, base_n + sample.baseline_n_m))

    def _update_table(self, sample: Optional[PoseSample], stale: bool) -> None:
        if sample is None:
            for var in self.values.values():
                var.set("--")
            self.status_var.set(
                f"Brak danych - MQTT {'połączony' if self.feed.connected else 'rozłączony'}, temat {self.feed.topic}"
            )
            return

        self.values["KURS KOMPASOWY"].set(f"{sample.heading_deg:.2f} deg" if sample.heading_deg is not None else "brak")
        self.values["ELEWACJA"].set(f"{sample.elevation_deg:.2f} deg" if sample.elevation_deg is not None else "brak")
        self.values["LAT"].set(f"{sample.lat:.8f}")
        self.values["LON"].set(f"{sample.lon:.8f}")
        self.values["WYSOKOŚĆ N.P.M."].set(f"{sample.alt_msl_m:.2f} m" if sample.alt_msl_m is not None else "brak")
        self.values["FIX"].set(sample.fix_type)
        self.value_labels["FIX"].configure(fg=BAD_RED if stale else fix_color(sample.fix_type))
        self.values["CZAS"].set(datetime.fromtimestamp(sample.timestamp).strftime("%Y-%m-%d %H:%M:%S"))
        self.values["PRĘDKOŚĆ"].set(f"{sample.speed_kmh:.1f} km/h")
        self.values["KURS"].set(f"{sample.course_deg:.1f} deg" if sample.course_deg is not None else "brak")

        age = time.monotonic() - sample.received_at
        state = "BRAK POŁĄCZENIA" if stale else "POŁĄCZONO"
        self.status_var.set(f"{state} - temat {self.feed.topic} - ostatnia próbka {age:.1f}s temu")

    def _draw_position(self) -> None:
        c = self.pos_canvas
        c.delete("all")
        cx = cy = GAUGE_SIZE / 2
        half = GAUGE_SIZE / 2 - 40

        all_pts = list(self._base_trail) + list(self._rover_trail)
        max_r = max((max(abs(e), abs(n)) for e, n in all_pts), default=0.05)
        step = pick_step(max_r)
        scale = half / (step * POS_RINGS)

        c.create_rectangle(cx - half, cy - half, cx + half, cy + half, outline=GRID, width=2)
        for i in range(1, POS_RINGS + 1):
            d = half * i / POS_RINGS
            c.create_rectangle(cx - d, cy - d, cx + d, cy + d, outline=GRID, width=1)
            label = step * i
            text = f"{label:.2f} m" if label < 1 else f"{label:.0f} m"
            c.create_text(cx + 4, cy + d, text=text, fill=MUTED, font=("Consolas", 8), anchor="nw")

        c.create_line(cx - half, cy, cx + half, cy, fill=GRID)
        c.create_line(cx, cy - half, cx, cy + half, fill=GRID)
        c.create_text(cx - half + 14, cy - half - 10, text="N", fill=MUTED, font=("Consolas", 10, "bold"))
        c.create_text(cx + half + 12, cy + 4, text="E", fill=MUTED, font=("Consolas", 10, "bold"))

        def plot(trail: deque[tuple[float, float]], color: str, name: str) -> None:
            pts = list(trail)
            for i, (e, n) in enumerate(pts):
                x, y = cx + e * scale, cy - n * scale
                rad = 4 if i == len(pts) - 1 else 2.5
                c.create_oval(x - rad, y - rad, x + rad, y + rad, fill=color, outline="")
            if pts:
                ex, en = pts[-1]
                x, y = cx + ex * scale, cy - en * scale
                c.create_text(x + 10, y, text=name, fill=color, font=("Consolas", 10, "bold"), anchor="w")

        plot(self._base_trail, COLOR_BASE, "BASE")
        plot(self._rover_trail, COLOR_ROVER, "ROVER")

        if not all_pts:
            c.create_text(cx, cy, text="BRAK DANYCH POZYCJI", fill=BAD_RED, font=("Consolas", 12, "bold"))

    def _draw_compass(self, heading: Optional[float], stale: bool) -> None:
        c = self.compass
        c.delete("all")
        cx = cy = GAUGE_SIZE / 2
        r = GAUGE_SIZE / 2 - 40

        c.create_oval(cx - r, cy - r, cx + r, cy + r, outline=GRID, width=2)
        for deg in range(0, 360, 10):
            major = deg % 30 == 0
            r_in = r - (16 if major else 8)
            c.create_line(*polar(cx, cy, r, 90 - deg), *polar(cx, cy, r_in, 90 - deg), fill=GRID, width=2 if major else 1)
            if major:
                c.create_text(*polar(cx, cy, r - 30, 90 - deg), text=str(deg), fill=MUTED, font=("Consolas", 9))

        for label, deg in (("N", 0), ("E", 90), ("S", 180), ("W", 270)):
            c.create_text(*polar(cx, cy, r + 18, 90 - deg), text=label, fill=FG, font=("Consolas", 15, "bold"))

        c.create_oval(cx - 5, cy - 5, cx + 5, cy + 5, fill=MUTED, outline="")

        if heading is None:
            c.create_text(cx, cy , text="BRAK KK", fill=BAD_RED, font=("Consolas", 12, "bold"))
            return

        color = MUTED if stale else ARROW_HEADING
        tip = polar(cx, cy, r - 24, 90 - heading)
        tail = polar(cx, cy, (r - 24) * 0.2, 90 - heading + 180)
        c.create_line(*tail, *tip, fill=color, width=2, arrow=tk.LAST, arrowshape=(10, 12, 3), capstyle=tk.ROUND)
        suffix = " (stare)" if stale else ""
        c.create_text(cx, cy + r + 22, text=f"{heading:.1f} deg{suffix}", fill=color, font=("Consolas", 14, "bold"))

    def _draw_elevation(self, elevation: Optional[float], stale: bool) -> None:
        c = self.elev
        c.delete("all")
        vx, vy = 60, GAUGE_SIZE / 2
        r = min(GAUGE_SIZE - 100, GAUGE_SIZE - 60) / 2

        c.create_arc(vx - r, vy - r, vx + r, vy + r, start=-90, extent=180, style=tk.ARC, outline=GRID, width=2)
        c.create_line(vx, vy, vx + r, vy, fill=GRID, width=2)
        for deg in range(-90, 91, 10):
            major = deg % 30 == 0
            r_in = r - (16 if major else 8)
            c.create_line(*polar(vx, vy, r, deg), *polar(vx, vy, r_in, deg), fill=GRID, width=2 if major else 1)
            if major:
                c.create_text(*polar(vx, vy, r + 18, deg), text=str(deg), fill=MUTED, font=("Consolas", 9))

        c.create_oval(vx - 5, vy - 5, vx + 5, vy + 5, fill=MUTED, outline="")

        if elevation is None:
            c.create_text(vx + r / 2, vy + r / 100, text="BRAK ELEWACJI", fill=BAD_RED, font=("Consolas", 12, "bold"))
            return

        color = MUTED if stale else ARROW_ELEV
        elevation = max(-90.0, min(90.0, elevation))
        tip = polar(vx, vy, r - 24, elevation)
        c.create_line(vx, vy, *tip, fill=color, width=2, arrow=tk.LAST, arrowshape=(10, 12, 3), capstyle=tk.ROUND)
        suffix = " (stare)" if stale else ""
        c.create_text(vx + r / 2, vy + r + 22, text=f"{elevation:.1f} deg{suffix}", fill=color, font=("Consolas", 14, "bold"))


class SimulatedFeed:
    """Sztuczne dane (heading/elewacja/pozycja) bez MQTT - do testow przez --fake."""

    topic = "sztuczne dane (--fake, brak MQTT)"

    def __init__(self) -> None:
        self._t0 = time.time()
        self._lat0, self._lon0 = 52.2318, 21.0060

    @property
    def connected(self) -> bool:
        return True

    def latest(self) -> PoseSample:
        t = time.time() - self._t0
        heading = (60 * math.sin(t / 6) + 180) % 360
        heading_lost = int(t / 10) % 4 == 3  # co ~40s heading znika na chwile - testuje log
        fix = "RTK Fix" if int(t / 8) % 3 != 1 else "RTK Float"  # co ~24s przelacza sie na Float - testuje log
        jitter_lat = 0.02 * math.sin(t * 1.3) / 111320.0
        jitter_lon = 0.02 * math.cos(t * 1.7) / (111320.0 * math.cos(math.radians(self._lat0)))

        return PoseSample(
            timestamp=time.time(),
            lat=self._lat0 + jitter_lat,
            lon=self._lon0 + jitter_lon,
            heading_deg=None if heading_lost else heading,
            elevation_deg=20 * math.sin(t / 4),
            speed_kmh=abs(2 * math.sin(t / 5)),
            course_deg=(heading + 15) % 360,
            alt_msl_m=118.0 + math.sin(t / 3),
            baseline_e_m=math.cos(math.radians(heading)),
            baseline_n_m=math.sin(math.radians(heading)),
            fix_type=fix,
            received_at=time.monotonic(),
        )

    def close(self) -> None:
        pass


def parse_args() -> argparse.Namespace:
    host, port, rover_id = load_defaults()
    parser = argparse.ArgumentParser(description="Live RTK heading/elevation demo over MQTT.")
    parser.add_argument("--host", default=host)
    parser.add_argument("--port", type=int, default=port)
    parser.add_argument("--rover-id", default=rover_id)
    parser.add_argument("--fake", action="store_true", help="Sztuczne dane zamiast MQTT - test bez brokera i sprzetu")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    feed = SimulatedFeed() if args.fake else MqttFeed(args.host, args.port, args.rover_id)
    root = tk.Tk()
    HeadingDemoApp(root, feed, args.rover_id)
    try:
        root.mainloop()
    finally:
        feed.close()


if __name__ == "__main__":
    main()
