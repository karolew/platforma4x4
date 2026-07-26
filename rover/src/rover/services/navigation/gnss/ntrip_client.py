"""Klient NTRIP (Virtual Base Station, np. asgeupos.pl) - pobiera strumien RTCM3."""
from __future__ import annotations

import asyncio
import base64


class NtripError(ConnectionError):
    pass


class NtripClient:
    def __init__(self, host: str, port: int, mountpoint: str, user: str, password: str) -> None:
        self._host = host
        self._port = port
        self._mountpoint = mountpoint
        self._user = user
        self._password = password
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None

    async def connect(self) -> None:
        self._reader, self._writer = await asyncio.open_connection(self._host, self._port)
        auth = base64.b64encode(f"{self._user}:{self._password}".encode()).decode()
        request = (
            f"GET /{self._mountpoint} HTTP/1.1\r\n"
            f"Host: {self._host}\r\n"
            f"Ntrip-Version: Ntrip/2.0\r\n"
            f"User-Agent: NTRIP platforma4x4-rover/1.0\r\n"
            f"Authorization: Basic {auth}\r\n"
            f"Connection: close\r\n\r\n"
        )
        self._writer.write(request.encode())
        await self._writer.drain()

        status_line = await self._reader.readline()
        if b"200" not in status_line:
            raise NtripError(f"nieoczekiwana odpowiedz kastera: {status_line!r}")
        while True:
            line = await self._reader.readline()
            if line in (b"\r\n", b""):
                break  # koniec naglowkow HTTP, dalej leci surowy RTCM

    async def close(self) -> None:
        if self._writer is not None:
            self._writer.close()

    async def read_rtcm(self, size: int = 1024) -> bytes:
        assert self._reader is not None
        return await self._reader.read(size)

    async def send_gga(self, sentence: str) -> None:
        assert self._writer is not None
        self._writer.write((sentence.strip() + "\r\n").encode("ascii"))
        await self._writer.drain()
