"""Reczny test set_baudrate na PX1122R przez Px1122rConfigClient.

set_baudrate() uzywa standardowej komendy SkyTraq 0x05 "Configure Serial Port",
ktora nie wystepuje w dostepnym AN0039 dla tego modulu (Raw Measurement Data
Extension) - do potwierdzenia na sprzecie. Domyslnie NIE zapisuje do flash
(save_to_flash=False), wiec jesli po zmianie modul przestanie odpowiadac,
power-cycle przywroci poprzedni baudrate.

Uzycie (na RPi, w .venv z extras 'navigation'):
    python rover/scripts/px1122r_baudrate_test.py base 460800
    python rover/scripts/px1122r_baudrate_test.py base 460800 --save
"""
from __future__ import annotations

import asyncio
import sys

from rover.common.config import load_service_config
from rover.services.navigation.gnss.px1122r_bus import Px1122rBus, Target
from rover.services.navigation.gnss.px1122r_config import Px1122rConfigClient


async def main() -> None:
    if len(sys.argv) < 3 or sys.argv[1] not in ("base", "rover"):
        print("Uzycie: px1122r_baudrate_test.py base|rover nowy_baudrate [--save]")
        sys.exit(1)

    target: Target = sys.argv[1]  # type: ignore[assignment]
    new_baud = int(sys.argv[2])
    save = "--save" in sys.argv[3:]

    args = load_service_config("navigation").driver_args
    uart_port = args.get("uart_port", "/dev/ttyAMA0")
    current_baudrate = args.get("baudrate", 115200)
    mux_select_gpio = args.get("mux_select_gpio", 17)

    bus = Px1122rBus(uart_port, current_baudrate, mux_select_gpio)
    await bus.start()
    client = Px1122rConfigClient(bus, target)
    try:
        rate = await client.get_output_rate()
        print(f"[{target}] polaczenie na {current_baudrate} OK, aktualny rate={rate}Hz")

        print(f"[{target}] przelaczam na {new_baud} (save_to_flash={save})...")
        await client.set_baudrate(new_baud, save_to_flash=save)
        print(f"[{target}] OK (ACK otrzymany) - modul powinien juz nadawac na {new_baud}")
    finally:
        await bus.stop()

    bus2 = Px1122rBus(uart_port, new_baud, mux_select_gpio)
    await bus2.start()
    client2 = Px1122rConfigClient(bus2, target)
    try:
        rate = await client2.get_output_rate()
        print(f"[{target}] polaczenie na {new_baud} OK, aktualny rate={rate}Hz - baudrate zmieniony poprawnie")
    finally:
        await bus2.stop()


if __name__ == "__main__":
    asyncio.run(main())
