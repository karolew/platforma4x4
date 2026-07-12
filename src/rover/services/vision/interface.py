from abc import ABC, abstractmethod

from rover.common.messages.vision import PathOffset


class PathDetector(ABC):
    @abstractmethod
    async def start(self) -> None: ...

    @abstractmethod
    async def stop(self) -> None: ...

    @abstractmethod
    async def detect(self) -> PathOffset: ...
