"""Reczny test set_baudrate na PX1122R przez Px1122rConfigClient, plus autodetekcja
aktualnego baudrate portu.

set_baudrate() uzywa standardowej komendy SkyTraq 0x05 "Configure Serial Port",
ktora nie wystepuje w dostepnym AN0039 dla tego modulu (Raw Measurement Data
Extension) - do potwierdzenia na sprzecie. Domyslnie NIE zapisuje do flash
(save_to_flash=False), wiec jesli po zmianie modul przestanie odpowiadac,
power-cycle przywroci poprzedni baudrate.

Protokol SkyTraq nie ma komendy "query baud rate" dla glownego portu (logiczne -
zeby zapytac trzeba juz byc podlaczonym na wlasciwym baudrate; potwierdzone
brakiem takiej pozycji w menu GNSS Viewer). Jedyny sposob "odczytania" aktualnego
baudrate to detect: probowanie kolejnych standardowych predkosci i sprawdzanie,
na ktorej modul odpowiada na get_output_rate().

Uzycie (na RPi, w .venv z extras 'navigation'):
    python rover/scripts/px1122r_baudrate_test.py base|rover detect
    python rover/scripts/px1122r_baudrate_test.py base|rover 460800
    python rover/scripts/px1122r_baudrate_test.py base|rover 460800 --save
"""
from __future__ import annotations

import asyncio
import sys

from rover.common.config import load_service_config
from rover.services.navigation.gnss.px1122r_bus import Px1122rBus, Target
from rover.services.navigation.gnss.px1122r_config import _BAUD_RATE_IDS, Px1122rConfigClient

_QUERY_TIMEOUT_S = 2.0  # przy zlym baudrate _read_frame() moze dlugo nie znalezc START w szumie


async def _try_baud(target: Target, uart_port: str, mux_select_gpio: int, baud: int) -> int | None:
    bus = Px1122rBus(uart_port, baud, mux_select_gpio)
    await bus.start()
    try:
        client = Px1122rConfigClient(bus, target)
        return await asyncio.wait_for(client.get_output_rate(), timeout=_QUERY_TIMEOUT_S)
    except Exception:
        return None
    finally:
        await bus.stop()


async def detect(target: Target, uart_port: str, mux_select_gpio: int) -> None:
    print(f"[{target}] szukam aktywnego baudrate (do {_QUERY_TIMEOUT_S}s na probe)...")
    for baud in sorted(_BAUD_RATE_IDS):
        rate = await _try_baud(target, uart_port, mux_select_gpio, baud)
        if rate is not None:
            print(f"[{target}] {baud}: OK, modul odpowiada (output rate={rate}Hz)")
        else:
            print(f"[{target}] {baud}: brak odpowiedzi")


async def main() -> None:
    if len(sys.argv) < 3 or sys.argv[1] not in ("base", "rover"):
        print("Uzycie: px1122r_baudrate_test.py base|rover detect|nowy_baudrate [--save]")
        sys.exit(1)

    target: Target = sys.argv[1]  # type: ignore[assignment]

    args = load_service_config("navigation").driver_args
    uart_port = args.get("uart_port", "/dev/ttyAMA0")
    current_baudrate = args.get("baudrate", 115200)
    mux_select_gpio = args.get("mux_select_gpio", 17)

    if sys.argv[2] == "detect":
        await detect(target, uart_port, mux_select_gpio)
        return

    new_baud = int(sys.argv[2])
    save = "--save" in sys.argv[3:]

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
