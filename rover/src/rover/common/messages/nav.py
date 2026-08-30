from __future__ import annotations

from pydantic import BaseModel


class Pose(BaseModel):
    timestamp: float
    lat: float
    lon: float
    heading_deg: float | None  # None = brak aktualnie wiarygodnego heading (nie zgadujemy dla robota autonomicznego)
    elevation_deg: float | None  # kat elewacji baseline PSTI,035 (pitch/roll wg osi montazu anten); None = jak wyzej
    speed_kmh: float
    fix_type: str  # GGA quality string - patrz nmea_parser_lite.QUALITY ("Fix Unavailable".."Simulator Mode")
