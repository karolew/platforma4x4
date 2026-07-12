from pydantic import BaseModel


class PathOffset(BaseModel):
    timestamp: float
    offset_m: float
    confidence: float
    path_end: bool
