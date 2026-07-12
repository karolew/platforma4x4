import asyncio

from rover.common.config import load_service_config
from rover.common.messages.nav import Pose
from rover.common.messages.sensors import CollisionEvent
from rover.common.messages.vision import PathOffset
from rover.common.mqtt_client import MqttBus
from rover.common.topics import DECISION_DRIVE_CMD, NAV_POSE, SENSORS_COLLISION, VISION_PATH_OFFSET, topic
from rover.services.decision.interface import DecisionStrategy
from rover.services.decision.strategies.basic_follow import BasicFollowStrategy

STRATEGIES: dict[str, type[DecisionStrategy]] = {
    "basic_follow": BasicFollowStrategy,
}


class _State:
    pose: Pose | None = None
    path_offset: PathOffset | None = None
    collision: CollisionEvent | None = None


async def main() -> None:
    cfg = load_service_config("decision")
    strategy = STRATEGIES[cfg.driver](**cfg.driver_args)
    state = _State()

    async with MqttBus(cfg.mqtt_host, cfg.mqtt_port, client_id="decision") as bus:

        async def track_pose() -> None:
            async for pose in bus.subscribe(topic(cfg.rover_id, NAV_POSE), Pose):
                state.pose = pose

        async def track_vision() -> None:
            async for offset in bus.subscribe(topic(cfg.rover_id, VISION_PATH_OFFSET), PathOffset):
                state.path_offset = offset

        async def track_collision() -> None:
            async for event in bus.subscribe(topic(cfg.rover_id, SENSORS_COLLISION), CollisionEvent):
                state.collision = event

        async def publish_decision() -> None:
            while True:
                cmd = strategy.decide(state.pose, state.path_offset, state.collision)
                await bus.publish(topic(cfg.rover_id, DECISION_DRIVE_CMD), cmd)
                await asyncio.sleep(0.1)

        await asyncio.gather(track_pose(), track_vision(), track_collision(), publish_decision())


if __name__ == "__main__":
    asyncio.run(main())
