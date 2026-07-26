def topic(rover_id: str, suffix: str) -> str:
    return f"rover/{rover_id}/{suffix}"


NAV_POSE = "nav/pose"
VISION_PATH_OFFSET = "vision/path_offset"
SENSORS_COLLISION = "sensors/collision"
DECISION_DRIVE_CMD = "decision/drive_cmd"
MOTION_STATUS = "motion/status"
ACTUATORS_SERVO_CMD = "actuators/servo_cmd"
PLANNER_MISSION = "planner/mission"
PLANNER_TELEMETRY = "planner/telemetry"
