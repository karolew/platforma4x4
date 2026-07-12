"""Wspolny UART0 do obu PX1122R, przelaczany CD4052 (1 pin select: 0=Base, 1=Rover).

Normalna praca (RtkGnssProvider) trzyma select na Base na stale - przelaczanie na
Rover sluzy WYLACZNIE jednorazowej/on-demand konfiguracji (Px1122rConfigClient),
nigdy odczytowi danych w petli glownej.
"""
from __future__ import annotations

import asyncio
from typing import Literal

import serial
from gpiozero import DigitalOutputDevice

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
            self._select_pin.off()
        else:
            self._select_pin.on()

    async def select(self, target: Target) -> None:
        self.select_sync(target)
        await asyncio.sleep(0.01)  # czas ustabilizowania CD4052

    async def write(self, data: bytes) -> None:
        assert self._serial is not None
        await asyncio.to_thread(self._serial.write, data)

    async def read(self, size: int = 256) -> bytes:
        assert self._serial is not None
        return await asyncio.to_thread(self._serial.read, size)
