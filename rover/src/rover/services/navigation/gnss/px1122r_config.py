"""Konfiguracja jednego PX1122R (Base albo Rover) przez wspolny Px1122rBus.

Uzywane WYLACZNIE poza normalna petla RtkGnssProvider - przy starcie albo na
zadanie. Kody komend (message ID) wg SkyTraq AN0039 - do uzupelnienia.
"""
from __future__ import annotations

import asyncio

from rover.services.navigation.gnss.px1122r_bus import Px1122rBus, Target
from rover.services.navigation.gnss.px1122r_protocol import decode_message, encode_message

_ACK = 0x83
_NACK = 0x84
_RATE_RESPONSE = 0x86

_MODE_MSG = 0x2E  # tryb pracy (differential mode)
_MODE_BASE = 0x02
_MODE_ROVER = 0x01
_MODE_RTCM_OFF = 0x00

_RTCM_MSG = 0x64  # wspolny z baseline (sub-id 0x21) - ogolna komenda "configure X"
_RTCM_1005_BASE_POSITION = 0x02
_RTCM_1074_GPS = 0x11
_RTCM_1084_GLONASS = 0x12
_RTCM_1094_GALILEO = 0x13
_RTCM_1124_BEIDOU = 0x14


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

    def _check_ack(self, msg_id: int, body: bytes) -> None:
        if msg_id == _NACK:
            raise RuntimeError(f"PX1122R NACK: {body!r}")
        if msg_id != _ACK:
            raise RuntimeError(f"nieoczekiwana odpowiedz (ID=0x{msg_id:02X}): {body!r}")

    async def _configure(self, msg_id: int, sub_id: int, save_to_flash: bool = True) -> None:
        resp_id, body = await self._request(msg_id, bytes([sub_id, int(save_to_flash)]))
        self._check_ack(resp_id, body)

    async def get_output_rate(self) -> int:
        msg_id, body = await self._request(0x10)  # AN0039: query position update rate
        if msg_id != _RATE_RESPONSE:
            raise RuntimeError(f"nieoczekiwana odpowiedz (ID=0x{msg_id:02X}): {body!r}")
        return body[0]

    async def set_output_rate(self, hz: int, save_to_flash: bool = True) -> None:
        # AN0039: rate_byte = wartosc Hz wprost (potwierdzone: 0x01/0x05/0x0A dla 1/5/10Hz)
        msg_id, body = await self._request(0x0E, bytes([hz, int(save_to_flash)]))
        self._check_ack(msg_id, body)

    async def get_baseline_m(self) -> float:
        raise NotImplementedError  # AN0039 (0x64/0x21 query) - brak przykladu ramki odpowiedzi

    async def set_baseline_m(self, meters: float, save_to_flash: bool = True) -> None:
        # AN0039: msg 0x64, sub-id 0x21, value = cm jako 16-bit big-endian (potwierdzone: 100cm/250cm)
        cm = round(meters * 100)
        body = bytes([0x21, int(save_to_flash)]) + cm.to_bytes(2, "big")
        msg_id, resp_body = await self._request(0x64, body)
        self._check_ack(msg_id, resp_body)

    async def configure_as_base(self) -> None:
        """AN0039: Moving Base - RTK base + RTCM 1005/1074/1084/1094/1124 @ 1Hz, zapis do flash."""
        await self._configure(_MODE_MSG, _MODE_BASE)
        for sub_id in (
            _RTCM_1005_BASE_POSITION,
            _RTCM_1074_GPS,
            _RTCM_1084_GLONASS,
            _RTCM_1094_GALILEO,
            _RTCM_1124_BEIDOU,
        ):
            await self._configure(_RTCM_MSG, sub_id)

    async def configure_as_rover(self) -> None:
        """AN0039: Rover - wylacza wysylanie poprawek RTCM."""
        await self._configure(_MODE_MSG, _MODE_ROVER)
        await self._configure(_MODE_MSG, _MODE_RTCM_OFF)
