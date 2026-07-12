from abc import ABC, abstractmethod

from rover.common.messages.motion import DriveCommand, WheelStatus


class MotorDriver(ABC):
    @abstractmethod
    async def start(self) -> None: ...

    @abstractmethod
    async def stop(self) -> None: ...

    @abstractmethod
    async def send_command(self, cmd: DriveCommand) -> None: ...

    @abstractmethod
    async def read_status(self) -> WheelStatus: ...
