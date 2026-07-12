import time

from rover.common.messages.vision import PathOffset
from rover.services.vision.interface import PathDetector


class MockPathDetector(PathDetector):
    async def start(self) -> None: ...

    async def stop(self) -> None: ...

    async def detect(self) -> PathOffset:
        return PathOffset(timestamp=time.time(), offset_m=0.0, confidence=1.0, path_end=False)
