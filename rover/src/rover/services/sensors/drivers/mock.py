import time

from rover.common.messages.sensors import CollisionEvent
from rover.services.sensors.interface import SensorDriver


class MockSensorDriver(SensorDriver):
    def __init__(self, **_kwargs: object) -> None: ...

    async def start(self) -> None: ...

    async def stop(self) -> None: ...

    async def read_collision(self) -> CollisionEvent:
        return CollisionEvent(timestamp=time.time(), triggered=False)
