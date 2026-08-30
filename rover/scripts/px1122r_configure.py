"""Uniwersalny skrypt konfiguracyjny PX1122R.

px1122r_rtk_mode_test.py NIE jest tu zastapiony i nadal istnieje osobno - obsluguje
kombinacje trybu/funkcji RTK spoza zakresu ponizszego (`rover normal|float`,
`base kinematic|survey|static`, `precise-normal|precise-float`), ktorych ten skrypt
celowo nie powiela (ponizej sa tylko `rtk advanced-base` i `rtk rover baseline=`, czyli
dokladnie to, co faktycznie uzywa "Advanced Moving Base" configu tego projektu).

Uzycie (na RPi, w .venv z extras 'navigation'):
    python px1122r_configure.py base|rover get rtk config
    python px1122r_configure.py base|rover get rtk slave-serial
    python px1122r_configure.py base|rover get rtk base-serial
    python px1122r_configure.py base|rover set rtk slave-serial baud=115200
    python px1122r_configure.py base|rover set rtk base-serial baud=115200
    python px1122r_configure.py base|rover set rtk advanced-base
    python px1122r_configure.py base|rover set rtk rover baseline=1.2
    python px1122r_configure.py base|rover get sw
    python px1122r_configure.py base|rover get update-rate
    python px1122r_configure.py base|rover get power-mode
    python px1122r_configure.py base|rover set power-mode=normal|power-save
    python px1122r_configure.py base|rover set serial baud=115200 [--save]
    python px1122r_configure.py base|rover set reset=hot|warm|cold|test
    python px1122r_configure.py base|rover set update-rate=2 [--save]
    python px1122r_configure.py base|rover get serial detect

`--save` ma znaczenie TYLKO dla `set serial` i `set update-rate` (domyslnie
save_to_flash=False, jak w usunietych px1122r_baudrate_test.py/px1122r_rate_test.py -
te komendy nie sa czescia "Advanced Moving Base" configu i bezpieczniej nie pisac ich
od razu do FLASH). Wszystkie pozostale `set` (rtk advanced-base/rover/slave-serial/
base-serial, power-mode) replikuja 1:1 komendy z GNSS Viewer, ktory wg naglowka
komendy_z_gnss_viewer.txt zawsze zapisuje do SRAM+FLASH - wiec dla nich save_to_flash
jest zawsze True, `--save` nie ma tam znaczenia. `get serial detect` nie dotyczy
save_to_flash (tylko odczyt).

ZAKRES `rtk slave-serial` vs `rtk base-serial` (wg NS-HP-GN2-User-Guide.pdf, cytat
2026-08-26 - wymagane przy advanced moving base >=4Hz): `slave-serial` konfiguruje
"receiver C moving base rover RXD2 UART" - dotyczy WYLACZNIE Rovera, uruchamiaj tylko
z `rover` (dlatego przyklad wyzej juz nie pokazuje `base|rover`). `base-serial`
konfiguruje "receiver B & C I2C mapped UART" - trzeba wyslac do OBU jednostek osobno
(`base` i `rover`), bo obie strony linku musza miec zgodny baudrate. Trzeci element z
dokumentacji, glowny UART TXD Base, to zwykle `set serial baud=` (0x05) - w tym
projekcie juz potwierdzony na 460800 (>=230400 wymagane), wiec zwykle nie trzeba go
ruszac.
"""
from __future__ import annotations

import asyncio
import sys

from rover.common.config import load_service_config
from rover.services.navigation.gnss.px1122r_bus import Px1122rBus, Target
from rover.services.navigation.gnss.px1122r_config import (
    _BAUD_RATE_IDS,
    POWER_MODE_NORMAL,
    POWER_MODE_SAVE,
    RESTART_COLD,
    RESTART_HOT,
    RESTART_TEST,
    RESTART_WARM,
    Px1122rConfigClient,
)

_RESET_MODES = {"hot": RESTART_HOT, "warm": RESTART_WARM, "cold": RESTART_COLD, "test": RESTART_TEST}
_POWER_MODES = {"normal": POWER_MODE_NORMAL, "power-save": POWER_MODE_SAVE}
_DETECT_QUERY_TIMEOUT_S = 2.0  # przy zlym baudrate _read_frame() moze dlugo nie znalezc START w szumie


def _usage() -> None:
    print(__doc__)
    sys.exit(1)


def _parse_tokens(tokens: list[str]) -> tuple[list[str], dict[str, str]]:
    """Dzieli tokeny CLI na 'subjecty' (slowa bez '=', np. 'rtk', 'advanced-base') i
    pary klucz=wartosc (np. 'baud=115200', 'reset=hot') - niezaleznie od tego, czy
    komenda uzywa formy pozycyjnej czy key=value."""
    subjects: list[str] = []
    kv: dict[str, str] = {}
    for tok in tokens:
        if tok == "--save":
            continue
        if "=" in tok:
            key, _, value = tok.partition("=")
            kv[key.lower()] = value
        else:
            subjects.append(tok.lower())
    return subjects, kv


def _baud_value(kv: dict[str, str]) -> int:
    if "baud" in kv:
        return int(kv["baud"])
    raise SystemExit("brak baud=<wartosc>")


async def _dispatch(
    client: Px1122rConfigClient,
    target: Target,
    action: str,
    subjects: list[str],
    kv: dict[str, str],
    save: bool,
) -> None:
    if action == "get" and subjects == ["rtk", "config"]:
        mode, func, baseline_m = await client.query_rtk_mode()
        print(f"[{target}] rtk config: mode={mode} operational_function={func} baseline_length_m={baseline_m}")

    elif action == "get" and subjects == ["rtk", "slave-serial"]:
        body = await client.get_slave_serial_baud()
        print(f"[{target}] rtk slave-serial (raw body, uklad niepotwierdzony): {body.hex(' ')}")

    elif action == "get" and subjects == ["rtk", "base-serial"]:
        body = await client.get_base_serial_baud()
        print(f"[{target}] rtk base-serial (raw body, uklad niepotwierdzony): {body.hex(' ')}")

    elif action == "set" and subjects == ["rtk", "slave-serial"]:
        baud = _baud_value(kv)
        await client.set_slave_serial_baud(baud)
        print(f"[{target}] rtk slave-serial baud={baud} OK (ACK)")

    elif action == "set" and subjects == ["rtk", "base-serial"]:
        baud = _baud_value(kv)
        await client.set_base_serial_baud(baud)
        print(f"[{target}] rtk base-serial baud={baud} OK (ACK)")

    elif action == "set" and subjects == ["rtk", "advanced-base"]:
        await client.configure_as_base()
        print(f"[{target}] rtk advanced-base (Precisely Kinematic Base) OK (ACK)")

    elif action == "set" and subjects == ["rtk", "rover"]:
        baseline_m = float(kv.get("baseline", "0.0"))
        await client.configure_as_rover(baseline_m)
        print(f"[{target}] rtk rover moving-base baseline={baseline_m}m OK (ACK)")

    elif action == "get" and subjects == ["sw"]:
        version_body, crc_body = await client.get_sw()
        print(f"[{target}] sw version (raw): {version_body.hex(' ')}")
        print(f"[{target}] sw crc (raw): {crc_body.hex(' ')}")

    elif action == "get" and subjects == ["update-rate"]:
        rate = await client.get_output_rate()
        print(f"[{target}] update-rate: {rate}Hz")

    elif action == "set" and "update-rate" in kv:
        hz = int(kv["update-rate"])
        await client.set_output_rate(hz, save_to_flash=save)
        print(f"[{target}] update-rate ustawiony na {hz}Hz (save_to_flash={save})")

    elif action == "get" and subjects == ["power-mode"]:
        body = await client.get_power_mode()
        print(f"[{target}] power-mode (raw body, uklad niepotwierdzony): {body.hex(' ')}")

    elif action == "set" and "power-mode" in kv:
        mode_name = kv["power-mode"]
        if mode_name not in _POWER_MODES:
            raise SystemExit(f"nieznany power-mode: {mode_name} (normal|power-save)")
        await client.set_power_mode(_POWER_MODES[mode_name])
        print(f"[{target}] power-mode={mode_name} OK (ACK)")

    elif action == "set" and subjects == ["serial"]:
        baud = _baud_value(kv)
        await client.set_baudrate(baud, save_to_flash=save)
        print(f"[{target}] serial baud={baud} OK (ACK, save_to_flash={save}) - UART hosta zmieniony")

    elif action == "set" and "reset" in kv:
        mode_name = kv["reset"]
        if mode_name not in _RESET_MODES:
            raise SystemExit(f"nieznany reset: {mode_name} (hot|warm|cold|test)")
        await client.restart(_RESET_MODES[mode_name])
        print(f"[{target}] reset={mode_name} wyslany (ACK)")

    else:
        _usage()


async def _detect_baud(target: Target, uart_port: str, mux_select_gpio: int) -> None:
    """Probuje kolejno wszystkie standardowe baudraty i sprawdza, na ktorym modul
    odpowiada na get_output_rate() - protokol SkyTraq nie ma komendy 'query baud rate'
    dla glownego portu (potwierdzone brakiem takiej pozycji w menu GNSS Viewer), wiec to
    jedyny sposob 'odczytania' aktualnego baudrate hosta."""
    print(f"[{target}] szukam aktywnego baudrate (do {_DETECT_QUERY_TIMEOUT_S}s na probe)...")
    for baud in sorted(_BAUD_RATE_IDS):
        bus = Px1122rBus(uart_port, baud, mux_select_gpio)
        await bus.start()
        try:
            client = Px1122rConfigClient(bus, target)
            rate = await asyncio.wait_for(client.get_output_rate(), timeout=_DETECT_QUERY_TIMEOUT_S)
            print(f"[{target}] {baud}: OK, modul odpowiada (output rate={rate}Hz)")
        except Exception:
            print(f"[{target}] {baud}: brak odpowiedzi")
        finally:
            await bus.stop()


async def main() -> None:
    if len(sys.argv) < 4 or sys.argv[1] not in ("base", "rover") or sys.argv[2] not in ("get", "set"):
        _usage()

    target: Target = sys.argv[1]  # type: ignore[assignment]
    action = sys.argv[2]
    rest = sys.argv[3:]
    save = "--save" in rest
    subjects, kv = _parse_tokens(rest)

    args = load_service_config("navigation").driver_args
    uart_port = args.get("uart_port", "/dev/ttyAMA0")
    mux_select_gpio = args.get("mux_select_gpio", 17)

    if action == "get" and subjects == ["serial", "detect"]:
        await _detect_baud(target, uart_port, mux_select_gpio)
        return

    bus = Px1122rBus(uart_port, args.get("baudrate", 115200), mux_select_gpio)
    await bus.start()
    client = Px1122rConfigClient(bus, target)
    try:
        await _dispatch(client, target, action, subjects, kv, save)
    finally:
        await bus.stop()


if __name__ == "__main__":
    asyncio.run(main())
