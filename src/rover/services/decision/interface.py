from abc import ABC, abstractmethod

from rover.common.messages.motion import DriveCommand
from rover.common.messages.nav import Pose
from rover.common.messages.sensors import CollisionEvent
from rover.common.messages.vision import PathOffset


class DecisionStrategy(ABC):
    @abstractmethod
    def decide(
        self,
        pose: Pose | None,
        path_offset: PathOffset | None,
        collision: CollisionEvent | None,
    ) -> DriveCommand: ...
