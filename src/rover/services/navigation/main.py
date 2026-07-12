import asyncio

from rover.common.config import load_service_config
from rover.common.mqtt_client import MqttBus
from rover.common.topics import NAV_POSE, topic
from rover.services.navigation.interface import NavigationProvider
from rover.services.navigation.providers.mock import MockNavigationProvider
from rover.services.navigation.providers.rtk_gnss import RtkGnssProvider

PROVIDERS: dict[str, type[NavigationProvider]] = {
    "rtk_gnss": RtkGnssProvider,
    "mock": MockNavigationProvider,
}


async def main() -> None:
    cfg = load_service_config("navigation")
    provider = PROVIDERS[cfg.driver](**cfg.driver_args)
    await provider.start()

    async with MqttBus(cfg.mqtt_host, cfg.mqtt_port, client_id="navigation") as bus:
        try:
            while True:
                pose = await provider.read_pose()
                await bus.publish(topic(cfg.rover_id, NAV_POSE), pose)
                await asyncio.sleep(0.1)
        finally:
            await provider.stop()


if __name__ == "__main__":
    asyncio.run(main())
