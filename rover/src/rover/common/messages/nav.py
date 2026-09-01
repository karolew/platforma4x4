from __future__ import annotations

from pydantic import BaseModel


class Pose(BaseModel):
    timestamp: float
    lat: float
    lon: float
    heading_deg: float | None  # None = brak aktualnie wiarygodnego heading (nie zgadujemy dla robota autonomicznego)
    elevation_deg: float | None  # kat elewacji baseline PSTI,035 (pitch/roll wg osi montazu anten); None = jak wyzej
    speed_kmh: float
    course_deg: float | None = None  # kurs nad ziemia (COG, VTG) - inny wektor niz heading anten
    alt_msl_m: float | None = None  # wysokosc nad poziomem morza (GGA)
    baseline_e_m: float | None = None  # PSTI,035 E: pozycja anteny Rover wzgledem Base (moving-base baseline)
    baseline_n_m: float | None = None  # PSTI,035 N: jak wyzej
    fix_type: str  # GGA quality string - patrz nmea_parser_lite.QUALITY ("Fix Unavailable".."Simulator Mode")
