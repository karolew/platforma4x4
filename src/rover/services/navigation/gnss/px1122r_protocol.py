"""Ramkowanie SkyTraq binary protocol (AN0039), uzywane przez PX1122R do konfiguracji."""
from __future__ import annotations

START = b"\xa0\xa1"
END = b"\x0d\x0a"


class FrameError(Exception):
    pass


def _checksum(payload: bytes) -> int:
    cs = 0
    for b in payload:
        cs ^= b
    return cs


def encode_message(msg_id: int, body: bytes = b"") -> bytes:
    payload = bytes([msg_id]) + body
    return START + len(payload).to_bytes(2, "big") + payload + bytes([_checksum(payload)]) + END


def decode_message(frame: bytes) -> tuple[int, bytes]:
    """Zwraca (msg_id, body). Zaklada ze `frame` to jedna pelna ramka START..END."""
    if frame[:2] != START or frame[-2:] != END:
        raise FrameError(f"brak START/END w ramce: {frame!r}")
    length = int.from_bytes(frame[2:4], "big")
    payload = frame[4 : 4 + length]
    checksum = frame[4 + length]
    if _checksum(payload) != checksum:
        raise FrameError(f"zla suma kontrolna: {frame!r}")
    return payload[0], payload[1:]
