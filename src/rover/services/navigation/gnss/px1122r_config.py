"""Konfiguracja jednego PX1122R (Base albo Rover) przez wspolny Px1122rBus.

Uzywane WYLACZNIE poza normalna petla RtkGnssProvider - przy starcie albo na
zadanie. Kody komend (message ID) wg SkyTraq AN0039 - do uzupelnienia.
"""
from __future__ import annotations

import asyncio

from rover.services.navigation.gnss.px1122r_bus import Px1122rBus, Target
from rover.services.navigation.gnss.px1122r_protocol import decode_message, encode_message


class Px1122rConfigClient:
    def __init__(self, bus: Px1122rBus, target: Target) -> None:
        self._bus = bus
        self._target = target
        self._lock = asyncio.Lock()

    async def _request(self, msg_id: int, body: bytes = b"", response_size: int = 256) -> tuple[int, bytes]:
        async with self._lock:
            await self._bus.select(self._target)
            await self._bus.write(encode_message(msg_id, body))
            frame = await self._bus.read(response_size)
            return decode_message(frame)

    async def get_output_rate(self) -> int:
        raise NotImplementedError  # message ID zapytania o output rate wg AN0039

    async def set_output_rate(self, hz: int) -> None:
        raise NotImplementedError  # message ID ustawienia rate (1-10Hz) wg AN0039

    async def get_baseline_m(self) -> float:
        raise NotImplementedError  # message ID odczytu dlugosci baseline (moving base)

    async def set_baseline_m(self, meters: float) -> None:
        raise NotImplementedError  # message ID zapisu dlugosci baseline

    async def get_message_rate(self, message: str) -> int:
        raise NotImplementedError  # message ID zapytania o rate danego komunikatu

    async def set_message_rate(self, message: str, hz: int) -> None:
        raise NotImplementedError  # message ID ustawienia rate danego komunikatu
