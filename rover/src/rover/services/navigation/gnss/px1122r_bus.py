"""Wspolny UART0 do obu PX1122R, przelaczany 74HC4053 (A/B/C zwarte na 1 pin
select GPIO17/pin11: 0=Rover, 1=Base). RPi pin 8 (TXD) -> wejscie Y, pin 10
(RXD) -> wejscie Z.

Normalna praca (RtkGnssProvider) trzyma select na Base na stale - przelaczanie na
Rover sluzy WYLACZNIE jednorazowej/on-demand konfiguracji (Px1122rConfigClient),
nigdy odczytowi danych w petli glownej.
"""
from __future__ import annotations

import asyncio
import os
from typing import Literal

# Wymuszone PRZED importem gpiozero: bez tego gpiozero probuje kolejno lgpio -> RPi.GPIO
# -> pigpio, konczac i tak na NativeFactory (dziala poprawnie dla prostego DigitalOutputDevice
# tutaj) - ale po drodze lgpio failuje z "xCreatePipe: Can't set permissions" (brak prawa
# zapisu pliku powiadomien .lgd-nfyN w biezacym katalogu roboczym, np. /opt/rover) i rzuca
# 3 ostrzezenia PinFactoryFallback. setdefault (nie nadpisuje), gdyby ktos chcial wymusic
# inny pin factory przez zmienna srodowiskowa.
os.environ.setdefault("GPIOZERO_PIN_FACTORY", "native")

import serial  # noqa: E402
from gpiozero import DigitalOutputDevice  # noqa: E402

Target = Literal["base", "rover"]


class Px1122rBus:
    def __init__(self, port: str, baudrate: int, mux_select_gpio: int) -> None:
        self._port_name = port
        self._baudrate = baudrate
        self._select_pin = DigitalOutputDevice(mux_select_gpio)
        self._serial: serial.Serial | None = None

    async def start(self) -> None:
        self._serial = await asyncio.to_thread(serial.Serial, self._port_name, self._baudrate, timeout=1)
        self.select_sync("base")

    async def stop(self) -> None:
        if self._serial is not None:
            await asyncio.to_thread(self._serial.close)
        self._select_pin.close()

    def select_sync(self, target: Target) -> None:
        if target == "base":
            self._select_pin.on()
        else:
            self._select_pin.off()

    async def select(self, target: Target) -> None:
        self.select_sync(target)
        await asyncio.sleep(0.01)  # czas ustabilizowania 74HC4053

    async def write(self, data: bytes) -> None:
        assert self._serial is not None
        await asyncio.to_thread(self._serial.write, data)

    async def read(self, size: int = 256) -> bytes:
        assert self._serial is not None
        return await asyncio.to_thread(self._serial.read, size)
