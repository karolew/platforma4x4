"""Reczny test configure_rtk_mode()/query_rtk_mode() (0x6A) na PX1122R.

Znalezione w AN0028 (SkyTraq Venus 8) jako "CONFIGURE RTK MODE AND OPERATIONAL
FUNCTION" - nieudokumentowane wprost dla PX1122R (inny chipset), do potwierdzenia
na sprzecie. To potencjalnie prawdziwy zastepnik dla wczesniej odrzuconych (NACK)
prob 0x64/0x21 i 0x6E - baseline jest tu polem WEWNATRZ tej samej komendy, nie
osobna komenda, uzywanym gdy Rover ma operational_function=moving-base.

Uzycie (na RPi, w .venv z extras 'navigation'):
    python rover/scripts/px1122r_rtk_mode_test.py base|rover query
    python rover/scripts/px1122r_rtk_mode_test.py rover moving-base <baseline_m>
    python rover/scripts/px1122r_rtk_mode_test.py rover normal|float
    python rover/scripts/px1122r_rtk_mode_test.py base kinematic|survey|static
    python rover/scripts/px1122r_rtk_mode_test.py base precise-normal|precise-float

Nazewnictwo "precise-*" odpowiada trybowi RTK_MODE_PRECISE_KINEMATIC_BASE (mode=2)
z datasheetu PX1122R - "Precisely Kinematic Mode Base" w parze z "Moving Base Mode
Rover" (rover moving-base) w konfiguracji Advanced Moving Base.
"""
from __future__ import annotations

import asyncio
import sys

from rover.common.config import load_service_config
from rover.services.navigation.gnss.px1122r_bus import Px1122rBus, Target
from rover.services.navigation.gnss.px1122r_config import (
    RTK_MODE_BASE,
    RTK_MODE_PRECISE_KINEMATIC_BASE,
    RTK_MODE_ROVER,
    Px1122rConfigClient,
)

_ROVER_FUNCS = {"normal": 0, "float": 1, "moving-base": 2}
_BASE_FUNCS = {"kinematic": 0, "survey": 1, "static": 2}
_PRECISE_BASE_FUNCS = {"precise-normal": 0, "precise-float": 1}


async def main() -> None:
    if len(sys.argv) < 3 or sys.argv[1] not in ("base", "rover"):
        print(
            "Uzycie: px1122r_rtk_mode_test.py base|rover "
            "query|normal|float|moving-base|kinematic|survey|static|precise-normal|precise-float [baseline_m]"
        )
        sys.exit(1)

    target: Target = sys.argv[1]  # type: ignore[assignment]
    action = sys.argv[2]

    args = load_service_config("navigation").driver_args
    bus = Px1122rBus(
        args.get("uart_port", "/dev/ttyAMA0"),
        args.get("baudrate", 115200),
        args.get("mux_select_gpio", 17),
    )
    await bus.start()
    client = Px1122rConfigClient(bus, target)
    try:
        if action == "query":
            mode, func, baseline_m = await client.query_rtk_mode()
            print(f"[{target}] RTK mode={mode} operational_function={func} baseline_length_m={baseline_m}")
            return

        baseline_m = float(sys.argv[3]) if len(sys.argv) > 3 else 0.0

        if action in _ROVER_FUNCS:
            print(f"[{target}] ustawiam Rover, function={action}, baseline={baseline_m}m...")
            await client.configure_rtk_mode(RTK_MODE_ROVER, _ROVER_FUNCS[action], baseline_length_m=baseline_m)
        elif action in _BASE_FUNCS:
            print(f"[{target}] ustawiam Base, function={action}, baseline={baseline_m}m...")
            await client.configure_rtk_mode(RTK_MODE_BASE, _BASE_FUNCS[action], baseline_length_m=baseline_m)
        elif action in _PRECISE_BASE_FUNCS:
            print(f"[{target}] ustawiam Precisely Kinematic Base, function={action}, baseline={baseline_m}m...")
            await client.configure_rtk_mode(
                RTK_MODE_PRECISE_KINEMATIC_BASE, _PRECISE_BASE_FUNCS[action], baseline_length_m=baseline_m
            )
        else:
            print(f"Nieznana akcja: {action}")
            sys.exit(1)

        print(f"[{target}] OK (ACK otrzymany)")
        mode, func, baseline_m = await client.query_rtk_mode()
        print(f"[{target}] po zmianie: mode={mode} function={func} baseline_length_m={baseline_m}")
    finally:
        await bus.stop()


if __name__ == "__main__":
    asyncio.run(main())
