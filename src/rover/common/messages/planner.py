from pydantic import BaseModel


class Waypoint(BaseModel):
    lat: float
    lon: float


class Mission(BaseModel):
    mission_id: str
    waypoints: list[Waypoint]


class Telemetry(BaseModel):
    timestamp: float
    lat: float | None = None
    lon: float | None = None
    battery_pct: float | None = None
    status: str = "idle"
