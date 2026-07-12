from pydantic import BaseModel


class ServoCommand(BaseModel):
    timestamp: float
    servo_id: str
    position_deg: float
