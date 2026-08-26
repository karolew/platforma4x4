"""Test: czy Base faktycznie przekazuje dane Roverowi po bezposrednim drucie
(SDA/SCL<->RXD2), gdy Base jest AKTYWNIE karmiony swiezym RTCM z NTRIP.

Rozni sie od nmea_dump_test.py tym, ze nie wymaga zatrzymania rover-navigation
"na zimno" - sam replikuje minimalna wersje jego petli (RTCM->Base + przesylanie
GGA do NTRIP) przez WARMUP_S, a dopiero potem na chwile podglada Rovera. Eliminuje
to falszywy negatyw z powodu braku swiezych korekt w Base w momencie testu.

Uzycie (na RPi, w .venv z extras 'navigation', po `sudo systemctl stop rover-navigation`):
    python rover/scripts/relay_check_test.py [warmup_s] [peek_s]
"""
from __future__ import annotations

import asyncio
import sys
import time

from rover.common.config import load_service_config
from rover.services.navigation.gnss.ntrip_client import NtripClient
from rover.services.navigation.gnss.px1122r_bus import Px1122rBus


def _is_gga(sentence: str) -> bool:
    return sentence.startswith("$") and sentence[1:].split(",", 1)[0].endswith("GGA")


async def main() -> None:
    warmup_s = float(sys.argv[1]) if len(sys.argv) > 1 else 25.0
    peek_s = float(sys.argv[2]) if len(sys.argv) > 2 else 8.0

    args = load_service_config("navigation").driver_args
    ntrip_cfg = args.get("ntrip", {})
    bus = Px1122rBus(
        args.get("uart_port", "/dev/ttyAMA0"),
        args.get("baudrate", 115200),
        args.get("mux_select_gpio", 17),
    )
    ntrip = NtripClient(
        host=str(ntrip_cfg.get("host", "")),
        port=int(ntrip_cfg.get("port", 2101)),
        mountpoint=str(ntrip_cfg.get("mountpoint", "")),
        user=str(ntrip_cfg.get("user", "")),
        password=str(ntrip_cfg.get("password", "")),
    )

    await bus.start()  # select("base") domyslnie
    await ntrip.connect()
    print(f"NTRIP polaczony. Karmie Base przez {warmup_s}s (RTCM in, GGA up)...")

    gga_sent = False
    buffer = b""
    stop = False

    async def rtcm_forward() -> None:
        while not stop:
            rtcm = await ntrip.read_rtcm()
            if rtcm:
                await bus.write(rtcm)

    async def base_read_and_report() -> None:
        nonlocal buffer, gga_sent
        last_quality = None
        while not stop:
            chunk = await bus.read()
            if not chunk:
                await asyncio.sleep(0.01)
                continue
            buffer += chunk
            while b"\r\n" in buffer:
                line, buffer = buffer.split(b"\r\n", 1)
                text = line.decode("ascii", errors="ignore")
                if not gga_sent and _is_gga(text):
                    await ntrip.send_gga(text)
                    gga_sent = True
                    print(f"[base] GGA wyslane do NTRIP: {text}")
                if _is_gga(text):
                    quality = text.split(",")[6] if len(text.split(",")) > 6 else "?"
                    if quality != last_quality:
                        print(f"[base] GGA quality={quality}")
                        last_quality = quality

    rtcm_task = asyncio.create_task(rtcm_forward())
    read_task = asyncio.create_task(base_read_and_report())
    await asyncio.sleep(warmup_s)
    stop = True
    rtcm_task.cancel()
    read_task.cancel()

    print(f"\n--- Przelaczam na Rover, podgladam {peek_s}s (Base przestaje dostawac RTCM na ten czas) ---")
    await bus.select("rover")
    buffer = b""
    deadline = time.monotonic() + peek_s
    saw_anything = False
    try:
        while time.monotonic() < deadline:
            chunk = await bus.read()
            if not chunk:
                await asyncio.sleep(0.01)
                continue
            buffer += chunk
            while b"\r\n" in buffer:
                line, buffer = buffer.split(b"\r\n", 1)
                text = line.decode("ascii", errors="ignore")
                if text.startswith("$"):
                    saw_anything = True
                    if "THS" in text or "PSTI,035" in text or "PSTI,032" in text or "GGA" in text:
                        print(f"[rover] {text}")
    finally:
        await bus.stop()
        await ntrip.close()

    if not saw_anything:
        print("[rover] BRAK jakichkolwiek zdan NMEA - port/mux martwy w tym oknie.")


if __name__ == "__main__":
    asyncio.run(main())
