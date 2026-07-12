from abc import ABC, abstractmethod

from rover.common.messages.nav import Pose


class NavigationProvider(ABC):
    @abstractmethod
    async def start(self) -> None: ...

    @abstractmethod
    async def stop(self) -> None: ...

    @abstractmethod
    async def read_pose(self) -> Pose: ...
