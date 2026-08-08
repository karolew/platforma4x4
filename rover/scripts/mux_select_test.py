"""Reczny test linii select 74HC4053 (GPIO17 / pin 11) bez reszty systemu.

UART0 RPi (pin 8 TXD -> wejscie Y, pin 10 RXD -> wejscie Z) przelaczany
wspolnym select A/B/C 74HC4053 zwartym na jeden GPIO17: 0=Rover, 1=Base
(zgodnie z px1122r_bus.py:select_sync() - base=on()/HIGH, rover=off()/LOW).

Uzycie (na RPi, w .venv z extras 'navigation'):
    python rover/scripts/mux_select_test.py base       # ustaw i przytrzymaj Base (high)
    python rover/scripts/mux_select_test.py rover       # ustaw i przytrzymaj Rover (low)
    python rover/scripts/mux_select_test.py toggle       # przelaczaj co 2s (Ctrl+C konczy)

Podczas trzymania stanu zmierz multimetrem/oscyloskopem GPIO17 oraz wyjscia
Y/Z 74HC4053, albo obserwuj ktory PX1122R odpowiada na dane z UART.
"""
from __future__ import annotations

import sys
import time

from gpiozero import DigitalOutputDevice

MUX_SELECT_GPIO = 17


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "toggle"
    pin = DigitalOutputDevice(MUX_SELECT_GPIO)
    try:
        if mode == "base":
            pin.on()
            print(f"GPIO{MUX_SELECT_GPIO} = HIGH (Base). Ctrl+C aby zakonczyc.")
            _hold()
        elif mode == "rover":
            pin.off()
            print(f"GPIO{MUX_SELECT_GPIO} = LOW (Rover). Ctrl+C aby zakonczyc.")
            _hold()
        elif mode == "toggle":
            print(f"Przelaczanie GPIO{MUX_SELECT_GPIO} co 2s (Base/Rover). Ctrl+C aby zakonczyc.")
            state = False
            while True:
                pin.value = state
                print("Base (HIGH)" if state else "Rover (LOW)")
                state = not state
                time.sleep(2)
        else:
            print(f"Nieznany tryb: {mode!r}. Uzyj: base | rover | toggle")
            sys.exit(1)
    except KeyboardInterrupt:
        pass
    finally:
        pin.close()


def _hold() -> None:
    while True:
        time.sleep(3600)


if __name__ == "__main__":
    main()
