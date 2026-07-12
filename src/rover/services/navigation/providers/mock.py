import time

from rover.common.messages.nav import Pose
from rover.services.navigation.interface import NavigationProvider


class MockNavigationProvider(NavigationProvider):
    def __init__(self, **_kwargs: object) -> None: ...

    async def start(self) -> None: ...

    async def stop(self) -> None: ...

    async def read_pose(self) -> Pose:
        return Pose(timestamp=time.time(), lat=0.0, lon=0.0, heading_deg=0.0, speed_kmh=0.0, fix_type="none")
