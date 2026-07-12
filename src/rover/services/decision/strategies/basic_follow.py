import time

from rover.common.messages.motion import DriveCommand
from rover.common.messages.nav import Pose
from rover.common.messages.sensors import CollisionEvent
from rover.common.messages.vision import PathOffset
from rover.services.decision.interface import DecisionStrategy


class BasicFollowStrategy(DecisionStrategy):
    def __init__(self, cruise_speed_kmh: float = 2.0, steer_gain: float = 1.0) -> None:
        self._cruise_speed_kmh = cruise_speed_kmh
        self._steer_gain = steer_gain

    def decide(
        self,
        pose: Pose | None,
        path_offset: PathOffset | None,
        collision: CollisionEvent | None,
    ) -> DriveCommand:
        if collision is not None and collision.triggered:
            return DriveCommand(timestamp=time.time(), linear_kmh=0.0, angular_radps=0.0)

        if path_offset is None or path_offset.path_end:
            return DriveCommand(timestamp=time.time(), linear_kmh=0.0, angular_radps=0.0)

        angular = -self._steer_gain * path_offset.offset_m
        return DriveCommand(timestamp=time.time(), linear_kmh=self._cruise_speed_kmh, angular_radps=angular)
