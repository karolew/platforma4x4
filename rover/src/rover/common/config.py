from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel

CONFIG_DIR = Path(os.environ.get("ROVER_CONFIG_DIR", Path(__file__).resolve().parents[3] / "config"))


class ServiceConfig(BaseModel):
    rover_id: str
    mqtt_host: str
    mqtt_port: int
    driver: str
    driver_args: dict[str, Any] = {}


def load_service_config(service_name: str) -> ServiceConfig:
    root = yaml.safe_load((CONFIG_DIR / "rover.yaml").read_text())
    service = yaml.safe_load((CONFIG_DIR / "services" / f"{service_name}.yaml").read_text())
    return ServiceConfig(
        rover_id=root["rover_id"],
        mqtt_host=root["mqtt"]["host"],
        mqtt_port=root["mqtt"]["port"],
        driver=service["driver"],
        driver_args=service.get("driver_args", {}),
    )
