import time

from rover.common.messages.motion import DriveCommand, WheelStatus
from rover.services.motion_control.interface import MotorDriver


class MockMotorDriver(MotorDriver):
    async def start(self) -> None: ...

    async def stop(self) -> None: ...

    async def send_command(self, cmd: DriveCommand) -> None:
        print(f"[mock motion] {cmd}")

    async def read_status(self) -> WheelStatus:
        return WheelStatus(
            timestamp=time.time(),
            front_steer_deg=0.0,
            rear_steer_deg=0.0,
            wheel_speeds_kmh=(0.0, 0.0, 0.0, 0.0),
        )
