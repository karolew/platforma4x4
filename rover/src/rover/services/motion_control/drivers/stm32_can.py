import can

from rover.common.messages.motion import DriveCommand, WheelStatus
from rover.services.motion_control.interface import MotorDriver


class Stm32CanMotorDriver(MotorDriver):
    def __init__(self, channel: str = "can0", bitrate: int = 500000) -> None:
        self._channel = channel
        self._bitrate = bitrate
        self._bus: can.BusABC | None = None

    async def start(self) -> None:
        self._bus = can.interface.Bus(channel=self._channel, bustype="socketcan", bitrate=self._bitrate)

    async def stop(self) -> None:
        if self._bus is not None:
            self._bus.shutdown()

    async def send_command(self, cmd: DriveCommand) -> None:
        raise NotImplementedError  # encode wg protokolu CAN uzgodnionego z STM32

    async def read_status(self) -> WheelStatus:
        raise NotImplementedError  # dekodowanie ramki feedback z STM32
