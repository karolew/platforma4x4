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

from rover.common.messages.nav import Pose
from rover.services.navigation.gnss.nmea_parser import NMEAParser
from rover.services.navigation.gnss.ntrip_client import NtripClient
from rover.services.navigation.gnss.px1122r_bus import Px1122rBus
from rover.services.navigation.interface import NavigationProvider


def _is_gga(sentence: str) -> bool:
    return sentence.startswith("$") and sentence[1:].split(",", 1)[0].endswith("GGA")


class RtkGnssProvider(NavigationProvider):
    def __init__(
        self,
        uart_port: str = "/dev/ttyAMA0",
        baudrate: int = 115200,
        mux_select_gpio: int = 17,
        ntrip: dict[str, object] | None = None,
        gga_interval_s: float = 300.0,
    ) -> None:
        ntrip = ntrip or {}
        self._gga_interval_s = gga_interval_s
        self._last_gga_sent_at = 0.0
        self._bus = Px1122rBus(uart_port, baudrate, mux_select_gpio)
        self._ntrip = NtripClient(
            host=str(ntrip.get("host", "")),
            port=int(ntrip.get("port", 2101)),
            mountpoint=str(ntrip.get("mountpoint", "")),
            user=str(ntrip.get("user", "")),
            password=str(ntrip.get("password", "")),
        )
        self._parser = NMEAParser()
        self._pose = Pose(timestamp=0.0, lat=0.0, lon=0.0, heading_deg=0.0, speed_kmh=0.0, fix_type="none")
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

        self._parser.parse(text)
        self._pose = Pose(
            timestamp=time.time(),
            lat=self._parser.lat or 0.0,
            lon=self._parser.lon or 0.0,
            heading_deg=self._parser.heading or 0.0,
            speed_kmh=self._parser.speed or 0.0,
            fix_type=self._parser.quality or "none",
        )

        if _is_gga(text):
            now = time.time()
            if now - self._last_gga_sent_at >= self._gga_interval_s:
                await self._ntrip.send_gga(text)
                self._last_gga_sent_at = now
