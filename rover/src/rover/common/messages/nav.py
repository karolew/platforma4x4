from __future__ import annotations

from pydantic import BaseModel


class Pose(BaseModel):
    timestamp: float
    lat: float
    lon: float
    heading_deg: float | None  # None = brak aktualnie wiarygodnego heading (nie zgadujemy dla robota autonomicznego)
    speed_kmh: float
    fix_type: str  # GGA quality string - patrz nmea_parser_lite.QUALITY ("Fix Unavailable".."Simulator Mode")
