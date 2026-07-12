import asyncio

from rover.common.config import load_service_config
from rover.common.messages.nav import Pose
from rover.common.messages.planner import Telemetry
from rover.common.mqtt_client import MqttBus
from rover.common.topics import NAV_POSE, PLANNER_MISSION, PLANNER_TELEMETRY, topic
from rover.services.planner_link.interface import PlannerTransport
from rover.services.planner_link.transports.rest_ws import RestWsPlannerTransport

TRANSPORTS: dict[str, type[PlannerTransport]] = {
    "rest_ws": RestWsPlannerTransport,
}


async def main() -> None:
    cfg = load_service_config("planner_link")
    transport = TRANSPORTS[cfg.driver](rover_id=cfg.rover_id, **cfg.driver_args)
    await transport.connect()

    latest_pose: Pose | None = None

    async with MqttBus(cfg.mqtt_host, cfg.mqtt_port, client_id="planner_link") as bus:

        async def track_pose() -> None:
            nonlocal latest_pose
            async for pose in bus.subscribe(topic(cfg.rover_id, NAV_POSE), Pose):
                latest_pose = pose

        async def uplink_telemetry() -> None:
            while True:
                telemetry = Telemetry(
                    timestamp=asyncio.get_event_loop().time(),
                    lat=latest_pose.lat if latest_pose else None,
                    lon=latest_pose.lon if latest_pose else None,
                    status="running",
                )
                await transport.send_telemetry(telemetry)
                await asyncio.sleep(1.0)

        async def downlink_missions() -> None:
            async for mission in transport.receive_missions():
                await bus.publish(topic(cfg.rover_id, PLANNER_MISSION), mission)

        try:
            await asyncio.gather(track_pose(), uplink_telemetry(), downlink_missions())
        finally:
            await transport.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
