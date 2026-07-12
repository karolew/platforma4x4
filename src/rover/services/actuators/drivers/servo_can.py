import can

from rover.common.messages.actuators import ServoCommand
from rover.services.actuators.interface import ActuatorDriver


class ServoCanDriver(ActuatorDriver):
    """Każde serwo ma własny STM32; RPi wysyła pozycję po CAN (servo_id -> CAN ID sterownika)."""

    def __init__(self, channel: str = "can0", bitrate: int = 500000, can_id_map: dict[str, int] | None = None) -> None:
        self._channel = channel
        self._bitrate = bitrate
        self._can_id_map = can_id_map or {}
        self._bus: can.BusABC | None = None

    async def start(self) -> None:
        self._bus = can.interface.Bus(channel=self._channel, bustype="socketcan", bitrate=self._bitrate)

    async def stop(self) -> None:
        if self._bus is not None:
            self._bus.shutdown()

    async def set_position(self, cmd: ServoCommand) -> None:
        raise NotImplementedError  # encode position_deg -> ramka CAN do can_id_map[cmd.servo_id]
