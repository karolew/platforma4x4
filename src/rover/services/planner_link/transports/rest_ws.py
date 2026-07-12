from typing import AsyncIterator

from rover.common.messages.planner import Mission, Telemetry
from rover.services.planner_link.interface import PlannerTransport


class RestWsPlannerTransport(PlannerTransport):
    """Telemetria wysyłana REST-em, misje odbierane przez WebSocket z PLANNER."""

    def __init__(self, base_url: str, rover_id: str) -> None:
        self._base_url = base_url
        self._rover_id = rover_id

    async def connect(self) -> None:
        raise NotImplementedError  # httpx.AsyncClient + websockets.connect

    async def disconnect(self) -> None:
        raise NotImplementedError

    async def send_telemetry(self, telemetry: Telemetry) -> None:
        raise NotImplementedError  # POST {base_url}/rovers/{rover_id}/telemetry

    async def receive_missions(self) -> AsyncIterator[Mission]:
        raise NotImplementedError  # nasłuch WS {base_url}/rovers/{rover_id}/missions
        yield  # pragma: no cover
