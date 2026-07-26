import asyncio

from rover.common.config import load_service_config
from rover.common.messages.actuators import ServoCommand
from rover.common.mqtt_client import MqttBus
from rover.common.topics import ACTUATORS_SERVO_CMD, topic
from rover.services.actuators.drivers.mock import MockActuatorDriver
from rover.services.actuators.drivers.servo_can import ServoCanDriver
from rover.services.actuators.interface import ActuatorDriver

DRIVERS: dict[str, type[ActuatorDriver]] = {
    "servo_can": ServoCanDriver,
    "mock": MockActuatorDriver,
}


async def main() -> None:
    cfg = load_service_config("actuators")
    driver = DRIVERS[cfg.driver](**cfg.driver_args)
    await driver.start()

    async with MqttBus(cfg.mqtt_host, cfg.mqtt_port, client_id="actuators") as bus:
        try:
            async for cmd in bus.subscribe(topic(cfg.rover_id, ACTUATORS_SERVO_CMD), ServoCommand):
                await driver.set_position(cmd)
        finally:
            await driver.stop()


if __name__ == "__main__":
    asyncio.run(main())
