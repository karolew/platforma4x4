"""Reczny test get/set_output_rate na PX1122R przez Px1122rConfigClient.

Uzycie (na RPi, w .venv z extras 'navigation'):
    python rover/scripts/px1122r_rate_test.py base        # odczyt aktualnego rate
    python rover/scripts/px1122r_rate_test.py base 5      # ustawienie 5Hz + odczyt po zmianie
    python rover/scripts/px1122r_rate_test.py rover

Uwaga: mux przelacza sie automatycznie na wybrany target (Px1122rConfigClient
woła Px1122rBus.select przy kazdym requescie) - nie trzeba nic robic recznie.
"""
from __future__ import annotations

import asyncio
import sys

from rover.common.config import load_service_config
from rover.services.navigation.gnss.px1122r_bus import Px1122rBus, Target
from rover.services.navigation.gnss.px1122r_config import Px1122rConfigClient


async def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] not in ("base", "rover"):
        print("Uzycie: px1122r_rate_test.py base|rover [nowy_rate_hz]")
        sys.exit(1)

    target: Target = sys.argv[1]  # type: ignore[assignment]
    new_hz = int(sys.argv[2]) if len(sys.argv) > 2 else None

    args = load_service_config("navigation").driver_args
    bus = Px1122rBus(
        args.get("uart_port", "/dev/ttyAMA0"),
        args.get("baudrate", 115200),
        args.get("mux_select_gpio", 17),
    )
    await bus.start()
    client = Px1122rConfigClient(bus, target)
    try:
        rate = await client.get_output_rate()
        print(f"[{target}] aktualny output rate: {rate}Hz")

        if new_hz is not None:
            print(f"[{target}] ustawiam {new_hz}Hz...")
            await client.set_output_rate(new_hz)
            rate = await client.get_output_rate()
            print(f"[{target}] output rate po zmianie: {rate}Hz")
    finally:
        await bus.stop()


if __name__ == "__main__":
    asyncio.run(main())
