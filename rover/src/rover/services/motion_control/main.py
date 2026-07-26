import asyncio

from rover.common.config import load_service_config
from rover.common.messages.motion import DriveCommand
from rover.common.mqtt_client import MqttBus
from rover.common.topics import DECISION_DRIVE_CMD, MOTION_STATUS, topic
from rover.services.motion_control.drivers.mock import MockMotorDriver
from rover.services.motion_control.drivers.stm32_can import Stm32CanMotorDriver
from rover.services.motion_control.interface import MotorDriver

DRIVERS: dict[str, type[MotorDriver]] = {
    "stm32_can": Stm32CanMotorDriver,
    "mock": MockMotorDriver,
}


async def main() -> None:
    cfg = load_service_config("motion_control")
    driver = DRIVERS[cfg.driver](**cfg.driver_args)
    await driver.start()

    async with MqttBus(cfg.mqtt_host, cfg.mqtt_port, client_id="motion_control") as bus:

        async def consume_commands() -> None:
            async for cmd in bus.subscribe(topic(cfg.rover_id, DECISION_DRIVE_CMD), DriveCommand):
                await driver.send_command(cmd)

        async def publish_status() -> None:
            while True:
                status = await driver.read_status()
                await bus.publish(topic(cfg.rover_id, MOTION_STATUS), status)
                await asyncio.sleep(0.1)

        try:
            await asyncio.gather(consume_commands(), publish_status())
        finally:
            await driver.stop()


if __name__ == "__main__":
    asyncio.run(main())
