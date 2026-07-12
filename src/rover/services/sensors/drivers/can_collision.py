import can

from rover.common.messages.sensors import CollisionEvent
from rover.services.sensors.interface import SensorDriver


class CanCollisionSensor(SensorDriver):
    def __init__(self, channel: str = "can0", bitrate: int = 500000) -> None:
        self._channel = channel
        self._bitrate = bitrate
        self._bus: can.BusABC | None = None

    async def start(self) -> None:
        self._bus = can.interface.Bus(channel=self._channel, bustype="socketcan", bitrate=self._bitrate)

    async def stop(self) -> None:
        if self._bus is not None:
            self._bus.shutdown()

    async def read_collision(self) -> CollisionEvent:
        raise NotImplementedError  # odczyt i dekodowanie ramki CAN z modułu kolizji STM32
