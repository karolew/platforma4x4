from abc import ABC, abstractmethod

from rover.common.messages.actuators import ServoCommand


class ActuatorDriver(ABC):
    @abstractmethod
    async def start(self) -> None: ...

    @abstractmethod
    async def stop(self) -> None: ...

    @abstractmethod
    async def set_position(self, cmd: ServoCommand) -> None: ...
