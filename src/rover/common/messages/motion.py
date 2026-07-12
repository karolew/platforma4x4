from pydantic import BaseModel


class DriveCommand(BaseModel):
    timestamp: float
    linear_kmh: float
    angular_radps: float


class WheelStatus(BaseModel):
    timestamp: float
    front_steer_deg: float
    rear_steer_deg: float
    wheel_speeds_kmh: tuple[float, float, float, float]
    fault: str | None = None
