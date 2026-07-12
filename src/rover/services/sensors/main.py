import asyncio

from rover.common.config import load_service_config
from rover.common.mqtt_client import MqttBus
from rover.common.topics import SENSORS_COLLISION, topic
from rover.services.sensors.drivers.can_collision import CanCollisionSensor
from rover.services.sensors.drivers.mock import MockSensorDriver
from rover.services.sensors.interface import SensorDriver

DRIVERS: dict[str, type[SensorDriver]] = {
    "can_collision": CanCollisionSensor,
    "mock": MockSensorDriver,
}


async def main() -> None:
    cfg = load_service_config("sensors")
    driver = DRIVERS[cfg.driver](**cfg.driver_args)
    await driver.start()

    async with MqttBus(cfg.mqtt_host, cfg.mqtt_port, client_id="sensors") as bus:
        try:
            while True:
                event = await driver.read_collision()
                await bus.publish(topic(cfg.rover_id, SENSORS_COLLISION), event)
                await asyncio.sleep(0.05)
        finally:
            await driver.stop()


if __name__ == "__main__":
    asyncio.run(main())
