from rover.common.messages.actuators import ServoCommand
from rover.services.actuators.interface import ActuatorDriver


class MockActuatorDriver(ActuatorDriver):
    def __init__(self, **_kwargs: object) -> None: ...

    async def start(self) -> None: ...

    async def stop(self) -> None: ...

    async def set_position(self, cmd: ServoCommand) -> None:
        print(f"[mock actuator] {cmd}")
