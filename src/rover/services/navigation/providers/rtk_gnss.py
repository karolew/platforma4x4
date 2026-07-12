from rover.common.messages.nav import Pose
from rover.services.navigation.interface import NavigationProvider


class RtkGnssProvider(NavigationProvider):
    """Odbiornik GNSS RTK + poprawki NTRIP (Virtual Base Station) po serial/UART."""

    def __init__(self, port: str = "/dev/ttyACM0", baudrate: int = 460800, ntrip_url: str = "") -> None:
        self._port = port
        self._baudrate = baudrate
        self._ntrip_url = ntrip_url

    async def start(self) -> None:
        raise NotImplementedError  # otwarcie portu + start klienta NTRIP przesyłającego RTCM do odbiornika

    async def stop(self) -> None:
        raise NotImplementedError

    async def read_pose(self) -> Pose:
        raise NotImplementedError  # parsowanie NMEA/UBX -> Pose
