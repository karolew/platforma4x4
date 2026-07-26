from abc import ABC, abstractmethod
from typing import AsyncIterator

from rover.common.messages.planner import Mission, Telemetry


class PlannerTransport(ABC):
    @abstractmethod
    async def connect(self) -> None: ...

    @abstractmethod
    async def disconnect(self) -> None: ...

    @abstractmethod
    async def send_telemetry(self, telemetry: Telemetry) -> None: ...

    @abstractmethod
    def receive_missions(self) -> AsyncIterator[Mission]: ...
