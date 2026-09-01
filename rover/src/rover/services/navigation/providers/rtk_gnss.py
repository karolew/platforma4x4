"""Moving-base RTK: 2x PX1122R na wspolnym UART0 + CD4052.

Normalna praca: select na Base na stale (patrz Px1122rBus), ciagly zapis RTCM
(z NTRIP/VBS) do Base RXD i ciagly odczyt NMEA z Base TXD - Base sam liczy
heading/baseline dzieki bezposredniemu laczu do Rovera poza RPi. Zero
przelaczania muxa w tej petli - Rover jest dotykany tylko przy konfiguracji
(Px1122rConfigClient), nie tutaj.
"""
from __future__ import annotations

import asyncio
import time
from typing import Optional

from rover.common.messages.nav import Pose
from rover.services.navigation.gnss.nmea_parser_lite import NavigationState, NMEAParser
from rover.services.navigation.gnss.ntrip_client import NtripClient
from rover.services.navigation.gnss.px1122r_bus import Px1122rBus
from rover.services.navigation.interface import NavigationProvider


# Heading (THS) jest wiarygodny tylko gdy pochodzi z tej samej fizycznej bazy co
# skonfigurowany baseline_length_m (Rover, operational_function=MOVING_BASE) - PSTI,035
# niesie zmierzona dlugosc tej samej baseline. Rozjazd > tolerancji = zly fix ambiguity
# albo zla konfiguracja - heading traktowany jako niewiarygodny.
_HEADING_BASELINE_TOLERANCE = 0.10


def _is_gga(sentence: str) -> bool:
    return sentence.startswith("$") and sentence[1:].split(",", 1)[0].endswith("GGA")


def _heading_deg(state: NavigationState, configured_baseline_m: float) -> Optional[float]:
    """THS heading, ale tylko gdy status='A' I zmierzony baseline (PSTI,035) zgadza sie
    (+/-10%) ze skonfigurowanym baseline_length_m - patrz _HEADING_BASELINE_TOLERANCE.
    None (nie 0.0!) w kazdym innym przypadku - robot autonomiczny konsumuje ten Pose,
    nie zgadujemy heading.
    """
    if state.heading_deg is None or state.heading_mode != "A":
        return None
    if state.baseline_len_035 is None or configured_baseline_m <= 0:
        return None
    if abs(state.baseline_len_035 - configured_baseline_m) > configured_baseline_m * _HEADING_BASELINE_TOLERANCE:
        return None
    return state.heading_deg


def _elevation_deg(state: NavigationState) -> Optional[float]:
    """Kat elewacji baseline PSTI,035, tylko gdy ta baseline ma RTK Fix (mode='R') -
    przy Float wektor E/N/U (a wiec i elewacja) jest zbyt niestabilny, by mu ufac."""
    if state.baseline_mode_035 != "R":
        return None
    return state.baseline_elevation_deg_035


class RtkGnssProvider(NavigationProvider):
    def __init__(
        self,
        uart_port: str = "/dev/ttyAMA0",
        baudrate: int = 115200,
        mux_select_gpio: int = 17,
        ntrip: dict[str, object] | None = None,
        gga_interval_s: float = 300.0,
        baseline_length_m: float = 1.0,  # dlugosc anten Base<->Rover (moving base) - patrz configure_as_rover(); zrodlo prawdy dla walidacji heading_deg (_heading_deg)
    ) -> None:
        ntrip = ntrip or {}
        self._gga_interval_s = gga_interval_s
        self._last_gga_sent_at = 0.0
        self._baseline_length_m = baseline_length_m
        self._bus = Px1122rBus(uart_port, baudrate, mux_select_gpio)
        self._ntrip = NtripClient(
            host=str(ntrip.get("host", "")),
            port=int(ntrip.get("port", 2101)),
            mountpoint=str(ntrip.get("mountpoint", "")),
            user=str(ntrip.get("user", "")),
            password=str(ntrip.get("password", "")),
        )
        # unit_format="iso8601": speed w km/h (Pose.speed_kmh); coord_format="decimal_degrees": lat/lon jako stopnie dziesietne
        self._parser = NMEAParser(unit_format="iso8601", coord_format="decimal_degrees")
        self._pose = Pose(
            timestamp=0.0, lat=0.0, lon=0.0, heading_deg=None, elevation_deg=None, speed_kmh=0.0, fix_type="none"
        )
        self._tasks: list[asyncio.Task[None]] = []

    async def start(self) -> None:
        await self._bus.start()
        await self._ntrip.connect()
        self._tasks = [
            asyncio.create_task(self._rtcm_forward_loop()),
            asyncio.create_task(self._nmea_read_loop()),
        ]

    async def stop(self) -> None:
        for task in self._tasks:
            task.cancel()
        await self._ntrip.close()
        await self._bus.stop()

    async def read_pose(self) -> Pose:
        for task in self._tasks:
            if task.done():
                task.result()  # propaguje wyjatek z tla (np. NotImplementedError z parsera)
        return self._pose

    async def _rtcm_forward_loop(self) -> None:
        while True:
            rtcm = await self._ntrip.read_rtcm()
            if rtcm:
                await self._bus.write(rtcm)

    async def _nmea_read_loop(self) -> None:
        buffer = b""
        while True:
            chunk = await self._bus.read()
            if not chunk:
                await asyncio.sleep(0.01)
                continue
            buffer += chunk
            while b"\r\n" in buffer:
                line, buffer = buffer.split(b"\r\n", 1)
                await self._handle_line(line)

    async def _handle_line(self, line: bytes) -> None:
        text = line.decode("ascii", errors="ignore")
        if not text.startswith("$"):
            return

        self._parser.feed_line(text)
        state = self._parser.get_state()
        heading_deg = _heading_deg(state, self._baseline_length_m)
        elevation_deg = _elevation_deg(state)
        self._pose = Pose(
            timestamp=time.time(),
            lat=state.lat or 0.0,
            lon=state.lon or 0.0,
            heading_deg=heading_deg,
            elevation_deg=elevation_deg,
            speed_kmh=state.speed or 0.0,
            course_deg=state.course_deg,
            alt_msl_m=state.alt,
            baseline_e_m=state.baseline_e_035,
            baseline_n_m=state.baseline_n_035,
            fix_type=state.quality_str,
        )

        if _is_gga(text):
            now = time.time()
            if now - self._last_gga_sent_at >= self._gga_interval_s:
                await self._ntrip.send_gga(text)
                self._last_gga_sent_at = now
