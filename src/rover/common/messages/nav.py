from pydantic import BaseModel


class Pose(BaseModel):
    timestamp: float
    lat: float
    lon: float
    heading_deg: float
    speed_kmh: float
    fix_type: str  # "none" | "rtk_float" | "rtk_fixed"
