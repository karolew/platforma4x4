"""Reczny test restart() (0x01 "System Restart") na PX1122R.

Standardowa komenda z bazowego binarnego protokolu SkyTraq (cala rodzina
chipsetow), nieudokumentowana w dostepnym AN0039 dla PX1122R - do potwierdzenia
na sprzecie. Wysyla tylko bajt trybu (bez opcjonalnej podpowiedzi UTC/pozycji -
patrz docstring Px1122rConfigClient.restart()). Jesli modul odpowie NACK zamiast
ACK, prawdopodobnie oczekuje dluzszego body - do uzupelnienia po potwierdzeniu
dokladnego ukladu pol.

Po restarcie moduł traci polaczenie na chwile (reinicjalizacja UART) - skrypt
tego nie sprawdza, tylko potwierdza ACK samej komendy.

Uzycie (na RPi, w .venv z extras 'navigation'):
    python rover/scripts/px1122r_restart_test.py base|rover hot|warm|cold|test
"""
from __future__ import annotations

import asyncio
import sys

from rover.common.config import load_service_config
from rover.services.navigation.gnss.px1122r_bus import Px1122rBus, Target
from rover.services.navigation.gnss.px1122r_config import (
    RESTART_COLD,
    RESTART_HOT,
    RESTART_TEST,
    RESTART_WARM,
    Px1122rConfigClient,
)

_MODES = {"hot": RESTART_HOT, "warm": RESTART_WARM, "cold": RESTART_COLD, "test": RESTART_TEST}


async def main() -> None:
    if len(sys.argv) < 3 or sys.argv[1] not in ("base", "rover") or sys.argv[2] not in _MODES:
        print(f"Uzycie: px1122r_restart_test.py base|rover {'|'.join(_MODES)}")
        sys.exit(1)

    target: Target = sys.argv[1]  # type: ignore[assignment]
    mode = _MODES[sys.argv[2]]

    args = load_service_config("navigation").driver_args
    bus = Px1122rBus(
        args.get("uart_port", "/dev/ttyAMA0"),
        args.get("baudrate", 115200),
        args.get("mux_select_gpio", 17),
    )
    await bus.start()
    client = Px1122rConfigClient(bus, target)
    try:
        print(f"[{target}] wysylam restart({sys.argv[2]})...")
        await client.restart(mode)
        print(f"[{target}] OK (ACK otrzymany) - modul powinien sie teraz restartowac")
    finally:
        await bus.stop()


if __name__ == "__main__":
    asyncio.run(main())
