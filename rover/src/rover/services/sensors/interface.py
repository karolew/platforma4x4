from abc import ABC, abstractmethod

from rover.common.messages.sensors import CollisionEvent


class SensorDriver(ABC):
    @abstractmethod
    async def start(self) -> None: ...

    @abstractmethod
    async def stop(self) -> None: ...

    @abstractmethod
    async def read_collision(self) -> CollisionEvent: ...
