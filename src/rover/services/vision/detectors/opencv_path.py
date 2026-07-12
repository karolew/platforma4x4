from rover.common.messages.vision import PathOffset
from rover.services.vision.interface import PathDetector


class OpenCvPathDetector(PathDetector):
    def __init__(self, camera_index: int = 0, resolution: tuple[int, int] = (640, 480)) -> None:
        self._camera_index = camera_index
        self._resolution = resolution

    async def start(self) -> None:
        raise NotImplementedError  # otwarcie kamery (cv2.VideoCapture)

    async def stop(self) -> None:
        raise NotImplementedError

    async def detect(self) -> PathOffset:
        raise NotImplementedError  # segmentacja grządki, wyliczenie offsetu i confidence
