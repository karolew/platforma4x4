from pydantic import BaseModel


class CollisionEvent(BaseModel):
    timestamp: float
    triggered: bool
    distance_m: float | None = None
