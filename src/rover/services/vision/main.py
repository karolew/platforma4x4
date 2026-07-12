import asyncio

from rover.common.config import load_service_config
from rover.common.mqtt_client import MqttBus
from rover.common.topics import VISION_PATH_OFFSET, topic
from rover.services.vision.detectors.mock import MockPathDetector
from rover.services.vision.detectors.opencv_path import OpenCvPathDetector
from rover.services.vision.interface import PathDetector

DETECTORS: dict[str, type[PathDetector]] = {
    "opencv_path": OpenCvPathDetector,
    "mock": MockPathDetector,
}


async def main() -> None:
    cfg = load_service_config("vision")
    detector = DETECTORS[cfg.driver](**cfg.driver_args)
    await detector.start()

    async with MqttBus(cfg.mqtt_host, cfg.mqtt_port, client_id="vision") as bus:
        try:
            while True:
                offset = await detector.detect()
                await bus.publish(topic(cfg.rover_id, VISION_PATH_OFFSET), offset)
                await asyncio.sleep(0.05)
        finally:
            await detector.stop()


if __name__ == "__main__":
    asyncio.run(main())
