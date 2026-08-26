"""Zrzut surowego NMEA z wybranego targetu (Base/Rover) przez czas N sekund.

Test empiryczny: ktory fizyczny modul faktycznie emituje PSTI,035/GNTHS (heading)
na swoim TXD. Datasheet PX1122R (Advanced Moving Base) jest niejednoznaczny co do
tego ktory modul ma "NMEA Out" w tym trybie - szybciej to zmierzyc niz zgadywac
z rysunku.

Uzycie (na RPi, w .venv z extras 'navigation', po `sudo systemctl stop rover-navigation`):
    python rover/scripts/nmea_dump_test.py base 10
    python rover/scripts/nmea_dump_test.py rover 10
"""
from __future__ import annotations

import asyncio
import sys
import time

from rover.common.config import load_service_config
from rover.services.navigation.gnss.px1122r_bus import Px1122rBus, Target


async def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] not in ("base", "rover"):
        print("Uzycie: nmea_dump_test.py base|rover [sekundy]")
        sys.exit(1)

    target: Target = sys.argv[1]  # type: ignore[assignment]
    duration_s = float(sys.argv[2]) if len(sys.argv) > 2 else 10.0

    args = load_service_config("navigation").driver_args
    bus = Px1122rBus(
        args.get("uart_port", "/dev/ttyAMA0"),
        args.get("baudrate", 115200),
        args.get("mux_select_gpio", 17),
    )
    await bus.start()
    await bus.select(target)
    print(f"[{target}] nasluch przez {duration_s}s...")

    buffer = b""
    deadline = time.monotonic() + duration_s
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
                    print(text)
    finally:
        await bus.stop()


if __name__ == "__main__":
    asyncio.run(main())
